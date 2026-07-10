# 05 — Conventions, Gotchas & Design System

> Part of the `context/` knowledge set. See `context/README.md` for the maintenance rule.
> **Keep this current:** when a new hard-won rule, gotcha, or design token is established, add it here so
> future work (and chat suggestions) don't reintroduce a fixed bug. When a module dies, list it below.

## Hard rules (violating these has broken the app before)

1. **Never break the dictation path.** File-tagging, auto-learn, sync, dictionary-cloud, and the canvas
   listener are all wrapped in try/except and **fail closed** (silent no-op). Any new peripheral feature
   must do the same — recording→transcribe→inject must always proceed. (`filetags.py`/`autolearn.py` carry
   explicit "HARD GUARANTEES" docstrings.)

2. **Verify generated web UI:** the WKWebView/pywebview HTML+JS is produced by Python strings. After any
   change, `node --check` the extracted `<script>` blocks. The desktop dashboard JS lives in a **raw
   string** (`flume_dashboard_html.py`) — inside it, JS escapes use a **single** backslash (`\s`, not
   `\\s`); `shared_dashboard._html()` uses doubled backslashes in places deliberately (e.g. `.split("\\n")`).
   Mixing the two silently corrupts the injected JS. Always: `py_compile` + `import app.main` +
   `node --check` the rendered script blocks.

3. **Config writes are atomic + locked.** Only write config via `config.py::save_config` (unique
   `tempfile.mkstemp` name + `os.replace` under `_config_lock`). Never share a temp filename across
   threads (a shared `config.tmp` caused a rename race). Cloud fetches write config **only when content
   changed** (avoids save churn).

4. **Main-thread discipline (macOS).** WKWebView and all AppKit UI must be touched on the main thread —
   route every background→UI hop through `main._on_main` / the `rumps.Timer` UI queue. Background threads
   never call WebView/AppKit directly.

5. **AX / Electron accessibility (file-tagging, auto-learn).** Cursor/Windsurf/VS Code/Antigravity/Kiro do
   NOT expose their web-content AX tree until you set **`AXManualAccessibility` + `AXEnhancedUserInterface`**
   on the app element; the tree builds **lazily** (needs a settle delay ~1.3 s), and the file-explorer rows
   sit ~depth 25 (walk depth ≤40). Do the deep harvest on a **background thread at record-start**, off the
   critical path. Always **exclude terminals and secure fields**; require the inserted text to be found in
   the field before trusting a read (Electron reads are flaky). See `electron-ax-file-tagging` memory.

6. **Groq prompt 896-char cap.** The Whisper bias prompt (dictionary glossary + open-file list) must stay
   under Groq's 896-char limit or every call 400s. `transcriber.py` trims to `_GROQ_PROMPT_CHAR_CAP=850`
   at a comma boundary, glossary first.

7. **Fonts:** AppKit views use CoreText-registered faces (`theme.py`); **WKWebViews can't resolve those by
   name** → inline TTFs as base64 `@font-face` via `fonts_css.web_font_css()`.

8. **Non-activating panels:** the overlay + auto-learn widget use
   `NSWindowStyleMaskBorderless | NSNonactivatingPanelMask` at `NSScreenSaverWindowLevel` so they never
   steal key focus from the app being dictated into. Any new floating HUD must too.

9. **Anti-nag memory:** once a word is offered by auto-learn (Add *or* dismiss) it's recorded in
   `config['autolearn_declined']` and never re-offered. (This is why re-testing the *same* word shows
   nothing — test with a fresh word, or clear the list.)

10. **Supabase RLS must be `TO public`, not `TO anon`, on any table both clients share.** The desktop
   talks to Supabase with the raw anon key (role `anon`); a *signed-in* mobile client sends the user's JWT
   (role `authenticated`). A policy scoped `TO anon` silently filters out the authenticated client's rows —
   this is what broke dictionary/snippet sync to signed-in phones (fixed via
   `whisperflow/supabase_dictionary_rls_fix.sql`). `pairings` still has the latent `TO anon` pattern.

## Design system (Flume)

