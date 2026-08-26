# Handoff — Windows bug-fix pass (branch `windows-bugs`, 2026-08-26)

> For the next agent or engineer picking this up. Everything below is verified against the
> code as of commit `fa282d0` (+ the tooling commit that follows it). Read `context/` first
> (`CLAUDE.md` rule); the rules this pass added are `context/05-conventions.md` #67–#69 and the
> extensions to #3 and #59b.

## 1. State of the branch

| | |
|---|---|
| Branch | `windows-bugs`, cut from `origin/dev` @ `d01ebc1` (= desktop **v1.0.34**) |
| Commits | `fa282d0` — the five fixes + `context/` sync; then the tooling/handoff commit |
| Pushed? | **No.** Nothing has left this machine. `git push -u origin windows-bugs` when ready. |
| Merging | `dev` is watched by `.github/workflows/auto-release-desktop.yml` (path filter `whisperflow/**`) → it auto-bumps `config.APP_VERSION`, tags, and `build-release.yml` ships **mac + win together**. Merging this = a release (would become 1.0.35). |
| Working tree | clean after the tooling commit |
| User's machine | Installed Flume **1.0.33** is still running (two `Flume.exe` — see §3.3). It was **not** stopped or upgraded by this work. |

Files touched (13 + tooling): `whisperflow/app/{win_main, shared_dashboard, updater, main, meetings, win_meeting_window, win_popover, flume_dashboard_html, config}.py`, `whisperflow/team_dashboard_fixtures.js`, `context/{02-architecture,03-features,05-conventions}.md`, plus new `whisperflow/scripts/{js_check,win_smoke_isolated}.py`.

## 2. The user's report (screenshots + text), verbatim intent

1. Home card **"Start meeting"** and Meetings **"New meeting"** — "not working" / "does not work".
2. Notes Studio — "align these icons" (the 2×2 pastel cards).
3. Running 1.0.33, 1.0.34 is published, **Settings → Check for updates does not pull it**.
4. Closing the program **doesn't quit**; it stays in Task Manager; **End task leaves it lurking** until killed.
5. "Spin up multiple agents and properly test it, fix any bugs and make it uniform … production ready."

## 3. Root causes → fixes (with pointers)

### 3.1 Updates never found on Windows
- **Cause A** — `win_main._check_update` ran once at t=0 behind a once-per-session flag, and `updater.check_for_update()` returns `None` for the first 30 s after launch (`sys._verbal_start_time` gate, set only on Windows). Net: **no Windows session ever really checked**.
- **Cause B** — the shared `DashboardApi` (`shared_dashboard.py`) read Mac-only attributes (`_update_available/_update_phase/_update_progress`) and called `_check_update(suppress_prompt=True)` → `AttributeError` every 30 s poll (visible in `~/.verbal/logs/app.log`) and a silent `TypeError` on the button.
- **Fix** — `win_main.py`: full port of the Mac update state machine (`_update_available/_phase/_progress/_ready_path`, `_pending_update` is now a property alias for the tray badge/menu code, `_update_check_loop` = 35 s delay then every 4 h, `_start_update_download`, `_install_ready_update`, `_download_and_install` for `auto_update` mode which now **waits for an idle app** (`_app_busy`) before the installer's `os._exit`, single-flight lock, supersede hand-off, new tray row **"Check for updates..."**). `updater.check_for_update(force=False)` — `force=True` skips the 30 s gate for explicit clicks; also fixed a latent `NameError` (`time` was not imported at module level in `download_update`'s retry). `shared_dashboard.DashboardApi`: all four update methods are `getattr`-fail-closed; `check_for_updates` is now **synchronous (≤ 8 s)** and returns `{available, version}`; `flume_dashboard_html.py::checkForUpdatesNow` acts on that reply instead of a 1.5 s timer. `main.py`: `_check_update(..., force=False)` signature + menubar "Check for Updates…" passes `force=True` (small, deliberate mac delta: a click within 30 s of launch now works).

