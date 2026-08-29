"""Queue-then-replay for tkinter widgets that live on their own thread.

`WinOverlay` / `WinAutoLearnWidget` start a daemon thread that builds a
`tk.Tk()` root and runs its mainloop. Public calls (`show`, `hide`,
`show_briefly`, ...) can arrive from the hotkey / inject threads BEFORE that
root exists — a hotkey in the first ~0.5 s after launch used to record with no
pill, and its "Pasted…" toast was silently dropped, because `_safe()` early-
returned on `self._root is None`.

`PendingCalls` is the tkinter-free piece of the fix:

* `dispatch(fn, post)` — if the tk side is ready, `post(fn)` is called (the
  widget passes `root.after(0, fn)`); otherwise `fn` is queued, in order, up
  to `maxlen` entries (oldest dropped — the latest state is what matters).
* `mark_ready(run)` — MUST be called on the tk thread from inside the
  mainloop (`root.after(0, ...)` right before `root.mainloop()`). It flips
  the ready flag and hands each queued callable to `run` in FIFO order. Because
  that happens on the tk thread before control returns to the event loop,
  anything another thread posts after the flip is processed strictly after the
  replay — order is preserved without holding a lock across tk calls.
* `close()` — tear-down / setup-failed: drops the queue and refuses further
  dispatches, so a replay can never race the exit path.

Every callable is invoked inside try/except; a failing item is logged at
debug and never stops the rest (fail closed — the overlay is peripheral to the
record → transcribe → inject path).
"""

import logging
import threading
from collections import deque

logger = logging.getLogger("verbal.tk_pending")

DEFAULT_MAXLEN = 32


class PendingCalls:
    def __init__(self, maxlen=DEFAULT_MAXLEN, name="tk"):
        self._name = name
        self._lock = threading.Lock()
        self._ready = threading.Event()
        self._closed = False
        self._items = deque(maxlen=max(1, int(maxlen)))
        self._dropped = 0

    # ── state ────────────────────────────────────────────────────────────
    @property
    def ready(self):
        return self._ready.is_set() and not self._closed

    @property
    def closed(self):
        return self._closed

    def __len__(self):
        with self._lock:
            return len(self._items)

    # ── caller side ──────────────────────────────────────────────────────
    def dispatch(self, fn, post):
        """Run `post(fn)` now if ready, else queue `fn`.

        Returns True when `post` was invoked, False when queued or closed.
        `post` is called OUTSIDE the lock so a blocking cross-thread
        `root.after` can never hold up the replay.
        """
        with self._lock:
            if self._closed:
                return False
            if not self._ready.is_set():
                if len(self._items) == self._items.maxlen:
                    self._dropped += 1
                self._items.append(fn)
                return False
        try:
            post(fn)
        except Exception as e:
            logger.debug("%s pending dispatch failed: %s", self._name, e)
        return True

    # ── tk side ──────────────────────────────────────────────────────────
    def mark_ready(self, run):
        """Flip to ready and replay the queue through `run(fn)` in order.

        Call from the owning tk thread, inside the mainloop. Returns the
        number of replayed items (0 if closed).
        """
        with self._lock:
            if self._closed:
                self._items.clear()
                return 0
            items = list(self._items)
            self._items.clear()
            dropped, self._dropped = self._dropped, 0
            self._ready.set()
        if dropped:
            logger.debug("%s pending: dropped %d early call(s) (queue full)",
                         self._name, dropped)
        n = 0
        for fn in items:
            try:
                run(fn)
                n += 1
            except Exception as e:
                logger.debug("%s pending replay failed: %s", self._name, e)
        if n:
            logger.debug("%s pending: replayed %d early call(s)", self._name, n)
        return n

    def close(self):
        """Drop anything queued and refuse further dispatches (exit / setup failed)."""
        with self._lock:
            self._closed = True
            self._items.clear()
