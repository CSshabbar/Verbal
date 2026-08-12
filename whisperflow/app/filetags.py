"""
Automatic IDE file tagging (desktop / macOS only).

Mirrors Wispr Flow "Context Awareness / File Tagging":
  - Detect the frontmost IDE (Cursor / Windsurf; VS Code = memory only).
  - Read the names of open/visible files via the macOS Accessibility API.
  - Bias the transcriber toward those names (prompt_fragment).
  - Rewrite spoken references into editor tags: "main dot py" -> "@main.py".

HARD GUARANTEES (see FILE_TAGGING_SWARM.md §1e / §6):
  - Nothing here may crash or stall a recording. Every AX call is wrapped in
    try/except; read_open_files() is time-bounded (~300ms) and returns [] on any
    failure or unsupported app.
  - tag() only ever produces "@name.ext" for files that are in the known set,
    only for names WITH an extension, is deterministic, never double-tags, and
    is a no-op when a dictionary substitution was applied or focus is a terminal.
  - Mobile is out of scope for tagging (Cursor/Windsurf are desktop apps).
"""
import logging
import re
import threading
import time

logger = logging.getLogger("verbal.filetags")

# ── constants ────────────────────────────────────────────────────────────────

# Bundle ids we treat as file-tagging-capable IDEs. All are VS Code / Electron
# forks with an @-file mention picker, so the AX harvest + tag injection are
# identical across them. Name matching (in _classify) is the robust fallback for
# newer IDEs whose exact bundle ids may vary by build/channel.
_CURSOR_BUNDLES = {"com.todesktop.230313mzl4w4u92"}
_WINDSURF_BUNDLES = {"com.exafunction.windsurf", "com.codeium.windsurf"}
_VSCODE_BUNDLES = {"com.microsoft.VSCode", "com.microsoft.VSCodeInsiders"}
_ANTIGRAVITY_BUNDLES = {"com.google.antigravity", "com.google.antigravity-ide"}
_KIRO_BUNDLES = {"dev.kiro.desktop"}

# Every recognized IDE gets FULL tagging (harvest + rewrite + @-mention injection).
TAGGING_IDES = {"cursor", "windsurf", "vscode", "antigravity", "kiro"}

_AX_BUDGET_S = 0.60           # hard wall-clock budget for the AX tree walk
_AX_MAX_NODES = 4000          # cap on total elements visited
_AX_MAX_DEPTH = 40            # Chromium/Electron (Cursor) trees are DEEP: the
                              # file-explorer rows sit around depth 25.
_AX_MAX_CHILDREN = 250        # cap on children considered per node

_SEEN_CAP = 200               # LRU cap for persisted "seen files"

_PROMPT_MAX_WORDS = 120       # keep the Whisper prompt fragment well bounded

# name.ext — a leading filename (letters/digits/space/dot/dash) then a real ext.
_NAME_EXT_RE = re.compile(r"^[\w .\-]+\.[A-Za-z0-9]+$")
# A filename token embedded anywhere in a longer title/description string. The
# extension must START with a letter so version numbers ('v2.0', '1.2') are not
# mistaken for files. 1–8 char extension.
_FILE_TOKEN_RE = re.compile(r"[\w\-]+\.[A-Za-z][A-Za-z0-9]{0,7}\b")

# Homophones a speech model is likely to emit for a spoken file extension.
_EXT_HOMOPHONES = {
    "py": ["py", "pie"],
    "c": ["c", "see"],
    "cpp": ["cpp"],
    "cs": ["cs"],
    "js": ["js"],
    "ts": ["ts"],
    "jsx": ["jsx"],
    "tsx": ["tsx"],
    "md": ["md"],
    "rs": ["rs"],
    "rb": ["rb"],
    "go": ["go"],
    "css": ["css"],
    "scss": ["scss"],
    "html": ["html"],
    "json": ["json"],
    "yml": ["yml"],
    "yaml": ["yaml"],
    "toml": ["toml"],
    "txt": ["txt", "text"],
    "sh": ["sh"],
    "sql": ["sql"],
    "java": ["java"],
    "kt": ["kt"],
    "swift": ["swift"],
    "php": ["php"],
    "vue": ["vue"],
}