Single source: desktop `app/theme.py` + `app/fonts_css.py`; mobile `flume-ui/theme/`. Also
`DESIGN_SYSTEM.md` at repo root.

- **Fonts:** **Geist** for all UI text; **JetBrains Mono** only for numerics + meta labels (timers,
  counts, UPPERCASE tags/eyebrows).
- **Base surface:** near-black (e.g. `#1a1512` / `rgba(22,20,18,…)`), light text `#f4f3f1`.
- **Accent:** `#E8522A` (orange) — used sparingly.
- **Pastel stat-card palette** (dashboard "fcards", and the auto-learn widget matches `cream`):
  - `cream` `#EADFCE` (ink `#2a1f18`) — "Words today"
  - `sage` `#DDE4D3` (ink `#1e2418`)
  - `plum` `#e6dae4` (ink `#221820`)
  - each card's icon disc = the ink color inverted (near-black bg, pastel glyph).
- **Auto-learn widget** deliberately uses the `cream` card language (cream pill, dark ink, near-black
  "Add to dictionary" button) — not orange/black — per user preference.

## Dead / legacy / inconsistent code to IGNORE

**Desktop (`whisperflow/app/`):**
- `dashboard.py` (`DashboardWindow`, ~3178 lines) — legacy AppKit dashboard, only a fallback if
  `FlumeWebDashboard` fails to construct. Superseded by the WKWebView Flume dashboard.
- `history_window.py` — legacy standalone AppKit history window; not referenced.
- `canvas_window.py` (`CanvasWindow`) — instantiated but menu routes to the web dashboard tab; effectively
  unused.
- `transcriber._transcribe_local` has an unreachable duplicate VAD `_run()` block after its `return`.
- `flume_dashboard_html.py` docstring ("pywebview window / SharedDashboard.show()") is **stale** — it's
  loaded into a WKWebView by `FlumeWebDashboard`.
- Three near-identical macOS specs (`verbal.spec`/`pico.spec`/`whisperflow.spec`) with **drifting version
  strings** (plist 1.3.0 vs 1.0.0) and slightly different `hiddenimports`; `config.APP_VERSION` is 1.0.10 —
  none match. `pico.spec` bundles `groq`+`scipy`; `verbal`/`whisperflow` bundle `pyautogui`.
- `ai_cleanup.apply_file_tags`/`FILE_TAG_PATTERNS` kept for reference/tests only — real tagging is in
  `filetags.py`.

**Mobile (`verbal-mobile/`):**
- `_old-flume/` (~27 files) — explicitly legacy.
- top-level `screens/` (empty) and `components/` (only `DeviceSelector.tsx`, imports legacy `lib/theme.ts`)
  — dead; live UI is under `flume-ui/`.
- `lib/useSync.ts` (superseded by `historyStore.ts`), `lib/useDeviceSelector.ts` (superseded by
  `flume-ui/hooks/useDevices.ts`), `lib/MarkdownText.tsx`, `lib/theme.ts` — not imported by live code.
- all `flume-ui/hooks/*.mock.ts` — contract references, never imported at runtime.
- `dist/` — stale web export.
- `flume-ui/components/ConfirmDialog.tsx` **is live** (imported directly by `useAuth`, `SettingsScreen`,
  `RootNavigator`) but intentionally **not** in the `components/index.ts` barrel.

## Verification checklist (run before considering a desktop change done)

```
cd whisperflow
.venv/bin/python -m py_compile app/<changed>.py
.venv/bin/python -c "import app.main"
# for dashboard/widget JS changes: node --check each rendered <script> block
.venv/bin/python autolearn_fixtures.py     # if autolearn touched
.venv/bin/python qa_filetags_fixtures.py    # if filetags touched
```

Mobile: `npx tsc --noEmit` in `verbal-mobile/`.

## Where the deep specs live

- `AUTOLEARN_DICTIONARY_SWARM.md` — the auto-learn feature spec (mission, algorithm, failure table, swarm).
- `FILE_TAGGING_SWARM.md` — the file-tagging feature spec.
- `GOOGLE_AUTH_SETUP.md` — auth provider setup facts (accurate table inventory).
- `DESIGN_SYSTEM.md` — design tokens.
