"""Pure-Python checks for app/tk_pending.PendingCalls (no tkinter needed).

Run:  cd whisperflow && python3 tk_pending_fixtures.py

Covers the bug this exists for: calls arriving before the tk root exists
must be queued in order and replayed on the tk thread once the mainloop is
up, a queued show_briefly must schedule its auto-hide relative to the replay
(not the enqueue), the queue is bounded, and close() drops everything.
"""

import sys
import os
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.tk_pending import PendingCalls  # noqa: E402

FAILS = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        FAILS.append(name)


def test_queue_then_replay_in_order():
    p = PendingCalls(name="t")
    log = []
    posted = []
    for i in range(3):
        direct = p.dispatch(lambda i=i: log.append(("q", i)), posted.append)
        check(f"early call {i} is queued, not posted", direct is False)
    check("nothing posted before ready", posted == [] and len(p) == 3)
    check("not ready before mark_ready", p.ready is False)

    n = p.mark_ready(lambda fn: fn())
    check("mark_ready replays all 3", n == 3)
    check("replay preserves FIFO order", log == [("q", 0), ("q", 1), ("q", 2)])
    check("ready after mark_ready", p.ready is True and len(p) == 0)

    direct = p.dispatch(lambda: log.append("late"), lambda fn: (posted.append(fn), fn()))
    check("after ready, dispatch posts directly", direct is True and len(posted) == 1)
    check("late call ran after replayed ones", log[-1] == "late")


def test_show_then_hide_both_replay_hide_wins():
    p = PendingCalls(name="t")
    state = {"visible": False}
    p.dispatch(lambda: state.__setitem__("visible", True), None)
    p.dispatch(lambda: state.__setitem__("visible", False), None)
    p.mark_ready(lambda fn: fn())
    check("show then hide queued -> hide wins", state["visible"] is False)


def test_show_briefly_timer_relative_to_replay():
    """The overlay queues ONE closure `(show_internal(), schedule_hide(d))`;
    the timer is armed when the closure runs, i.e. at replay time."""
    p = PendingCalls(name="t")
    clock = {"now": 0.0}
    armed_at = []

    def show_briefly(duration):
        p.dispatch(lambda: armed_at.append(clock["now"] + duration), None)

    show_briefly(2.0)            # queued at t=0
    clock["now"] = 0.7           # mainloop comes up 700 ms later
    p.mark_ready(lambda fn: fn())
    check("auto-hide armed relative to replay time, not enqueue time",
          armed_at == [2.7])


def test_bounded_queue_drops_oldest():
    p = PendingCalls(maxlen=4, name="t")
    got = []
    for i in range(10):
        p.dispatch(lambda i=i: got.append(i), None)
    check("queue is bounded", len(p) == 4)
    p.mark_ready(lambda fn: fn())
    check("oldest dropped, newest kept in order", got == [6, 7, 8, 9])


def test_replay_exception_is_contained():
    p = PendingCalls(name="t")
    got = []

    def boom():
        raise RuntimeError("tk exploded")
    p.dispatch(boom, None)
    p.dispatch(lambda: got.append("after-boom"), None)
    n = p.mark_ready(lambda fn: fn())
    check("a failing replayed item does not stop the rest", got == ["after-boom"])
    check("mark_ready counts only successful items", n == 1)


def test_close_drops_queue_and_refuses_dispatch():
    p = PendingCalls(name="t")
    got = []
    p.dispatch(lambda: got.append("x"), None)
    p.close()
    check("close() empties the queue", len(p) == 0 and p.closed)
    n = p.mark_ready(lambda fn: fn())
    check("mark_ready after close replays nothing", n == 0 and got == [])
    check("mark_ready after close does not become ready", p.ready is False)
    direct = p.dispatch(lambda: got.append("y"), lambda fn: fn())
    check("dispatch after close is a silent no-op", direct is False and got == [])


def test_close_after_ready_stops_posting():
    p = PendingCalls(name="t")
    p.mark_ready(lambda fn: fn())
    p.close()
    posted = []
    direct = p.dispatch(lambda: None, posted.append)
    check("cleanup() after ready: nothing is posted to a quitting root",
          direct is False and posted == [])


def test_thread_safety_no_lost_calls():
    """Many producer threads race mark_ready: every call must end up either
    replayed or posted, exactly once, and replayed ones come first."""
    p = PendingCalls(maxlen=100000, name="t")
    replayed, posted = [], []
    lock = threading.Lock()
    start = threading.Event()

    def producer(base):
        start.wait()
        for i in range(200):
            p.dispatch(lambda v=base + i: v,
                       lambda fn: (lock.acquire(), posted.append(fn()), lock.release()))

    threads = [threading.Thread(target=producer, args=(k * 1000,)) for k in range(8)]
    for t in threads:
        t.start()
    start.set()
    threads[0].join(timeout=0.001)          # let some calls land in the queue
    p.mark_ready(lambda fn: replayed.append(fn()))
    for t in threads:
        t.join()
    total = len(replayed) + len(posted)
    check("no call lost or duplicated across the ready flip",
          total == 8 * 200 and len(set(replayed + posted)) == total)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
    print()
    if FAILS:
        print(f"{len(FAILS)} FAILED: {FAILS}")
        sys.exit(1)
    print("ALL PASS")