# Session cache of file names seen this run (populated by remember_files).
_session_files = []


# ── app detection ──────────────────────────────────────────────────────────

def _frontmost_app():
    """Return the NSRunningApplication that is frontmost, or None. Guarded."""
    try:
        from AppKit import NSWorkspace
        return NSWorkspace.sharedWorkspace().frontmostApplication()
    except Exception as e:
        logger.debug("frontmost app lookup failed: %s", e)
        return None


def _classify(bundle_id, name):
    bundle_id = bundle_id or ""
    name = (name or "").lower()
    nc = re.sub(r"[\s\-_]+", "", name)  # normalized: 'Anti-Gravity' -> 'antigravity'
    if bundle_id in _CURSOR_BUNDLES or "cursor" in name:
        return "cursor"
    if bundle_id in _WINDSURF_BUNDLES or "windsurf" in name or "codeium" in name:
        return "windsurf"
    if bundle_id in _ANTIGRAVITY_BUNDLES or "antigravity" in nc:
        return "antigravity"
    if bundle_id in _KIRO_BUNDLES or "kiro" in nc:
        return "kiro"
    if bundle_id in _VSCODE_BUNDLES or "visual studio code" in name or name == "code":
        return "vscode"
    return None


def supported_ide(bundle_id=None, name=None):
    """Classify an app as a supported IDE ('cursor'/'windsurf'/'vscode'/
    'antigravity'/'kiro' — all get full tagging, see TAGGING_IDES) or None.
    Never raises.

    Pass the saved dictation-target app's (bundle_id, name) — captured at
    recording start — so classification reflects where the user was typing, not
    the live frontmost app (which may be the overlay by transcription time).
    With no args, falls back to the live frontmost app.
    """
    if bundle_id is None and name is None:
        app = _frontmost_app()
        if app is None:
            return None
        try:
            bundle_id = app.bundleIdentifier()
            name = app.localizedName()
        except Exception as e:
            logger.debug("supported_ide attribute read failed: %s", e)
            return None
    return _classify(bundle_id, name)


# ── accessibility harvest ────────────────────────────────────────────────────

def _ax_attr(element, attr):
    """AXUIElementCopyAttributeValue(element, attr) → value or None. Guarded."""
    try:
        from ApplicationServices import AXUIElementCopyAttributeValue
        err, value = AXUIElementCopyAttributeValue(element, attr, None)
        if err:
            return None
        return value
    except Exception:
        return None


def _title_to_name(title):
    """Extract a 'name.ext' from a window/tab title like 'main.py — project'."""
    if not title:
        return None
    try:
        s = str(title).strip()
    except Exception:
        return None
    # Titles usually look like "<file> — <project>" (em/en dash or hyphen).
    for sep in (" — ", " – ", " - ", " — ", " – "):
        if sep in s:
            s = s.split(sep, 1)[0].strip()
            break
    # Editors sometimes prefix a dirty marker.
    s = s.lstrip("*• ").strip()
    if _NAME_EXT_RE.match(s):
        return s
    # Fallback: a tab/row title may embed the filename in extra text, e.g.
    # "README.md, tab 1 of 5" or "route_coordinates_fix.md — Edited". Pull the
    # first embedded 'name.ext' token.
    m = _FILE_TOKEN_RE.search(s)
    if m:
        tok = m.group(0)
        if _NAME_EXT_RE.match(tok):
            return tok
    return None


