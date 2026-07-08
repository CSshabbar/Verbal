# File Tagging — Context / Harness / Loop Engineering Spec

> Single source of truth for building **automatic IDE file tagging** in Verbal.
> Read this top-to-bottom before spawning any agent. Everything an agent needs to
> act correctly (context), how the agents are wired (harness/swarm), and the
> iterate-until-proven loop (loop engineering) lives here.

---

## 0. MISSION (the loop's success criterion)

**When a user is focused in a supported IDE and speaks a file name, that file is
inserted into their text as a correct tag — `@name.ext` — automatically.**

Concretely, this is DONE when all of the following hold on a real machine:

1. User is in **Cursor** or **Windsurf**, a project with files like `main.py`,
   `useAuth.ts`, `README.md` is open.
2. User dictates: *"open at file main dot pie and check use auth"* →
   output contains **`@main.py`** and **`@useAuth.ts`** (correctly cased/extended).
3. A file that isn't open / doesn't exist is **not** tagged (no false tags).
4. It never fires in the IDE **terminal**, never tags a word without an
   extension, and never crashes or slows a recording noticeably.
5. Works with the custom-dictionary feature already shipped (shared machinery),
   and is gated behind a user **toggle**.

If any of 1–5 fails, the loop is **not** complete.

---

## 1. CONTEXT (ground truth — do not re-derive)

### 1a. What the feature is
Detect the frontmost IDE → read the names of its open/visible files via the
macOS Accessibility API → (a) **bias** the transcriber toward those names so they
are heard correctly, and (b) **rewrite** spoken references into editor tags
(`@name.ext`). Mirrors Wispr Flow "Context Awareness / File Tagging."

### 1b. Wispr Flow's documented behavior (the bar to match)
- File tagging runs **only in Cursor + Windsurf**; VS Code = file-name memory only.
- Reads **file names, variable names, nearby text, app metadata** — **locally**,
  then sends relevant context to the transcription API during dictation.
- **Remembers file names across sessions.**
- Tags **only filenames with an extension** (`file.ts`, not `file`).
- Does **NOT** run: inside the IDE terminal; when a dictionary substitution was
  applied to that transcript; when the File-Tagging setting is off.

### 1c. The technical mechanism (how the data is obtained)
macOS **Accessibility API** (needs Accessibility permission + non-sandboxed — the
app already has both, used for pasting):
- Frontmost app + pid: `NSWorkspace.sharedWorkspace().frontmostApplication()`.
- `AXUIElementCreateApplication(pid)` → `kAXFocusedWindowAttribute` → window
  `kAXTitleAttribute` (usually `"main.py — project"` = the active file).
- Walk window children for tab/radio-button elements whose titles match
  `name.ext` = the open files.
- System-wide focus + nearby text: `AXUIElementCreateSystemWide()` →
  `kAXFocusedUIElement` → `kAXValueAttribute` / `kAXSelectedTextAttribute`.
- Terminal detection: focused element role / tab title (e.g. no extension, or a
  known terminal container) → skip.

### 1d. Existing code to REUSE (do not reinvent)
- `whisperflow/app/injector.py :: get_focused_app_name()` — frontmost app (has
  the `NSWorkspace` handle + saved pid used for paste).
- `whisperflow/app/dictionary.py` — `build_prompt()` (vocab → Whisper prompt),
  `apply_replacements()`. **File names are dynamic, session-scoped vocabulary.**
- `whisperflow/app/transcriber.py :: transcribe_with_status()` — already builds a
  prompt from the dictionary and passes `prompt=` to `_transcribe_groq`/`_gemini`;
  already runs a post-transcription `finalize()` pass. **Hook here.**
- `whisperflow/app/main.py :: _process_audio()` — the recording→transcribe→paste
  path; `save_focused_app()` already snapshots the target app before pasting.
- Existing "at file main.py → @main.py" command referenced in the About text —
  a rudimentary tagger to supersede.
- `config.py` (atomic `save_config` + lock) for persistence; add a settings toggle.
- Dictionary lives on its own **Dictionary screen** in the dashboard — the
  File-Tagging toggle + "seen files" list belong there or in Settings.

### 1e. Hard constraints / guardrails (violating any = failure)
- **Never crash or stall a recording.** All AX reads wrapped in try/except with a
  hard timeout; failure = feature silently no-ops, transcription proceeds.
- **Non-negotiable Wispr rules:** only `name.ext`; skip terminal; skip when a
  dictionary substitution already applied; respect the toggle (default OFF until
  proven, then decide).
