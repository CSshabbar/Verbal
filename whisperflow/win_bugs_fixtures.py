#!/usr/bin/env python3
"""Durable fixtures for the 2026-08-26 Windows bug-fix pass (and the follow-up
that closed holes the first pass left in the scratchpad).

No live GUI, no network (except none — the update gate returns before httpx),
no writes to the real ~/.verbal. Safe on Windows next to the installed app.

Run:
    .venv/Scripts/python.exe win_bugs_fixtures.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

_results = []


def record(name, passed, detail=""):
    _results.append((name, bool(passed), "" if passed else str(detail)))
    tag = "PASS" if passed else "FAIL"
    line = "[%s] %s" % (tag, name)
    if detail and not passed:
        line += "  --  " + detail
    print(line)


def check(name, cond, detail=""):
    record(name, bool(cond), detail)


def _isolate_config(cfgmod, home: Path):
    home.mkdir(parents=True, exist_ok=True)
    (home / "logs").mkdir(exist_ok=True)
    cfgmod.CONFIG_DIR = home
    cfgmod.CONFIG_FILE = home / "config.json"
    cfgmod.LOG_DIR = home / "logs"
    cfgmod._last_good_json = None
    cfgmod._serving_unread_defaults = False
    cfgmod._last_tmp_sweep = 0.0


# ── 1. glibc-only strftime + untitled meeting title ──────────────────────────
def test_meeting_default_title():
    raises = False
    try:
        time.strftime("%b %-d, %H:%M")
    except ValueError:
        raises = True
    if os.name == "nt":
        check("strftime_%-d_raises_on_windows", raises,
              "Windows CRT must reject %-d so we never use it")
    else:
        check("strftime_%-d_posix_ok_or_raises", True)

    from app.meetings import MeetingSession
    s = MeetingSession(SimpleNamespace(config={}), "", use_mic=False, use_system=False)
    check("untitled_meeting_title_prefix", s.title.startswith("Meeting — "), s.title)
    check("untitled_meeting_title_no_percent", "%-" not in s.title, s.title)


# ── 2. updater 30 s gate vs force=True ───────────────────────────────────────
def test_updater_gate():
    import app.updater as updater
    sys._verbal_start_time = time.time()
    gated = updater.check_for_update(force=False)
    check("automatic_check_gated_in_first_30s", gated is None, repr(gated))
    check("updater_time_is_module_level", "time" in dir(updater),
          "download_update retry used to NameError")


# ── 3. DashboardApi update methods fail-closed without the state machine ─────
def test_update_bridge_fail_closed():
    from app.shared_dashboard import DashboardApi

    class Dash:
        app = SimpleNamespace()  # no _update_available / _phase / _progress

    r = DashboardApi(Dash()).get_update_status()
    check("get_update_status_ok_without_attrs", r.get("ok") is True, r)
    check("get_update_status_available_none", r.get("available") is None, r)
    check("get_update_status_phase_idle", r.get("phase") == "idle", r)

    class NoCheck:
        app = SimpleNamespace()  # no _check_update

    r2 = DashboardApi(NoCheck()).check_for_updates()
    check("check_for_updates_err_when_missing", r2.get("ok") is False, r2)


# ── 4. Mac/Windows tab map is one dict; popover Preferences is settings ──────
def test_dashboard_tabs():
    from app.shared_dashboard import DASHBOARD_TAB
    check("tab_3_settings", DASHBOARD_TAB.get(3) == "settings", DASHBOARD_TAB)
    check("tab_4_canvas", DASHBOARD_TAB.get(4) == "canvas", DASHBOARD_TAB)
    check("tab_5_notes", DASHBOARD_TAB.get(5) == "notes", DASHBOARD_TAB)

    from app.win_popover import _PopoverBridge

    opened = []

    class Dash:
        def show_tab(self, tab):
            opened.append(tab)

    class App:
        def __init__(self):
            self.dashboard = Dash()

        def _on_main(self, fn):
            fn()

    class Pop:
        def __init__(self, app):
            self.app = app

        def hide(self):
            opened.append("hide")

    bridge = _PopoverBridge(Pop(App()))
    bridge.open_preferences()
    check("popover_preferences_opens_settings",
          opened[:1] == ["settings"], opened)
    opened.clear()
    bridge.open_canvas()
    check("popover_canvas_opens_canvas", opened == ["canvas"], opened)


# ── 5. config: unreadable ≠ corrupt; existing .bak does not crash load ───────
def test_config_hardening():
    import app.config as cfgmod

    home = Path(tempfile.mkdtemp(prefix="flume_cfg_"))
    orig = (cfgmod.CONFIG_DIR, cfgmod.CONFIG_FILE, cfgmod.LOG_DIR,
            cfgmod._last_good_json, cfgmod._serving_unread_defaults,
            cfgmod._last_tmp_sweep)
    try:
        _isolate_config(cfgmod, home)

        cfgmod.CONFIG_FILE.write_text("{not json", encoding="utf-8")
        cfgmod.CONFIG_FILE.with_suffix(".json.bak").write_text("{}", encoding="utf-8")
        try:
            c = cfgmod.load_config()
            check("corrupt_with_existing_bak_loads", isinstance(c, dict), type(c))
        except Exception as e:
            check("corrupt_with_existing_bak_loads", False, repr(e))

        _isolate_config(cfgmod, home)
        home.mkdir(parents=True, exist_ok=True)
        c = cfgmod.load_config()
        c["sync_user_id"] = "keep-me"
        cfgmod.save_config(c)
        on_disk = cfgmod.CONFIG_FILE.read_text(encoding="utf-8")
        check("saved_user_id_roundtrip", "keep-me" in on_disk, on_disk[:200])

        cfgmod._last_good_json = None
        cfgmod._serving_unread_defaults = False
        orig_read = cfgmod._read_config_text

        def locked():
            return None, OSError(13, "Access is denied")

        cfgmod._read_config_text = locked
        try:
            d = cfgmod.load_config()
            check("unreadable_serves_defaults_flag",
                  cfgmod._serving_unread_defaults is True, cfgmod._serving_unread_defaults)
            check("unreadable_does_not_use_keep_me",
                  d.get("sync_user_id") != "keep-me", d.get("sync_user_id"))
            raised = False
            try:
                d["sync_user_id"] = "wipe"
                cfgmod.save_config(d)
            except OSError:
                raised = True
            check("save_refused_while_unread_defaults", raised)
            still = cfgmod.CONFIG_FILE.read_text(encoding="utf-8")
            check("unreadable_did_not_clobber_file", "keep-me" in still, still[:200])
        finally:
            cfgmod._read_config_text = orig_read

        _isolate_config(cfgmod, home)
        cfgmod.CONFIG_FILE.write_bytes(b"\xff\xfe torn")
        try:
            cfgmod.load_config()
            check("torn_utf8_does_not_raise", True)
        except UnicodeDecodeError as e:
            check("torn_utf8_does_not_raise", False, repr(e))
    finally:
        (cfgmod.CONFIG_DIR, cfgmod.CONFIG_FILE, cfgmod.LOG_DIR,
         cfgmod._last_good_json, cfgmod._serving_unread_defaults,
         cfgmod._last_tmp_sweep) = orig


# ── 6. Clipboard restore decision (pure — runs on any OS) ────────────────────
# app.win_injector imports ctypes.windll at module level, so the pure function is
# lifted out of the source via ast and exec'd. Keeps the test runnable on the
# macOS dev box: python3 -c "import win_bugs_fixtures as f; f.test_clipboard_restore_decision()"

def _load_should_restore_clipboard():
    import ast
    src = Path(HERE, "app", "win_injector.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "should_restore_clipboard":
            mod = ast.Module(body=[node], type_ignores=[])
            ns = {}
            exec(compile(mod, "win_injector.should_restore_clipboard", "exec"), ns)
            return ns["should_restore_clipboard"]
    raise AssertionError("should_restore_clipboard not found in app/win_injector.py")


def test_clipboard_restore_decision():
    f = _load_should_restore_clipboard()
    # (snapshot_present, current_matches_transcript, fallback, enabled) -> expected
    cases = [
        ((True,  True,  False, True),  True,  "happy path: restore"),
        ((False, True,  False, True),  False, "no snapshot (non-text/locked/empty): leave transcript"),
        ((True,  False, False, True),  False, "clipboard changed since paste: no-op"),
        ((True,  True,  True,  True),  False, "FALLBACK (paste blocked): user needs the transcript"),
        ((True,  True,  False, False), False, "config restore_clipboard=False"),
        ((False, False, True,  False), False, "everything against: no restore"),
        ((True,  False, True,  True),  False, "fallback + changed: no restore"),
        ((False, True,  True,  True),  False, "fallback wins over everything"),
    ]
    for args, expected, why in cases:
        got = f(*args)
        check("clip_restore_%s" % "_".join("1" if a else "0" for a in args),
              got is expected, "%s: got %r want %r" % (why, got, expected))

    # Module constant guard: the delayed restore must wait >= 300 ms after Ctrl+V.
    import ast, re
    src = Path(HERE, "app", "win_injector.py").read_text(encoding="utf-8")
    m = re.search(r"^CLIPBOARD_RESTORE_DELAY_S\s*=\s*([0-9.]+)", src, re.M)
    check("clip_restore_delay_constant_present", m is not None)
    check("clip_restore_delay_ge_300ms", m is not None and float(m.group(1)) >= 0.3)
    # The fallback call sites must be explicit about NOT restoring.
    check("clip_restore_fallback_explicit_in_injector",
          "fallback=False, enabled=restore_clipboard" in src
          and "deliberately NO restore" in src)
    wm = Path(HERE, "app", "win_main.py").read_text(encoding="utf-8")
    check("clip_restore_sync_receive_opts_out",
          "inject_text(text, restore_clipboard=False)" in wm)
    check("clip_restore_dictation_reads_config",
          'restore_clipboard=self.config.get("restore_clipboard", True)' in wm)
    cfg = Path(HERE, "app", "config.py").read_text(encoding="utf-8")
    check("clip_restore_config_default_true", '"restore_clipboard": True' in cfg)


def main():
    test_clipboard_restore_decision()
    test_meeting_default_title()
    test_updater_gate()
    test_update_bridge_fail_closed()
    test_dashboard_tabs()
    test_config_hardening()
    failed = sum(1 for _, ok, _ in _results if not ok)
    print("total=%d passed=%d failed=%d ALL_GREEN=%s"
          % (len(_results), len(_results) - failed, failed, failed == 0))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