def read_open_files(pid=None, budget=None, settle=0.0):
    """Best-effort list of open/visible 'name.ext' files in the frontmost IDE.

    Uses the macOS Accessibility API: focused window title + a bounded walk of
    the window's children collecting tab/element titles that look like files.
    `budget` overrides the wall-clock walk budget (seconds) — the background
    harvester passes a large value; the synchronous path uses the small default.

    HARD-GUARDED: every AX call is wrapped, the walk is bounded by node/depth
    caps and a wall-clock budget, and the function returns [] on any failure or
    unsupported app rather than raising.
    """
    _budget = budget if budget else _AX_BUDGET_S
    deadline = time.monotonic() + _budget
    found = []
    seen = set()

    def _add(name):
        if name and name.lower() not in seen:
            seen.add(name.lower())
            found.append(name)

    try:
        if pid is None:
            app = _frontmost_app()
            if app is None:
                return []
            pid = app.processIdentifier()
        if not pid:
            return []

        from ApplicationServices import AXUIElementCreateApplication
        ax_app = AXUIElementCreateApplication(pid)
        if ax_app is None:
            return []

        # CRITICAL for Electron/Chromium apps (Cursor, Windsurf, VS Code): they
        # do NOT expose their web-content accessibility tree until asked. Without
        # this, the walk only sees ~13 native chrome nodes (title bar) and never
        # reaches the editor tabs or file explorer. Setting these attributes makes
        # Chromium build the full tree. It persists for the app's lifetime, so we
        # only pay the build cost once; a short settle delay helps the first run.
        try:
            from ApplicationServices import AXUIElementSetAttributeValue
            _e1 = AXUIElementSetAttributeValue(ax_app, "AXManualAccessibility", True)
            _e2 = AXUIElementSetAttributeValue(ax_app, "AXEnhancedUserInterface", True)
            logger.debug("[filetag] enable AX: AXManualAccessibility err=%s AXEnhancedUserInterface err=%s",
                         _e1, _e2)
        except Exception as _e:
            logger.debug("[filetag] enable AX raised: %s", _e)

        # Chromium builds its web-content tree LAZILY after the attribute is set:
        # the native window chrome (~80 nodes) is present immediately, but the
        # editor tabs + file-explorer rows (~depth 25) appear only after a short
        # delay. The background harvester passes settle>0 to wait for them (it runs
        # off the recording critical path); the synchronous path passes settle=0
        # and just grabs the active file from the window title.
        if settle and settle > 0:
            time.sleep(settle)
        deadline = time.monotonic() + _budget

        window = _ax_attr(ax_app, "AXFocusedWindow")
        if window is None:
            # Fall back to the app's first window if none is "focused" (the app
            # may not be frontmost by transcription time).
            wins = _ax_attr(ax_app, "AXWindows")
            try:
                window = list(wins)[0] if wins else None
            except Exception:
                window = None
        if window is None:
            return []

        # 1) The focused window title is the active file (highest confidence).
        _add(_title_to_name(_ax_attr(window, "AXTitle")))

        # 2) Bounded breadth/depth walk of the window subtree for tab + explorer
        #    titles. Reads AXTitle AND AXDescription (Chromium exposes filenames
        #    on either, depending on the element).
        # Breadth-first: cover shallow containers (tab bar, explorer) before
        # diving deep into editor content, so a bounded walk still finds files.
        from collections import deque
        nodes = 0
        max_depth = 0
        web_areas = 0
        queue = deque([(window, 0)])
        while queue:
            if time.monotonic() > deadline or nodes >= _AX_MAX_NODES:
                break
            node, depth = queue.popleft()
            nodes += 1
            if depth > max_depth:
                max_depth = depth
            if _ax_attr(node, "AXRole") == "AXWebArea":
                web_areas += 1
            for attr in ("AXTitle", "AXDescription"):
                _add(_title_to_name(_ax_attr(node, attr)))
            if depth >= _AX_MAX_DEPTH:
                continue
            children = _ax_attr(node, "AXChildren")
            if not children:
                continue
            try:
                children = list(children)[:_AX_MAX_CHILDREN]
            except Exception:
                continue
            for child in children:
                queue.append((child, depth + 1))
        logger.debug("[filetag] harvest: %d nodes, maxdepth=%d webareas=%d, %d file(s): %s",
                     nodes, max_depth, web_areas, len(found), found)
    except Exception as e:
        logger.debug("read_open_files failed: %s", e)
        return []

    return found


_harvesting = threading.Lock()