- **No changes to** `overlay.py` visuals or the sound effects (`play_*`).
- **Desktop is the target** (Cursor/Windsurf are desktop). Mobile is out of scope
  for tagging (note it, don't build it).
- Keep it **behind a flag** so it can't regress the shipped dictionary or recording.
- Every code change must **compile (`py_compile`) + import + `node --check`** the
  generated dashboard JS before it counts as done.

---

## 2. TARGET ARCHITECTURE (what to build)

New module `whisperflow/app/filetags.py`:
- `supported_ide() -> str|None` — bundle-id/name check for Cursor/Windsurf.
- `read_open_files(pid) -> list[str]` — AX harvest: window title + tabs → `*.ext`
  names; graceful fallback (title only); timeout-guarded.
- `focus_is_terminal() -> bool` — skip condition.
- `session_files` cache (+ persisted "seen files" in config, LRU-capped).
- `prompt_fragment(files) -> str` — merge into the Whisper prompt.
- `tag(text, files, dict_applied) -> str` — rewrite spoken file references to
  `@name.ext`; obey the extension-only + terminal + dict-substitution rules.

Wiring:
- In `transcribe_with_status`: if `supported_ide()` and toggle on and not terminal,
  append `prompt_fragment(files)` to the dictionary prompt; after transcription,
  run `tag(...)` (after, and conditioned on, dictionary replacements).
- Toggle + seen-files UI on the Dictionary screen.

---

## 3. HARNESS ENGINEERING (how agents run)

- **Topology:** an **Orchestrator** owns the loop; it fans work to specialist
  agents, collects structured results, and gates progress on verification.
- **Determinism:** control flow (order, retries, done-checks) is fixed by the
  orchestrator; agents only do their scoped job and return structured output.
- **Isolation:** agents that mutate files run in a **git worktree** so parallel
  edits don't collide; read-only agents never write.
- **Every produced change is verified by a DIFFERENT agent than the one that
  wrote it** (author ≠ reviewer). Nothing merges unverified.
- **Structured hand-offs:** each agent returns `{status, artifacts, evidence,
  blockers}` — never prose the orchestrator has to parse loosely.
- **Budget:** phases are cheap→expensive (scout → build → adversarial verify);
  stop early when acceptance tests pass.

---

## 4. THE SWARM (agents · responsibilities · conditions · rules)

Each agent has: **Role**, **Inputs**, **Outputs**, **Done-when**, **Rules**.

### A1 — Recon Agent (read-only)
- **Role:** Confirm §1d facts against the current tree; locate exact insertion
  points (line refs) in `transcriber.py`, `main.py`, dictionary UI.
- **Inputs:** this file.
- **Outputs:** a map of {file:line} anchors + any drift from §1d.
- **Done-when:** every anchor verified to exist.
- **Rules:** no edits; if §1d is stale, report — do not silently adapt.

### A2 — AX-Harvester Agent
- **Role:** Build `read_open_files(pid)` + `focus_is_terminal()` in `filetags.py`
  using PyObjC `ApplicationServices`/`HIServices` AXUIElement calls.
- **Outputs:** the harvester + a standalone manual test (`python -c` that prints
  open files while Cursor is focused).
- **Done-when:** returns real `*.ext` names for a focused Cursor window; returns
  `[]` (never raises) for unsupported/again-and-terminal cases.
- **Rules:** hard 300ms timeout; wrap every AX call in try/except; only
  Cursor/Windsurf bundle ids; NEVER touch the recording path directly.

### A3 — App-Detector Agent
- **Role:** `supported_ide()` — frontmost app → bundle id → Cursor/Windsurf/None;
  reuse `get_focused_app_name()` machinery, don't duplicate NSWorkspace state.
- **Done-when:** correct classification for Cursor, Windsurf, VS Code (→ memory
  only), and a non-IDE app (→ None).
- **Rules:** pure/fast; no network; no side effects.

### A4 — Memory Agent
- **Role:** session + persisted "seen files" cache (config), dedupe, LRU cap
  (e.g. 200), only `name.ext`.
- **Done-when:** files seen in one session are recognized in the next; cap holds.
- **Rules:** use the atomic `save_config` + lock; **write only on change**
  (the config-race lesson); never write per-transcription in a tight loop.

### A5 — Injector Agent
- **Role:** `prompt_fragment(files)` and the hook in `transcribe_with_status`
  that merges it with the dictionary prompt.
- **Done-when:** spoken open-file names transcribe with correct spelling more
  often (measured by A8 fixtures); dictionary prompt still works.
- **Rules:** reuse `dictionary.build_prompt` style; keep total prompt under the
  Whisper token budget; feature-flag gated.

### A6 — Tagger Agent
- **Role:** `tag(text, files, dict_applied)` — detect spoken references to known
  files ("main dot py", "at file use auth", bare "main.py") and rewrite to
  `@name.ext`; plus the post-transcribe wiring.
- **Done-when:** A8 fixtures pass, including the negatives.
- **Rules (Wispr parity, all enforced):** only files with an extension; **skip
  entirely if `dict_applied` is true**; **skip if `focus_is_terminal()`**; never
  tag a file not in the known set; never double-tag; deterministic.

### A7 — Integration Agent (worktree)
- **Role:** wire A2–A6 into `transcriber.py`/`main.py`, add the **toggle** +
  seen-files list to the Dictionary screen, add `app.filetags` to the 3 specs.
- **Done-when:** `py_compile` + `import app.main` + `node --check` dashboard JS
  all pass; feature flag default set; nothing else changed.
- **Rules:** touch only what's necessary; do not modify `overlay.py`, sounds, or
  unrelated code; keep the shipped dictionary + recording paths intact.

### A8 — QA / Adversarial Verifier Agent (author ≠ this agent)
- **Role:** write + run fixtures that DON'T need a mic: given `(transcript,
  known_files, dict_applied, is_terminal)` assert `tag()` output. Cover:
  correct tag, casing/extension recovery, unknown file (no tag), terminal (no
  tag), dict-applied (no tag), multiple files, punctuation ("dot"), no-op text.
- **Done-when:** all fixtures green; tries to BREAK the tagger and reports holes.
- **Rules:** adversarial by default — assume the tagger is wrong until fixtures
  prove otherwise; a single red fixture blocks "done".

### A9 — Orchestrator / Loop Agent
- **Role:** run §5 loop; sequence A1→A2/A3→A4→A5→A6→A7→A8; gate on evidence;
  decide done vs. iterate; surface a crisp status + the one manual on-device
  check the human must run.
- **Rules:** never declare success on unverified work; if A8 red, route the
  specific failure back to the owning agent with the failing fixture; stop when
  §0 criteria 1–5 are provably met (fixtures) + human confirms on device.

---

## 5. LOOP ENGINEERING (iterate until proven)

```
recon (A1)
  └─ build data layer:  A2 (harvest) ‖ A3 (detect) ‖ A4 (memory)      [parallel, read-mostly]
       └─ build language layer: A5 (inject) → A6 (tag)                 [sequential; tag needs files+rules]
            └─ integrate: A7 (wire + flag + compile/lint/import)
                 └─ verify: A8 (adversarial fixtures)
                      ├─ ALL GREEN → hand human the ONE on-device test (§0.1–2)
                      │                 └─ human confirms → DONE
                      └─ ANY RED  → orchestrator routes failing fixture to owner
                                        (A2 wrong files? A6 wrong rule?) → re-run from there
