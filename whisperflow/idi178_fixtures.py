"""IDI-178 #14 — threaded proof that ESC-cancel survives the reset drain.

Models main.py's real ordering with a fake app: the ESC handler sets
`_cancel_flag` and QUEUES `_reset_to_ready` onto a UI queue; a worker thread
checks the flag only AFTER the queue has drained (the exact interleaving that
lost the cancel). Runs the same scenario against the OLD behaviour (reset
clears the flag) and the NEW one (cleared at record start instead).

Also asserts the live main.py source: `_reset_to_ready` no longer clears, and
`_on_record_start` does.
"""
import os
import queue
import re
import sys
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = HERE

fails = 0


def check(name, ok, detail=""):
    global fails
    print(("PASS " if ok else "FAIL ") + name + (("  — " + detail) if detail else ""))
    if not ok:
        fails += 1


class FakeApp:
    """The mac/win recording state machine, reduced to the flag plumbing."""

    def __init__(self, reset_clears):
        self._reset_clears = reset_clears
        self._cancel_flag = threading.Event()
        self._processing = False
        self._is_recording = False
        self._ui = queue.Queue()
        self.pasted = False

    # ── main.py equivalents ──
    def _on_main(self, fn):
        self._ui.put(fn)

    def _drain(self):
        while True:
            try:
                self._ui.get_nowait()()
            except queue.Empty:
                return

    def _on_record_start(self):
        self._is_recording = True
        self._cancel_flag.clear()          # the NEW home of the clear

    def _reset_to_ready(self):
        self._processing = False
        self._is_recording = False
        if self._reset_clears:             # the OLD (buggy) behaviour
            self._cancel_flag.clear()

    def _on_esc_pressed(self):
        if self._processing:
            self._cancel_flag.set()
            self._on_main(self._reset_to_ready)
        elif self._is_recording:
            self._on_main(self._reset_to_ready)


def scenario(reset_clears):
    """ESC during transcription; the UI queue drains BEFORE the worker's next
    cancel check. Returns True if the dictation still pasted (cancel lost)."""
    app = FakeApp(reset_clears)
    app._on_record_start()
    app._is_recording = False
    app._processing = True                 # transcription in flight

    at_check = threading.Event()
    may_check = threading.Event()

    def worker():                          # _process_audio's tail
        at_check.set()
        may_check.wait(5)
        if app._cancel_flag.is_set():
            return
        app.pasted = True

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    at_check.wait(5)                       # worker parked just before its check
    app._on_esc_pressed()                  # ESC: set flag + queue the reset
    app._drain()                           # the reset runs FIRST (the race)
    may_check.set()                        # ...now the worker checks
    t.join(5)
    return app.pasted


old_pasted = scenario(reset_clears=True)
new_pasted = scenario(reset_clears=False)
check("old behaviour reproduces the bug (cancel lost, text pasted)", old_pasted is True)
check("fixed behaviour honours the cancel (nothing pasted)", new_pasted is False)

# a cancelled dictation must not poison the NEXT one
app = FakeApp(reset_clears=False)
app._cancel_flag.set()                     # left set by the previous cancel
app._on_record_start()
check("next recording start clears the stale flag", not app._cancel_flag.is_set())

# ── source assertions against the real files ──
for name in ("main.py", "win_main.py"):
    src = open(os.path.join(ROOT, "app", name), encoding="utf-8").read()
    body = src[src.index("def _reset_to_ready"):]
    body = body[:body.index("\n    def ", 1)] if "\n    def " in body[1:] else body
    code = "\n".join(l for l in body.splitlines() if not l.strip().startswith("#"))
    check(f"{name}: _reset_to_ready no longer clears _cancel_flag",
          "_cancel_flag.clear()" not in code)
    start = src[src.index("def _on_record_start"):]
    start = start[:start.index("\n    def ", 1)]
    check(f"{name}: _on_record_start clears _cancel_flag",
          "_cancel_flag.clear()" in start)

# IDI-165 Windows leftover: overlay Cancel must be the ESC path, not `_cancel_recording`.
overlay_src = open(os.path.join(ROOT, "app", "win_overlay.py"), encoding="utf-8").read()
cancel_idx = overlay_src.find('elif name == "overlay_cancel":')
check("win_overlay.py has overlay_cancel branch", cancel_idx != -1)
if cancel_idx != -1:
    cancel_body = overlay_src[cancel_idx:cancel_idx + 900]
    check("win_overlay overlay_cancel calls _on_esc_pressed",
          "_on_esc_pressed" in cancel_body)

print(f"\nfailed={fails} ALL_GREEN={fails == 0}")
sys.exit(1 if fails else 0)