def harvest_async(pid, config=None, save_config_fn=None, budget=4.0):
    """Fire-and-forget deep harvest OFF the recording critical path.

    Called at record-start: Cursor's AX tree is slow to walk (thousands of nodes)
    and builds lazily after AXManualAccessibility is enabled, so we walk it in a
    background thread with a large budget WHILE the user is speaking. Results land
    in the session + persisted cache (get_seen_files), which the transcriber then
    reads instantly at finalize time. Never raises; skips if one is already running.
    """
    if pid is None:
        return
    if not _harvesting.acquire(blocking=False):
        return  # a harvest is already in flight — don't stack them

    def _run():
        try:
            # settle: wait for Chromium's lazily-built web tree before walking.
            files = read_open_files(pid, budget=budget, settle=1.3)
            if files:
                remember_files(config, files, save_config_fn)
        except Exception as e:
            logger.debug("harvest_async failed: %s", e)
        finally:
            _harvesting.release()

    try:
        threading.Thread(target=_run, daemon=True).start()
    except Exception:
        _harvesting.release()


def focus_is_terminal():
    """Best-effort: is the system-wide focused element an IDE terminal?

    Uses AXUIElementCreateSystemWide → focused UI element role/title heuristics.
    Returns False on ANY uncertainty (never raises) — we only skip tagging when
    we are reasonably confident focus is a terminal.
    """
    try:
        from ApplicationServices import AXUIElementCreateSystemWide
        system = AXUIElementCreateSystemWide()
        if system is None:
            return False
        focused = _ax_attr(system, "AXFocusedUIElement")
        if focused is None:
            return False

        role = _ax_attr(focused, "AXRole")
        subrole = _ax_attr(focused, "AXSubrole")
        for token in (role, subrole):
            if token and "terminal" in str(token).lower():
                return True

        # Walk up to a couple of ancestors checking title/description hints.
        node = focused
        for _ in range(3):
            for attr in ("AXTitle", "AXDescription", "AXIdentifier"):
                val = _ax_attr(node, attr)
                if val and "terminal" in str(val).lower():
                    return True
            parent = _ax_attr(node, "AXParent")
            if parent is None:
                break
            node = parent
    except Exception as e:
        logger.debug("focus_is_terminal failed: %s", e)
        return False
    return False


# ── seen-files memory ────────────────────────────────────────────────────────

def _norm_files(files):
    """Keep only well-formed 'name.ext', dedupe case-insensitively, preserve
    first-seen order."""
    out = []
    seen = set()
    for f in files or []:
        try:
            f = str(f).strip()
        except Exception:
            continue
        if not f or not _NAME_EXT_RE.match(f):
            continue
        key = f.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(f)
    return out


def get_seen_files(config):
    """Persisted seen files (config['filetag_files']) merged with this session's
    cache. Most-recent first, deduped, capped."""
    persisted = _norm_files((config or {}).get("filetag_files", []))
    # Session files take precedence (most recently observed).
    merged = _norm_files(list(_session_files) + persisted)
    return merged[:_SEEN_CAP]


def remember_files(config, files, save_config_fn):
    """Record newly observed files in the session cache + persist to config.

    LRU-capped at 200, deduped case-insensitively, only 'name.ext'. Writes
    config ONLY when the persisted list actually changed (avoids save_config
    churn — the config-race lesson).
    """
    global _session_files
    new = _norm_files(files)
    if not new and not _session_files:
        # Nothing to do and nothing cached.
        if config is None:
            return []

    # Update session cache: newest first.
    _session_files = _norm_files(new + list(_session_files))[:_SEEN_CAP]

    if config is None:
        return list(_session_files)

    old = _norm_files(config.get("filetag_files", []))
    merged = _norm_files(list(_session_files) + old)[:_SEEN_CAP]

    if merged != old and save_config_fn is not None:
        config["filetag_files"] = merged
        try:
            save_config_fn(config)
        except Exception as e:
            logger.debug("remember_files save failed: %s", e)
    else:
        config["filetag_files"] = merged
    return merged


# ── prompt biasing ───────────────────────────────────────────────────────────

