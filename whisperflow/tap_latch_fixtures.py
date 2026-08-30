#!/usr/bin/env python3
"""
Tap-to-latch — assertion harness for the HOLD-mode key state machine.

The dictation key does two jobs on one press: hold it down and it records while
held (push-to-talk); TAP it and the recording stays on hands-free until the next
tap. Before this, a tap started and stopped a recording inside a third of a
second, which `_on_record_stop` then binned as "too short" — the user-visible
"I have to be so quick about it or it stops the transcription".

The listener is driven with fake Quartz events (it only ever calls .type(),
.keyCode() and .modifierFlags()), so the real `_handle_event` runs — no logic is
duplicated here. macOS-only: `app.hotkey` imports Quartz/AppKit.

Run:
  whisperflow/.venv/bin/python tap_latch_fixtures.py

Exits 1 if any assertion fails.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from app.hotkey import HotkeyListener, TAP_LATCH_MAX_SECONDS  # noqa: E402

KEY = 54          # Right Command — the shipped default hold key
OTHER = 8         # 'c', for the Right-⌘+C chord case
ESC = 0x35

_total = 0
_failed = 0


def check(name, cond):
    global _total, _failed
    _total += 1
    if cond:
        print(f"  ok   {name}")
    else:
        _failed += 1
        print(f"  FAIL {name}")


class FakeEvent:
    """Minimal stand-in for the NSEvent the listener inspects."""

    def __init__(self, type_, keycode, flags=0):
        self._t, self._k, self._f = type_, keycode, flags

    def type(self):
        return self._t

    def keyCode(self):
        return self._k

    def modifierFlags(self):
        return self._f


class Harness:
    """A listener wired to recording call-counters, with a controllable clock."""

    def __init__(self, mode="hold"):
        self.events = []
        self.now = 1000.0
        self.listener = HotkeyListener(
            on_start=lambda: self.events.append("start"),
            on_stop=lambda: self.events.append("stop"),
            on_toggle=lambda: self.events.append("toggle"),
            on_esc=lambda: self.events.append("esc"),
            hold_key=KEY, toggle_key=KEY, mode=mode,
        )
        # Freeze time so a "tap" is deterministic rather than a race with the
        # test runner's own speed.
        import app.hotkey as _hk
        self._hk = _hk
        self._real_time = _hk.time.time
        _hk.time.time = lambda: self.now

    def restore(self):
        self._hk.time.time = self._real_time

    def press(self, keycode=KEY):
        # A modifier press arrives as FlagsChanged with the flag SET.
        flags = 0x100000 if keycode == KEY else 0
        self.listener._handle_event(FakeEvent(12 if keycode == KEY else 10, keycode, flags))

    def release(self, keycode=KEY):
        self.listener._handle_event(FakeEvent(12 if keycode == KEY else 11, keycode, 0))

    def esc(self):
        self.listener._handle_event(FakeEvent(10, ESC))

    def wait(self, seconds):
        self.now += seconds


def run(name, script, expected, mode="hold"):
    h = Harness(mode)
    try:
        script(h)
        check(f"{name}: {expected}", h.events == expected)
        if h.events != expected:
            print(f"       got {h.events}")
    finally:
        h.restore()


print("== push-to-talk still works (long press) ==")
run("hold and release",
    lambda h: (h.press(), h.wait(2.0), h.release()),
    ["start", "stop"])

run("a press just over the tap window is a hold",
    lambda h: (h.press(), h.wait(TAP_LATCH_MAX_SECONDS + 0.05), h.release()),
    ["start", "stop"])

print("\n== tap latches (the fix) ==")
run("a tap starts and KEEPS recording",
    lambda h: (h.press(), h.wait(0.15), h.release()),
    ["start"])

run("second tap stops it",
    lambda h: (h.press(), h.wait(0.15), h.release(),
               h.wait(3.0), h.press(), h.wait(0.1), h.release()),
    ["start", "stop"])

run("a press exactly at the boundary still latches",
    lambda h: (h.press(), h.wait(TAP_LATCH_MAX_SECONDS), h.release()),
    ["start"])

run("tap, then HOLD to stop also works",
    lambda h: (h.press(), h.wait(0.1), h.release(),
               h.wait(2.0), h.press(), h.wait(1.0), h.release()),
    ["start", "stop"])

run("three taps = record, stop, record",
    lambda h: (h.press(), h.wait(0.1), h.release(),
               h.wait(1.0), h.press(), h.wait(0.1), h.release(),
               h.wait(1.0), h.press(), h.wait(0.1), h.release()),
    ["start", "stop", "start"])

print("\n== chords are never dictation ==")
run("Right-Cmd + C does not latch",
    lambda h: (h.press(), h.wait(0.05), h.press(OTHER), h.release(OTHER),
               h.wait(0.05), h.release()),
    ["start", "stop"])

run("chord then a real tap still latches afterwards",
    lambda h: (h.press(), h.wait(0.05), h.press(OTHER), h.release(OTHER), h.release(),
               h.wait(1.0), h.press(), h.wait(0.1), h.release()),
    ["start", "stop", "start"])

print("\n== state can't drift ==")
run("ESC drops the latch so the next tap RECORDS (not stops)",
    lambda h: (h.press(), h.wait(0.1), h.release(),       # latched
               h.esc(),                                    # cancelled
               h.wait(1.0), h.press(), h.wait(0.1), h.release()),
    ["start", "esc", "start"])

run("clear_latch() has the same effect (the _reset_to_ready path)",
    lambda h: (h.press(), h.wait(0.1), h.release(),
               h.listener.clear_latch(),
               h.wait(1.0), h.press(), h.wait(0.1), h.release()),
    ["start", "start"])

run("switching mode drops the latch",
    lambda h: (h.press(), h.wait(0.1), h.release(),
               h.listener.set_mode("hold"),
               h.wait(1.0), h.press(), h.wait(0.1), h.release()),
    ["start", "start"])

run("a repeated key-down while held does not re-start",
    lambda h: (h.press(), h.press(), h.wait(2.0), h.release()),
    ["start", "stop"])

print("\n== TOGGLE mode is untouched ==")
run("tap toggles",
    lambda h: (h.press(), h.wait(0.1), h.release()),
    ["toggle"], mode="toggle")

run("two taps toggle twice",
    lambda h: (h.press(), h.wait(0.1), h.release(),
               h.wait(1.0), h.press(), h.wait(0.1), h.release()),
    ["toggle", "toggle"], mode="toggle")

all_green = _failed == 0
print(f"\ntotal={_total} passed={_total - _failed} failed={_failed} ALL_GREEN={all_green}")
sys.exit(0 if all_green else 1)