### 3.2 Start meeting / New meeting dead
- **Cause A** — `meetings.py:716` default title used `strftime('%b %-d, %H:%M')`; `%-d` is glibc-only → Windows CRT `ValueError: Invalid format string` → "manager start failed" for any **untitled** meeting (seen twice in the log). Fixed with `tm_mday`. Only occurrence in `app/*.py`.
- **Cause B** — `WinMeetingWindow` created a titled pywebview window with **no `closing`/`closed` handlers**. X destroyed the WinForms form; Python kept the dead handle; `show()` was a silent no-op forever (log showed `meeting open: ready=True` on every click, no window).
- **Fix** — `win_meeting_window.py` + `win_popover.py`: `events.closing` → hide + cancel (**UserClosing only** — a native `FormClosing` handler attached after pywebview's un-cancels `WindowsShutDown / TaskManagerClosing / ApplicationExitCall`, otherwise Flume would block Windows shutdown); `events.closed` → drop the handle so the next `show()` rebuilds; `_window_alive()` check; `_wait_shown()` bounds pywebview's 20 s `_shown_call` blocks to 5 s; `_visible=True` is set **before** `.show()` (fixes a race with `_on_loaded` hiding a just-shown window); `destroy()` sets `_destroying` for programmatic teardown; `_on_closing` also lets the close through when `app._exiting` is set.

### 3.3 Lurking process
- **Cause** — the Windows build is PyInstaller **one-file** (`verbal-win.spec`: `EXE(...)` with no `COLLECT`). Every launch is a 9 MB bootloader parent + a ~320 MB child (confirmed live: PID 64616 → 62104). Task Manager "End task" on the parent orphans the child, which still holds `VerbalSingletonMutex_v1`, so the next launch just signals it and exits. (Separately, 1.0.33's tray Quit used `sys.exit` on the tray thread — already fixed in `9a453cb`/1.0.34.)
- **Fix** — `win_main.py`: `_watch_bootloader_parent(on_parent_exit)` — armed **only** when frozen **and** the layout is one-file (`sys._MEIPASS` exists and lies outside the exe dir — guards against a future onedir build where the elevated relaunch's parent is also `Flume.exe`), parent exe path == `sys.executable`, PID-reuse guarded via `GetProcessTimes`; waits on the parent handle and calls `_hard_exit`. `_tray_quit` → shared `_hard_exit(reason)`: re-entrant, hides the tray icon **synchronously** (`icon.visible = False` — `stop()` alone leaves a ghost icon when `os._exit` follows on the pystray thread), runs webview-destroy in a daemon thread joined for 1 s (pywebview's destroy is a sync `Control.Invoke`; a stalled GUI thread must not stop us reaching `os._exit`), then `logging.shutdown()` + `os._exit(0)`. `shared_dashboard.py`: one-time toast on first X of the dashboard (config key `tray_close_hint_shown`) — "Flume keeps running in the tray".

### 3.4 Studio cards
- **Cause** — `.scard .sdisc{margin-bottom:auto}` bottom-anchored title+description, so a two-line description ("Markdown, text, clipboard") shifted the title; the Export card sat in a `display:block` wrapper with `height:100%`; Notes used `<div class="nmenuwrap">`, Meetings `<span>`.
- **Fix** — `flume_dashboard_html.py` CSS (~L696–716, all scoped under `.scards` so the **older Settings `.scard` rules at ~L491–520 are untouched**): `align-items:stretch`, wrapper is a flex column, `.scards .scard{min-height:108px; justify-content:flex-start}`, `.sdisc{margin-bottom:0}`, `.ss{min-height:calc(2*1.35em)}`; Meetings wrapper is now a `<div>`. Verified by headless Edge render: all 8 cards 108.34 px, discs/titles on identical baselines per row.

### 3.5 (found in the log) `config.json` WinError 5 / 183 spam — a real data-loss path
- `.bak` was created with `os.rename` (fails if `.bak` exists → 183); a **locked** file (AV/indexer, WinError 5) was treated as *corrupt* → moved aside → **reset to defaults and saved** (session/history gone).
- **Fix** — `config.py`: `.bak` via `os.replace`; retryable-lock detection + 20→320 ms backoff; in-place fallback write with a `.prev` snapshot; **unreadable ≠ corrupt** (serve in-memory copy / defaults **without persisting**, and `save_config` raises `OSError(EACCES)` while `_serving_unread_defaults` so a caller can't write defaults over the real file); decode bytes inside the corrupt handler (a torn UTF-8 file used to raise `UnicodeDecodeError` out of `load_config`); stale `.config-*.tmp` sweep; `deepcopy` of defaults.

## 4. How it was verified (all green at `fa282d0`)

```
cd whisperflow
.venv/Scripts/python.exe -m py_compile app/<changed>.py
.venv/Scripts/python.exe -c "import app.win_main, app.shared_dashboard, app.win_meeting_window, app.win_popover, app.meetings, app.updater, app.config"
.venv/Scripts/python.exe -c "import ast; ast.parse(open('app/main.py',encoding='utf-8').read())"   # main.py needs rumps — cannot import on Windows
.venv/Scripts/python.exe scripts/js_check.py          # node --check on every rendered <script> block: 6/6
node team_dashboard_fixtures.js                        # 93/93 (runner now cross-platform)
.venv/Scripts/python.exe notes_fixtures.py             # 66/66
.venv/Scripts/python.exe meeting_detect_fixtures.py    # 24/24
PYTHONUTF8=1 .venv/Scripts/python.exe scripts/win_smoke_isolated.py   # 10/10, exit 0, nothing lingering
```

`scripts/win_smoke_isolated.py` runs the **real `VerbalWinApp` from source** with `USERPROFILE` pointed at `%TEMP%/flume_smoke_home` (so it never touches `~/.verbal`, is signed out, and cannot rotate the user's Supabase refresh token), never takes the singleton mutex (safe alongside the installed app), `APP_VERSION` patched to 1.0.33, `auto_update=False`. Steps: forced check finds 1.0.34 while the gated automatic check stays `None`; `DashboardApi.get_update_status`/`check_for_updates` correct; meeting window show → X (via `destroy()`, which pywebview routes through `FormClosing` = `UserClosing`) → still alive & hidden → show again → blank-title `MeetingSession` constructs → programmatic `destroy()` drops the handle → rebuild → `_tray_quit()` from a worker thread ends the process. Bump `EXPECT_VERSION` in it when a newer win build is published.

Also run during the pass: a mocked state-machine test of the update flow (11 scenarios) and a config stress test (8 writer threads vs. an external reader, corrupt/locked/torn-file recovery) — both lived in the session scratchpad and are **not** in the repo; the smoke harness and `js_check.py` are.

Review process: 10 adversarial reviewers (correctness + Windows-runtime lens per area) produced 20 findings; **7 majors, all confirmed real and fixed** (UTF-8 crash, defaults-over-real-config, `_hard_exit` could hang before `os._exit`, close-veto blocked Windows shutdown ×2, silent auto-install mid-dictation, updater `NameError`, onedir false-positive in the parent watcher). Minor deliberately **not** applied: `save_config` retry backoff can add up to ~1.2 s on the transcribe→inject path if an external handle holds `config.json` — the only hot-path save is `transcriber.remember_files` (flag-gated); the right fix is to schedule that save off the inject path in `transcriber.py`, not in `config.py`.

## 5. NOT done / needs a frozen build or a human

1. **onedir build (the structural fix for §3.3).** `verbal-win.spec` → add `COLLECT(...)`; `verbal-setup.iss` `[Files]` `Source: "dist\Flume\*"; Flags: recursesubdirs` (currently `dist\Flume.exe`); CI's PyInstaller/ISCC steps in `.github/workflows/build-release.yml` (~L87, L107, L116) reference `dist/FlumeSetup.exe` — unchanged, but check the artifact path. Win: no bootloader parent, no per-launch extraction of ~600 MB to `%TEMP%` (faster startup). The parent watcher already disarms itself under onedir. Needs a real build + install test.
2. **Frozen-build tests nobody could run here** (the live smoke test needed `taskkill` on the user's app, which the harness policy blocked; the isolated harness covers the source-level paths): (a) End task on the 9 MB `Flume.exe` parent → child gone within ~1 s, no ghost tray icon; (b) tray **Quit** → process gone, no ghost icon; (c) Windows **shut down / sign out** with the meeting window or popover built → no "Flume is preventing you from shutting down" screen (expect log `close reason WindowsShutDown -- allowing destroy`); (d) real 1.0.33 → new build: banner appears ~35 s after launch; Settings button works immediately; **Update → Restart to update** installs and relaunches; (e) `auto_update` (default **True**, no Windows UI toggle) silently installs only when idle.
3. **The user's installed 1.0.33 cannot self-update** — that is the bug. After the next release, install it **once by hand** (`supabase/functions/download?platform=win` → GitHub Release asset); from then on the in-app flow works.
4. `windows_specs/`, `WINDOWS_PARITY_PLAN.md`: unchanged; still the spec for the remaining native workstreams.

## 6. Gotchas learned (so you don't relearn them)

- **Do not `import app.main` on Windows** (rumps/AppKit) — `ast.parse` it. `import app.win_main` is the Windows import check.
- The `team_dashboard_fixtures.js` runner hardcoded `.venv/bin/python` and needed `PYTHONUTF8=1` — fixed in this pass; the checklist in `context/05` now has the Windows line.
- pywebview facts (5.x, read `.venv/Lib/site-packages/webview/platforms/winforms.py`): `closing` handlers run **synchronously on the WinForms UI thread**; any handler returning `False` sets `args.Cancel` — with **no `CloseReason` exposed**, hence the native `FormClosing` handler; `show()` on a dead uid **does not raise**, it silently returns; `show/hide/destroy/resize` are `_shown_call` = block up to 20 s then `WebViewException`; `evaluate_js` inside a closing handler **deadlocks**; `create_window` on a running loop is synchronous via `Invoke`, so `window.native` is valid on return.
- pystray: `icon.stop()` only posts `WM_STOP`; the `NIM_DELETE` happens when the loop drains — which `os._exit` on that same thread prevents. `icon.visible = False` is the synchronous hide.
- `Path.home()`/`expanduser('~')` on Windows follow **`USERPROFILE`** (not `HOME`) — that is how the smoke harness isolates state; the repo's `idi170_171_fixtures.py`/`idi172_174_fixtures.py` set `HOME` and are therefore **not safe to run on Windows** (they would hit the real `~/.verbal`).
- `%-d`-style `strftime` directives raise on Windows — rule #68.
- Git on this box rewrites LF→CRLF on touch (the warnings are noise); files were kept LF.
- Workflow note: agents editing the same file must be sequenced (updates → quit both owned `win_main.py`); one agent stalled and was auto-retried — check `journal.jsonl` before assuming a result is missing.

## 7. Suggested order for whoever continues

1. `git push -u origin windows-bugs`, open PR → `dev`; CI builds mac+win.
2. Install the resulting win build on the user's box by hand (once); run §5.2 (a)–(e) against it.
3. If (a)–(e) pass, schedule the onedir change (§5.1) as its own PR — it is a packaging change, keep it separate from behaviour fixes.
4. Optionally move `transcriber.remember_files`' `save_config` off the inject path (see §4 minor).
