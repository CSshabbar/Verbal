"""Pure fixtures for app/deep_link.py (runs anywhere). `python3 deep_link_fixtures.py`."""
import sys, types
sys.path.insert(0, ".")
from app import deep_link

CASES = {
    "flume://invite?t=abc.def": "abc.def",
    "flume://invite/xyz": "xyz",
    "FLUME://invite?token=q%2Fw": "q/w",
    "flume://invite?t=%20tok%20": "tok",
    "https://ovpcthjingugwvpxlsna.supabase.co/functions/v1/invite?t=tok": "tok",
    "https://idiaz.io/flume/download.html?t=tok2": "tok2",
    "flume://pair?t=x": "",          # other flume:// routes are not invites
    "verbal://team-invite?t=x": "",  # mobile scheme, not ours
    "notaurl": "", "": "", None: "", "flume://invite": "",
}

def main():
    fails = 0
    for url, want in CASES.items():
        got = deep_link.parse_invite_token(url)
        ok = got == want
        fails += 0 if ok else 1
        print(("PASS" if ok else "FAIL"), repr(url), "->", repr(got))
    # handle(): parks the token, shows the dashboard on Team, emits inviteLink; never raises
    calls = []
    class Dash:
        def show(self): calls.append("show")
        def show_tab(self, t): calls.append(("tab", t))
        def emit(self, e, p): calls.append((e, p))
    import app.config as c
    c.save_config = lambda cfg: calls.append("save")
    app = types.SimpleNamespace(config={}, dashboard=Dash())
    r = deep_link.handle(app, "flume://invite?t=T1")
    ok = r and app.config.get(deep_link.PENDING_KEY) == "T1" and "show" in calls and ("tab", "team") in calls \
        and ("inviteLink", {"token": "T1"}) in calls
    fails += 0 if ok else 1; print(("PASS" if ok else "FAIL"), "handle() parks token + drives dashboard", calls)
    class Boom:
        def show(self): raise RuntimeError("no window")
        def show_tab(self, t): raise RuntimeError("x")
        def emit(self, e, p): calls.append("emit-after-error")
    app2 = types.SimpleNamespace(config={}, dashboard=Boom())
    r2 = deep_link.handle(app2, "flume://invite?t=T2")
    ok = r2 and app2.config.get(deep_link.PENDING_KEY) == "T2" and "emit-after-error" in calls
    fails += 0 if ok else 1; print(("PASS" if ok else "FAIL"), "handle() survives a broken dashboard step")
    ok = deep_link.handle(app, "flume://pair?t=x") is False
    fails += 0 if ok else 1; print(("PASS" if ok else "FAIL"), "non-invite URL is ignored")
    print(f"total={len(CASES)+3} failed={fails} ALL_GREEN={fails==0}")
    return 0 if fails == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
