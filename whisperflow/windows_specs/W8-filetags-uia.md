# W8 — File-tags: `win_ax.py` (IUIAutomation harvest) behind a PLATFORM shim

**Goal:** replicate `app/filetags.py`'s frontmost-app detection + accessibility-tree harvest on
Windows using **UI Automation** (`IUIAutomation` tree walk via `uiautomation`/`comtypes`), enabling
Chromium a11y for Electron editors (the Windows analog of macOS `AXManualAccessibility`). **Keep the
pure rewrite/prompt logic**; swap only the harvest layer behind a platform shim.

## Files

- **Create:** `app/win_ax.py` — Windows harvest + IDE detection with the **same public names**
  `filetags.py` exposes.
- **Reuse (import, do not reimplement):** the pure logic in `app/filetags.py` — `tag()`,
  `prompt_fragment()`, `_norm_files`, `get_seen_files`, `remember_files`, `_split_name`,
  `_stem_pattern`, `_ext_pattern`, `_split_stem_tokens`, and the `TAGGING_IDES` set. These are string/
  regex/config functions with **no AppKit** — import them.
- **Reference (Mac):** `app/filetags.py` (the AX harvest is what you replace).
- **Depends on / used by:** `app/win_injector.py` (W5) calls `win_ax.supported_ide()` +
  `win_ax.TAGGING_IDES`; the pipeline calls `win_ax.harvest_async(pid, ...)` at record-start.

## KEEP (pure) vs SWAP (native harvest)

`filetags.py` splits cleanly. Put the platform boundary at the **tree harvest + frontmost-app + a11y
enable** functions.

**KEEP — reuse verbatim (import from `filetags`):**
- `tag(text, files, dict_applied=False, is_terminal=False)` — rewrites `name.ext` mentions in the
  transcript into `@name.ext` tags (the regex/stem/ext matching engine). This is the payload W5's
  mention path consumes.
- `prompt_fragment(files)` — builds the ≤120-word Whisper prompt fragment (`_PROMPT_MAX_WORDS`).
- `_norm_files`, `get_seen_files(config)`, `remember_files(config, files, save_config_fn)` — the
  seen-files memory (used even for VS Code, which is "memory only").
- `TAGGING_IDES = {"cursor", "windsurf", "vscode", "antigravity", "kiro"}`.

**SWAP — reimplement in `win_ax.py` (native):**
- `_frontmost_app()` — macOS `NSWorkspace.frontmostApplication()` → **Windows:**
  `GetForegroundWindow` + `GetWindowThreadProcessId` → PID + exe (reuse `win_injector`'s helpers or
  `uiautomation.GetForegroundControl()`).
- `_classify(bundle_id, name)` / `supported_ide(bundle_id=None, name=None)` — macOS classifies by
  **bundle id**; **Windows:** classify by **exe basename** (`cursor.exe`→`cursor`,
  `windsurf.exe`→`windsurf`, `code.exe`→`vscode`, plus `antigravity`/`kiro`). Return a key in
  `TAGGING_IDES` or `None`. Keep the signature — W5 calls `supported_ide(exe, window_title)`.
- `read_open_files(pid=None, budget=None, settle=0.0)` — macOS walks the AX tree reading
  `AXTitle`/`AXDescription` under `AXWebArea` after enabling `AXManualAccessibility`. **Windows:**
  walk the **UIA tree** of the target process and collect file-name-looking strings from tab items /
  document titles / editor tab controls. Return a list of `name.ext` strings (then pass through the
  reused `_norm_files`).
- `harvest_async(pid, config=None, save_config_fn=None, budget=4.0)` — same contract: spawn a daemon
  thread that calls `read_open_files(pid, ...)` and `remember_files(...)`. Reuse the Mac's threading
  shape (`filetags.harvest_async` lines ~307–336) — only the inner `read_open_files` differs.
- `focus_is_terminal()` — macOS uses `AXUIElementCreateSystemWide` focused-element role heuristics;
  **Windows:** check the focused UIA control's ControlType/class (terminal panes in VS Code/Cursor,
  Windows Terminal `WindowsTerminal.exe`, ConHost) → bool. Used so terminal dictation doesn't get
  file-tagged.