```

**Termination:** loop exits only when A8 is fully green **and** the human on-device
check passes. Bad-path (can't read AX / unknown IDE) must degrade to "no tags,
transcription unaffected" — that is a valid stable state, not a failure to retry
forever.

**Anti-thrash:** cap at N build↔verify cycles; if the AX harvest proves too
fragile for full tab-walking, fall back to the **window-title-only** slice (§ Wispr
80/20) and ship that, logging what was dropped.

---

## 6. GLOBAL RULES (every agent, always)

1. **Do no harm to recording.** If in doubt, no-op and let transcription proceed.
2. **Verify before claiming done** — compile + import + `node --check` + fixtures.
3. **Author ≠ verifier.** Self-certified code doesn't merge.
4. **Reuse the dictionary machinery**; don't fork prompt/replace logic.
5. **Respect the toggle** and the three Wispr skip-conditions.
6. **Only `name.ext`.** Never invent or tag unknown files.
7. **Structured returns** only; evidence (fixture output, file:line) over prose.
8. **Don't touch** overlay visuals, sounds, auth, canvas, notes.
9. **macOS/desktop only** for tagging; note mobile as out-of-scope.
10. Every network/AX/file op is timeout- and exception-guarded.

---

## 7. DEFINITION OF DONE (acceptance)

- [ ] `filetags.py` exists; `read_open_files` returns real files for Cursor.
- [ ] `supported_ide()` classifies Cursor/Windsurf/VS Code/other correctly.
- [ ] Speaking an open file name yields `@name.ext` in the transcript.
- [ ] Unknown file → not tagged. Terminal → not tagged. Dict-substitution → not tagged.
- [ ] Session-persisted seen-files memory works across restarts.
- [ ] Toggle present; OFF = zero behavior change.
- [ ] All A8 fixtures green; `py_compile` + import + `node --check` clean.
- [ ] Human on-device confirmation in Cursor recorded here: __________