def prompt_fragment(files):
    """A short 'Files: a.ts, b.py.' fragment to bias the Whisper prompt toward
    the open file names. None if there is nothing to add."""
    names = _norm_files(files)
    if not names:
        return None
    fragment = "Files: " + ", ".join(names) + "."
    parts = fragment.split()
    if len(parts) > _PROMPT_MAX_WORDS:
        fragment = " ".join(parts[:_PROMPT_MAX_WORDS])
    return fragment


# ── tagging ──────────────────────────────────────────────────────────────────

def _split_stem_tokens(stem):
    """Break a file stem into spoken word tokens.

    'useAuth' -> ['use','Auth']; 'my_file-name' -> ['my','file','name'];
    'main' -> ['main']; 'v2Client' -> ['v2','Client'] (rough)."""
    tokens = []
    for chunk in re.split(r"[_\-. ]+", stem):
        if not chunk:
            continue
        parts = re.findall(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+", chunk)
        tokens.extend(parts or [chunk])
    return tokens or [stem]


# Between two stem tokens the speaker may say nothing ('useAuth'->'useauth'),
# a space/underscore/dash, OR the SEPARATOR WORD itself — Whisper transcribes
# 'route_coordinates' as 'route underscore coordinates'.
_TOK_SEP = r"(?:\s+(?:underscore|under score|dash|hyphen)\s+|[\s_\-]*)"


def _stem_pattern(stem):
    """Regex matching the spoken form of a stem, tolerating spaces/underscores
    (literal or spoken) between camelCase/underscore words (so 'useAuth' matches
    'use auth'/'useAuth' and 'route_coordinates' matches 'route underscore
    coordinates')."""
    tokens = _split_stem_tokens(stem)
    return _TOK_SEP.join(re.escape(t) for t in tokens)


def _ext_pattern(ext):
    alts = _EXT_HOMOPHONES.get(ext.lower(), [ext])
    # de-dupe while preserving order, escape each
    seen = []
    for a in alts:
        if a not in seen:
            seen.append(a)
    return r"(?:" + r"|".join(re.escape(a) for a in seen) + r")"


# Separator between a spoken stem and its extension: literal '.' or ' dot '.
_SEP = r"(?:\s*\.\s*|\s+dot\s+)"
# Optional command prefixes that introduce a file reference.
_PREFIX_ANY = r"(?:(?:at\s+file|tag\s+file|file|tag|at|mention|open)\s+)?"
_PREFIX_STRONG = r"(?:at\s+file|tag\s+file|mention|open|file)\s+"
# Bare-stem tagging (pass 3) only runs when the utterance shows file intent.
_FILE_TRIGGER_RE = re.compile(r"(?<![@\w])(?:at\s+file|tag\s+file|file|open|tag|mention)\b", re.IGNORECASE)


def _split_name(fname):
    """('useAuth.ts') -> ('useAuth', 'ts'); returns (stem, ext) or (None, None)
    if there is no usable extension."""
    if "." not in fname:
        return None, None
    stem, _, ext = fname.rpartition(".")
    if not stem or not ext or not re.match(r"^[A-Za-z0-9]+$", ext):
        return None, None
    return stem, ext


def tag(text, files, dict_applied=False, is_terminal=False):
    """Rewrite spoken references to a KNOWN file into '@name.ext'.

    Handles: bare 'main.py'; 'main dot py' / 'main dot pie' (spoken separator +
    homophone extension); 'at file use auth' / 'file useAuth' (prefix + spoken
    stem, extension resolved from the known file).

    Rules (all enforced): only files WITH an extension are ever tagged; if
    `dict_applied` OR `is_terminal` the text is returned unchanged; a file not
    in `files` is never tagged; an already-'@name.ext' reference is never
    double-tagged; matching is deterministic (longest/most-specific first).
    """
    if not text or dict_applied or is_terminal:
        return text

    # Build (fname, stem, ext) for every known file that has a real extension,
    # sorted most-specific first for deterministic, longest-match-wins behavior.
    candidates = []
    seen_keys = set()
    for f in files or []:
        try:
            f = str(f).strip()
        except Exception:
            continue
        if not f or not _NAME_EXT_RE.match(f):
            continue
        stem, ext = _split_name(f)
        if stem is None:
            continue
        key = f.lower()
        if key in seen_keys:
            continue
        seen_keys.add(key)
        candidates.append((f, stem, ext))

    if not candidates:
        return text

    candidates.sort(key=lambda c: (len(c[1]) + len(c[2]), c[0]), reverse=True)

    result = text

    def _repl(fname):
        return lambda m: "@" + fname

    # Pass 1 — extension present in speech (prefix optional). Highest confidence.
    for fname, stem, ext in candidates:
        pat = (
            r"(?<![@\w])"
            + _PREFIX_ANY
            + _stem_pattern(stem)
            + _SEP
            + _ext_pattern(ext)
            + r"(?!\w)"
        )
        try:
            result = re.sub(pat, _repl(fname), result, flags=re.IGNORECASE)
        except re.error:
            continue

    # Pass 2 — strong prefix ('at file' / 'file' / …) + spoken stem, extension
    # optional and resolved from the known file.
    for fname, stem, ext in candidates:
        pat = (
            r"(?<![@\w])"
            + _PREFIX_STRONG
            + _stem_pattern(stem)
            + r"(?:" + _SEP + _ext_pattern(ext) + r")?"
            + r"(?!\w)"
        )
        try:
            result = re.sub(pat, _repl(fname), result, flags=re.IGNORECASE)
        except re.error:
            continue

    # Pass 2b — spoken stem immediately FOLLOWED by the word 'file' ('the README
    # file', 'the main file', 'open the settings file'). This is the natural way
    # people name a file in speech; the trailing 'file' is a strong signal, and the
    # stem must still exactly match a known open file. Extension optional; the
    # trailing 'file' is consumed so 'go over the readme file' -> 'go over @README.md'.
    for fname, stem, ext in candidates:
        pat = (
            r"(?<![@\w])"
            + _stem_pattern(stem)
            + r"(?:" + _SEP + _ext_pattern(ext) + r")?"
            + r"\s+file\b"
        )
        try:
            result = re.sub(pat, _repl(fname), result, flags=re.IGNORECASE)
        except re.error:
            continue

    # Pass 3 — bare multi-token stem (no prefix, no extension). ONLY runs when the
    # utterance shows file-reference intent (a trigger word like file/open/tag/at
    # file/mention appears), so ordinary speech such as "update my config before
    # lunch" is never hijacked into "@myConfig.json". Single-word stems still
    # require a prefix or extension (passes 1–2) and are never bare-matched.
    if _FILE_TRIGGER_RE.search(text):
        for fname, stem, ext in candidates:
            if len(_split_stem_tokens(stem)) < 2:
                continue
            pat = r"(?<![@\w])" + _stem_pattern(stem) + r"(?!\w)"
            try:
                result = re.sub(pat, _repl(fname), result, flags=re.IGNORECASE)
            except re.error:
                continue

    return result


# ── Windows platform shim ────────────────────────────────────────────────
# On Windows the AX harvest / IDE classification / terminal detection all use
# UI Automation (see app/win_ax.py). Override the four swap functions AFTER
# the pure logic above so the cross-platform callers (transcriber, main) can
# keep importing app.filetags unchanged — same names, Windows-native
# implementations. All pure helpers (tag, prompt_fragment, remember_files,
# get_seen_files, _norm_files) stay shared.
import sys as _sys
if _sys.platform == "win32":  # pragma: no cover - platform gate
    try:
        from app.win_ax import (
            supported_ide as _win_supported_ide,
            read_open_files as _win_read_open_files,
            harvest_async as _win_harvest_async,
            focus_is_terminal as _win_focus_is_terminal,
        )
        supported_ide     = _win_supported_ide
        read_open_files   = _win_read_open_files
        harvest_async     = _win_harvest_async
        focus_is_terminal = _win_focus_is_terminal
    except Exception as _e:  # win_ax not built / uiautomation missing
        logger.debug("filetags: Windows shim not loaded (%s); AX harvest disabled", _e)