## Public interface `win_ax.py` MUST expose (names `filetags.py` uses)

```python
TAGGING_IDES = {...}                              # re-export from filetags
def supported_ide(bundle_id=None, name=None): ... # exe-based on Windows
def read_open_files(pid=None, budget=None, settle=0.0) -> list[str]: ...
def harvest_async(pid, config=None, save_config_fn=None, budget=4.0): ...
def focus_is_terminal() -> bool: ...
# re-export the pure helpers so callers can `from app import win_ax` uniformly:
from app.filetags import tag, prompt_fragment, get_seen_files, remember_files, _norm_files
```

> Consider a **shim in `filetags.py`** (top-of-file `if sys.platform=='win32': from app.win_ax import
> read_open_files, supported_ide, harvest_async, focus_is_terminal`) so the cross-platform callers can
> keep importing `app.filetags` unchanged. Whichever way, keep the names identical.

## Enabling Chromium accessibility for Electron editors (the AXManualAccessibility analog)

Cursor / Windsurf / VS Code are Electron/Chromium apps whose accessibility tree is **not exposed by
default** — the equivalent of the macOS `AXManualAccessibility` + `AXEnhancedUserInterface` toggle
(`filetags.py` lines ~230–233). On Windows the a11y tree builds when an assistive client engages.
Approaches (try in order, fail-closed):

1. **Passive engage:** simply constructing the UIA tree walk / calling
   `element.GetChildren()`/`FindAll` on the Chromium window often triggers Chromium to build its
   accessibility tree (Chromium responds to `WM_GETOBJECT` / active UIA clients). A short **settle
   delay** after first touch (the Mac uses a settle delay too) lets the tree populate before you read.
2. **Force the flag:** Chromium honors `--force-renderer-accessibility`. For editors the user can't
   relaunch with flags, rely on (1); document that first-harvest may be empty and the seen-files
   memory fills in on subsequent recordings.
3. **Probe via `WM_GETOBJECT`** on the renderer HWND to nudge the tree, then walk.

Bound the walk hard (mirror `filetags`: `_AX_BUDGET_S=0.60`, `_AX_MAX_NODES=4000`, `_AX_MAX_DEPTH=40`,
`_AX_MAX_CHILDREN=250`) — Chromium/Electron trees are deep; never let the walk stall the pipeline.

## Supported editors

Same set as Mac `TAGGING_IDES`, by exe:

| Editor | exe | tagging? |
|---|---|---|
| Cursor | `Cursor.exe` | full `@`-mention tagging |
| Windsurf | `Windsurf.exe` | full |
| VS Code | `Code.exe` | memory-only on Mac (VS Code has no `@file` picker) — match Mac behavior |
| Antigravity | `antigravity`/exe | full |
| Kiro | `kiro`/exe | full |

(Confirm exact exe basenames on the target machines; classification is lowercased basename → key.)

## Wiring in `win_main`

- At **record-start** (in `_on_record_start`, mirroring `main.py` ~lines 606–610): if
  `self.config.get("filetag_enabled")`, call `win_ax.harvest_async(get_focused_app_pid(), self.config,
  save_config_fn)` so open files are known by transcription time.
- Feed `prompt_fragment(get_seen_files(config))` into the transcription prompt (parity with Mac) so
  Whisper spells filenames right — check how `main.py`/`transcriber` consume the fragment and mirror.
- At inject time, W5's `_inject_with_mentions` uses `tag()`'d text; ensure the transcript is passed
  through `tag(result, files, ...)` before injection when file-tagging is on (mirror the Mac pipeline).

## Acceptance

- [ ] `supported_ide("Cursor.exe")` → `"cursor"`; `supported_ide("notepad.exe")` → `None`.
- [ ] `read_open_files(pid_of_cursor)` returns the open editor tabs' `name.ext` (may need a second
      recording as the Chromium tree warms up — document the warm-up).
- [ ] Dictating "open at main dot pie and utils dot pie" into Cursor with file-tagging on yields
      `@main.py` / `@utils.py` real chips (via W5).
- [ ] `focus_is_terminal()` is True in a VS Code integrated terminal / Windows Terminal → no tagging.
- [ ] Every harvest/read is bounded and guarded — a slow/blocked editor never delays dictation.
