"""Isolated live smoke test for the Windows shell (added 2026-08-26 with the
Windows bug-fix pass: updates, meeting window lifetime, quit path).

Usage (Windows, from whisperflow/):
    PYTHONUTF8=1 .venv/Scripts/python.exe scripts/win_smoke_isolated.py
Takes ~55 s, briefly shows a second tray icon and the meeting window, and ends
via os._exit(0) once every step passed — a non-zero exit, a lingering
python.exe, or a "quit_did_not_exit" step in the results means a regression.
Results: %TEMP%/flume_smoke_result.json
Isolated app log: %TEMP%/flume_smoke_home/.verbal/logs/app.log

Runs the REAL VerbalWinApp from source, in-process, but:
  * USERPROFILE is redirected to a throwaway dir BEFORE app.config is imported,
    so config/logs/recordings/meetings never touch the user's ~/.verbal (and the
    fresh config is signed out -> no Supabase session/refresh-token rotation).
  * The singleton mutex is never acquired (we do not call win_main.main()), so
    the user's installed Flume keeps running untouched — safe to run alongside it.
  * auto_update is written False into the isolated config so the update the
    check finds is never downloaded/installed by this run.
  * APP_VERSION is patched to 1.0.33 so whatever app_versions_latest currently
    holds counts as an update; the asserts below expect EXPECT_VERSION — bump
    it when a newer Windows build is published (queried live 2026-08-28:
    app_versions_latest served 1.0.38; v1.0.41 was published MID-RUN at 23:08 UTC the same day).
Results are flushed after every step because the run ends in os._exit()
(that IS one of the things under test).
"""
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import traceback

EXPECT_VERSION = "1.0.41"                 # latest published win build at the time of writing
HERE = os.path.dirname(os.path.abspath(__file__))
HOME = os.path.join(tempfile.gettempdir(), "flume_smoke_home")
shutil.rmtree(HOME, ignore_errors=True)
os.makedirs(HOME, exist_ok=True)
os.environ["USERPROFILE"] = HOME          # Path.home() / expanduser('~') on Windows
os.environ["HOMEDRIVE"], os.environ["HOMEPATH"] = os.path.splitdrive(HOME)[0], os.path.splitdrive(HOME)[1]
RESULT = os.path.join(tempfile.gettempdir(), "flume_smoke_result.json")
REPO_APP = os.path.dirname(HERE)          # whisperflow/
sys.path.insert(0, REPO_APP)
os.chdir(REPO_APP)

res = {"steps": {}, "order": []}


def record(name, ok, detail=""):
    res["steps"][name] = {"ok": bool(ok), "detail": str(detail)[:1500]}
    res["order"].append(name)
    with open(RESULT, "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1)
    print(f"[{'OK ' if ok else 'FAIL'}] {name}: {str(detail)[:300]}", flush=True)


# ── import + patch versions so 1.0.34 counts as an update ───────────────────
sys._verbal_start_time = time.time()      # keep the 30 s gate CLOSED for automatic checks
import app.config as cfgmod               # noqa: E402
assert str(cfgmod.CONFIG_DIR).lower().startswith(HOME.lower()), cfgmod.CONFIG_DIR
cfgmod.APP_VERSION = "1.0.33"
import app.updater as updater             # noqa: E402
updater.APP_VERSION = "1.0.33"
from app import win_main                  # noqa: E402
win_main.APP_VERSION = "1.0.33"
import app.shared_dashboard as sd         # noqa: E402
sd.APP_VERSION = "1.0.33"
record("isolation", True, f"CONFIG_DIR={cfgmod.CONFIG_DIR} LOG_DIR={cfgmod.LOG_DIR}")

# Isolated config: signed out, no auto-install, no dashboard auto-open.
c = cfgmod.load_config()
c["auto_update"] = False
c["open_dashboard_on_launch"] = False
c["sync_enabled"] = False
cfgmod.save_config(c)

appobj = win_main.VerbalWinApp()
assert appobj.config.get("auto_update") is False
record("construct", True, "VerbalWinApp constructed; auto_update=False; updater has time module: %s"
       % ("time" in dir(updater)))


def alive(mw):
    try:
        return bool(mw and mw._window_alive())
    except Exception as e:
        return f"err {e}"


def scenario():
    try:
        time.sleep(8)
        # 1) update check: automatic path must still be gated, forced path must find 1.0.34
        gated = updater.check_for_update()
        appobj._check_update(force=True)
        av = appobj._update_available
        api = sd.DashboardApi(appobj.dashboard)
        st = api.get_update_status()
        ok = (gated is None and isinstance(av, dict) and av.get("version") == EXPECT_VERSION
              and st.get("ok") and (st.get("available") or {}).get("version") == EXPECT_VERSION
              and st.get("phase") == "idle" and st.get("current_version") == "1.0.33"
              and appobj._pending_update is av)
        record("update_check", ok, f"gated={gated} available={av and av.get('version')} status={st}")
        r2 = api.check_for_updates()
        record("dashboard_check_button", r2.get("ok") and r2.get("available") and r2.get("version") == EXPECT_VERSION, r2)

        # 2) meeting window: show
        appobj._toggle_meeting()
        time.sleep(6)
        mw = appobj.meeting_window
        record("meeting_show_1", mw is not None and mw.visible and alive(mw) is True,
               f"visible={getattr(mw,'visible',None)} alive={alive(mw)}")

        # 2b) layout smoke (2026-08-28 report: collapsed bar rendered as a
        # full titled window). Native form props report PHYSICAL px (rule
        # #42), so expectations scale logical constants by the window's own
        # DPI scale. Reading Width/etc. off-thread is tolerable for a smoke
        # check (plain field reads; no message-pump interaction).
        def native_geom():
            form = mw._window.native
            return (int(form.Width), int(form.Height),
                    str(form.FormBorderStyle), bool(form.TopMost),
                    str(form.WindowState))

        s = mw._dpi_scale()
        tol = int(round(8 * s))                 # ±8 LOGICAL px, in physical

        def near(v, logical):
            return abs(v - round(logical * s)) <= tol

        mw.set_layout("bar")
        time.sleep(2)
        w_, h_, border, topmost, state = native_geom()
        # .NET Enum.ToString() gives the bare member name; pywebview-side str()
        # may prefix the type — accept both.
        ok = (near(h_, 54) and near(w_, 560)
              and border.endswith("None") and topmost)
        record("bar_layout", ok,
               f"phys={w_}x{h_} scale={s} border={border} topmost={topmost} state={state}")

        mw.set_layout("expanded")
        time.sleep(2)
        w_, h_, border, topmost, state = native_geom()
        # expanded is user-resizable, so assert the MIN_W/MIN_H floor
        # (700x480 logical) rather than exact WIN_WxWIN_H.
        ok = (w_ >= round(700 * s) - tol and h_ >= round(480 * s) - tol
              and border.endswith("Sizable") and not topmost)
        record("expand_restore", ok,
               f"phys={w_}x{h_} scale={s} border={border} topmost={topmost} state={state}")

        # 2c) minimize mid-meeting collapses to the bar (2026-08-28 report).
        # _on_native_resize keys on app.meetings.active/.processing — pure
        # properties over meetings.session.state, so a stub namespace with
        # state="recording" simulates a live meeting WITHOUT any audio
        # capture or a real MeetingSession. Nothing else consumes the stub in
        # this window: HUD pushes and _toggle_meeting/_sign_out are not
        # exercised while it is set, and it is cleared in the finally.
        if appobj.meetings is None or not hasattr(mw, "_on_native_resize"):
            record("minimize_to_bar", True,
                   "skipped: minimize interception not wired on this build")
        else:
            import types as _types
            appobj.meetings.session = _types.SimpleNamespace(
                state="recording", title="Smoke")
            try:
                def _minimize():
                    import System.Windows.Forms as WinForms
                    mw._window.native.WindowState = \
                        WinForms.FormWindowState.Minimized
                invoked = mw._apply_native(_minimize)   # UI-thread hop
                time.sleep(3)   # inline collapse + deferred set_layout('bar')
                w_, h_, border, topmost, state = native_geom()
                ok = (invoked and mw._layout == "bar"
                      and state.endswith("Normal")      # un-minimized again
                      and near(h_, 54) and near(w_, 560)
                      and border.endswith("None") and topmost)
                record("minimize_to_bar", ok,
                       f"invoked={invoked} layout={mw._layout} state={state} "
                       f"phys={w_}x{h_} border={border} topmost={topmost}")
            finally:
                appobj.meetings.session = None          # drop the stub
            mw.set_layout("expanded")   # restore for the close-X step below
            time.sleep(2)

        # 2d) Windows builds must not leak Mac-only wording/glyphs
        # (2026-08-28 report). flume_html() legitimately contains '⌘' inside
        # runtime-guarded JS ternaries (IS_WINDOWS?'Ctrl+V':'⌘V') that never
        # render on Windows — exempt exactly those, flag any other '⌘'.
        from app.flume_dashboard_html import flume_html
        from app.meeting_html import meeting_html
        fh, mh = flume_html(), meeting_html()
        fh_guarded = fh.replace("IS_WINDOWS?'Ctrl+V':'⌘V'", "")
        ok = ("This PC" in fh and "This Mac" not in fh
              and "⌘" not in fh_guarded
              and "Ctrl+." in mh and "⌘" not in mh)
        record("rendered_strings", ok,
               f"pc={'This PC' in fh} mac={'This Mac' in fh} "
               f"flume_cmd_unguarded={fh_guarded.count(chr(0x2318))} "
               f"meet_ctrl={'Ctrl+.' in mh} meet_cmd={mh.count(chr(0x2318))}")

        # 3) user presses X: Form.Close() on the UI thread == CloseReason.UserClosing
        mw._window.destroy()          # pywebview routes this through FormClosing -> our _on_closing veto
        time.sleep(3)
        record("meeting_close_x", alive(mw) is True and not mw.visible and mw._window is not None,
               f"alive={alive(mw)} visible={mw.visible} window={mw._window is not None} destroying={mw._destroying}")

        # 4) Start meeting again -> must re-show (the user's reported bug)
        appobj._toggle_meeting()
        time.sleep(5)
        record("meeting_show_2", mw.visible and alive(mw) is True, f"visible={mw.visible} alive={alive(mw)}")

        # 5) blank-title meeting must not raise on Windows
        from app.meetings import MeetingSession
        s = MeetingSession(appobj, "", use_mic=False, use_system=False)
        record("default_title", s.title.startswith("Meeting"), s.title)

        # 6) programmatic destroy -> closed handler drops the handle -> next show rebuilds
        mw.destroy()
        time.sleep(3)
        dropped = mw._window is None
        appobj._toggle_meeting()
        time.sleep(6)
        record("meeting_rebuild_after_destroy", dropped and mw.visible and alive(mw) is True,
               f"dropped={dropped} visible={mw.visible} alive={alive(mw)}")
        mw.hide()

        # 6b) dashboard X DESTROYS the form (unlike meeting, which hides).
        # show() on a dead uid is a silent no-op — same class of bug as Start
        # meeting. Next Open Dashboard must rebuild.
        dash = appobj.dashboard
        dash.show()
        time.sleep(6)
        d_alive = bool(dash._window is not None and dash._window_alive())
        record("dashboard_show_1", d_alive,
               f"window={dash._window is not None} alive={dash._window_alive() if dash._window else None}")
        if dash._window is not None:
            dash._window.destroy()
        time.sleep(3)
        gone = dash._window is None or not dash._window_alive()
        dash.show()
        time.sleep(5)
        record("dashboard_rebuild", gone and dash._window is not None and dash._window_alive(),
               f"gone={gone} window={dash._window is not None} alive={dash._window_alive() if dash._window else None}")
        try:
            if dash._window is not None:
                dash._window.hide()
        except Exception:
            pass

        # 7) quit: must exit the process (os._exit) within ~2 s and leave no ghost
        record("quit_requested", True, "calling _tray_quit from a worker thread")
        appobj._tray_quit()
        time.sleep(5)
        record("quit_did_not_exit", False, "process still alive 5 s after _tray_quit")
    except Exception:
        record("scenario_exception", False, traceback.format_exc())
        try:
            appobj._hard_exit("smoke test failure")
        except Exception:
            os._exit(3)


threading.Thread(target=scenario, name="smoke-scenario", daemon=True).start()
appobj.start()      # blocks in webview.start(); the scenario thread ends the process
record("start_returned", False, "appobj.start() returned instead of the process exiting")
