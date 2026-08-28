#!/usr/bin/env python3
"""Durable fixtures for `app/win_system_audio.py` (WASAPI loopback capture).

Runs ANYWHERE (Mac/Linux/Windows) — `soundcard` is replaced by an in-memory
fake installed in `sys.modules` before the module is imported, so this pins
the threading / restart / stop semantics without touching real audio:

  - RestartPolicy: bounded attempts, backoff, healthy refund, reset
  - happy path: start → 16 kHz mono callbacks → stop() < 2 s, idempotent
  - the silence player runs while capturing and is stopped with it
  - a silent endpoint (record() blocks until something plays) still stops
    deterministically BECAUSE of the silence player; without it stop() still
    returns (join timeout) and logs a warning instead of hanging
  - device fault mid-run → WARNING + reconnect on the CURRENT default device
  - persistent fault → gives up after 3 attempts, `.running=False`, `.error`
  - default-output switch (no exception) → detected by the poll → reconnect
  - no device / first segment fails → start() False, no orphan thread

Run:
    .venv/bin/python win_sysaudio_fixtures.py        (mac)
    .venv/Scripts/python.exe win_sysaudio_fixtures.py (win)
"""
from __future__ import annotations

import logging
import os
import sys
import threading
import time
import types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import numpy as np

_results = []


def record(name, passed, detail=""):
    _results.append((name, bool(passed), "" if passed else str(detail)))
    print("[%s] %s%s" % ("PASS" if passed else "FAIL", name,
                         ("  --  " + str(detail)) if (detail and not passed) else ""))


def check(name, cond, detail=""):
    record(name, bool(cond), detail)


# ── fake soundcard ─────────────────────────────────────────────────────────
class FakeSpeaker:
    def __init__(self, name, id_, channels=2):
        self.name, self.id, self.channels = name, id_, channels
        self.playing = threading.Event()   # set while a _Player is inside its `with`
        self.play_calls = 0
        self.player_fail = False

    def player(self, samplerate, channels=None, blocksize=None):
        sp = self

        class _P:
            def __enter__(s):
                if sp.player_fail:
                    raise RuntimeError("Error 0x88890004")   # AUDCLNT_E_DEVICE_INVALIDATED
                sp.playing.set()
                return s

            def __exit__(s, *a):
                sp.playing.clear()

            def play(s, data):
                sp.play_calls += 1
                time.sleep(len(data) / float(samplerate))   # render-buffer pacing
        return _P()


class FakeLoopback:
    """Recorder factory. `scenario` is a dict the tests mutate:
       fail_enter: int   raise in __enter__ this many times (counts down)
       fail_after: int   raise from record() once this many records were served
       silent:     bool  record() blocks until the paired speaker is `playing`
                         (WASAPI loopback yields nothing while nothing plays)
    """
    def __init__(self, speaker, scenario, samplerate=48000):
        self.speaker = speaker
        self.channels = speaker.channels
        self.sc = scenario
        self.rate = samplerate
        self.opened = 0
        self.closed = 0

    def recorder(self, samplerate, channels=None, blocksize=None):
        lb = self

        class _R:
            def __init__(s):
                s.n = 0

            def __enter__(s):
                if lb.sc.get("fail_enter", 0) > 0:
                    lb.sc["fail_enter"] -= 1
                    raise RuntimeError("Error 0x88890004")
                lb.opened += 1
                return s

            def __exit__(s, *a):
                lb.closed += 1

            def record(s, numframes=None):
                fa = lb.sc.get("fail_after")
                if fa is not None and s.n >= fa:
                    raise RuntimeError("Error 0x88890004")
                if lb.sc.get("silent"):
                    # Block until SOMETHING plays on the endpoint. Only the
                    # silence player can unblock us. Give up after 10 s so a
                    # broken test can't hang the harness.
                    if not lb.speaker.playing.wait(10.0):
                        return np.zeros((numframes, lb.channels), np.float32)
                time.sleep(numframes / float(samplerate))
                s.n += 1
                out = np.zeros((numframes, lb.channels), np.float32)
                out[:, 0] = 0.25
                return out
        return _R()


class FakeSC(types.ModuleType):
    def __init__(self):
        super().__init__("soundcard")
        self.speakers = {}
        self.default_id = None
        self.scenario = {}
        self.loopbacks = {}

    def add_speaker(self, name, id_, channels=2):
        sp = FakeSpeaker(name, id_, channels)
        self.speakers[id_] = sp
        self.loopbacks[id_] = FakeLoopback(sp, self.scenario)
        return sp

    def default_speaker(self):
        if self.default_id is None:
            raise RuntimeError("no default")
        return self.speakers[self.default_id]

    def get_microphone(self, id, include_loopback=False):
        for sp in self.speakers.values():
            if id in sp.name and include_loopback:
                return self.loopbacks[sp.id]
        raise IndexError("no device with id %s" % id)


fake = FakeSC()
sys.modules["soundcard"] = fake
import app.win_system_audio as wsa  # noqa: E402  (after the fake is installed)

wsa._DEVICE_POLL_S = 0.15          # keep the default-device poll fast for tests


class _LogCatcher(logging.Handler):
    def __init__(self):
        super().__init__(); self.records = []

    def emit(self, r):
        self.records.append(r)

    def has(self, level, needle):
        return any(r.levelno == level and needle in r.getMessage() for r in self.records)


logs = _LogCatcher()
wsa.logger.addHandler(logs)
wsa.logger.setLevel(logging.DEBUG)


def fresh(scenario=None, default="A"):
    fake.speakers.clear(); fake.loopbacks.clear(); fake.scenario.clear()
    if scenario:
        fake.scenario.update(scenario)
    fake.add_speaker("Speakers (Realtek)", "A")
    fake.add_speaker("Headset (USB)", "B")
    fake.default_id = default
    logs.records.clear()
    got = []
    cap = wsa.SystemAudioCapture(lambda c: got.append(c))
    cap._policy = wsa.RestartPolicy(3, 0.05, 10.0)   # fast backoff for tests
    return cap, got


def wait_for(pred, timeout=5.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if pred():
            return True
        time.sleep(0.02)
    return pred()


# ── 1. RestartPolicy (pure) ────────────────────────────────────────────────
p = wsa.RestartPolicy(3, 1.0, 10.0)
check("policy: three delays then None", [p.next_delay() for _ in range(4)] == [1.0, 1.0, 1.0, None])
check("policy: exhausted flag", p.exhausted)
check("policy: short run does not refund", p.note_healthy(9.9) is False and p.exhausted)
check("policy: healthy run refunds budget", p.note_healthy(10.0) is True and p.attempts == 0)
p.next_delay(); p.reset()
check("policy: reset", p.attempts == 0 and not p.exhausted)
check("policy: zero attempts → never retry", wsa.RestartPolicy(0).next_delay() is None)
check("policy: class defaults are 3 / 1.0 s", (wsa.SystemAudioCapture.RECONNECT_ATTEMPTS,
                                              wsa.SystemAudioCapture.RECONNECT_BACKOFF_S) == (3, 1.0))

# ── 2. happy path ──────────────────────────────────────────────────────────
cap, got = fresh()
ok = cap.start(timeout=3.0)
check("start() returns True", ok and cap.running and cap.error is None, cap.error)
wait_for(lambda: len(got) >= 5)
check("callbacks arrive", len(got) >= 5, len(got))
check("callback is float32 mono @16k (1024 frames/48k → ~341)",
      got and got[0].dtype == np.float32 and got[0].ndim == 1 and 330 <= len(got[0]) <= 350,
      (got[0].dtype, got[0].shape) if got else None)
check("level tracks audio", cap.level > 0.1, cap.level)
spA = fake.speakers["A"]
check("silence player is running while capturing", spA.playing.is_set() and spA.play_calls > 0)
t0 = time.time(); cap.stop(); dt = time.time() - t0
check("stop() < 2 s", dt < 2.0, dt)
check("stop() clears running/level", not cap.running and cap.level == 0.0)
check("silence player stopped with recorder", wait_for(lambda: not spA.playing.is_set(), 1.5))
check("recorder context closed", fake.loopbacks["A"].closed == fake.loopbacks["A"].opened == 1,
      (fake.loopbacks["A"].opened, fake.loopbacks["A"].closed))
n = len(got); time.sleep(0.15)
check("no callbacks after stop", len(got) == n)
t0 = time.time(); cap.stop(); cap.stop()
check("stop() idempotent", time.time() - t0 < 0.1 and not cap.running)
check("start() again after stop works (handle was released)", cap.start(timeout=3.0), cap.error)
cap.stop()

# ── 3. silent endpoint ─────────────────────────────────────────────────────
cap, got = fresh({"silent": True})
ok = cap.start(timeout=3.0)
check("silent endpoint: start() True (silence player unblocks record())", ok, cap.error)
wait_for(lambda: len(got) >= 2)
t0 = time.time(); cap.stop(); dt = time.time() - t0
check("silent endpoint: stop() < 2 s thanks to silence player", dt < 2.0 and not cap.running, dt)

# same, but with the silence player disabled → record() blocks; stop() must still return
cap, got = fresh({"silent": True})
_orig_start = wsa._SilencePlayer.start
wsa._SilencePlayer.start = lambda self: None
try:
    ok = cap.start(timeout=1.0)
    # The recorder context opens fine, so start() is True — the stream exists;
    # only record() then blocks forever (the pre-fix field symptom).
    check("no silence player: start() True but no callbacks arrive",
          ok and not wait_for(lambda: len(got) > 0, 0.4), (ok, len(got)))
    t0 = time.time(); cap.stop(); dt = time.time() - t0
    check("no silence player: stop() still returns ≤ 2.1 s", dt <= 2.1, dt)
    check("no silence player: stop() warns about the stuck handle",
          logs.has(logging.WARNING, "still alive after 2 s"))
finally:
    wsa._SilencePlayer.start = _orig_start
    fake.speakers["A"].playing.set()   # release the blocked fake thread

# ── 4. device fault mid-run → reconnect ───────────────────────────────────
cap, got = fresh({"fail_after": 4})
ok = cap.start(timeout=3.0)
check("fault: starts", ok, cap.error)
saw_reconnecting = wait_for(lambda: logs.has(logging.WARNING, "reconnecting (1/3)"), 3.0)
check("fault: WARNING logged with reconnecting (1/3)", saw_reconnecting)
fake.scenario.pop("fail_after")      # device is back
ok2 = wait_for(lambda: cap.running and cap.reconnects == 1, 3.0)
check("fault: capture re-opened (reconnects == 1) and running", ok2, (cap.running, cap.reconnects, cap.error))
check("fault: error cleared after successful reconnect", cap.error is None, cap.error)
n = len(got); wait_for(lambda: len(got) > n + 3)
check("fault: callbacks flow again after reconnect", len(got) > n + 3)
cap.stop()
check("fault: stop() after reconnect", not cap.running)

# ── 5. persistent fault → give up after 3 attempts ────────────────────────
cap, got = fresh({"fail_after": 2})
ok = cap.start(timeout=3.0)
gave_up = wait_for(lambda: (not cap.running) and cap.error and "gave up" in cap.error
                   and cap._thread is not None and not cap._thread.is_alive(), 5.0)
check("persistent: gives up, running=False, error explains", gave_up, (cap.running, cap.error))
check("persistent: exactly 3 reconnect attempts logged",
      logs.has(logging.WARNING, "reconnecting (3/3)") and not logs.has(logging.WARNING, "(4/3)"))
check("persistent: error names attempts + mic-only",
      "3 reconnect attempts" in (cap.error or "") and "mic-only" in (cap.error or ""), cap.error)
check("persistent: silence player torn down", not fake.speakers["A"].playing.is_set())
t0 = time.time(); cap.stop()
check("persistent: stop() after give-up is instant and clean", time.time() - t0 < 0.5 and cap._thread is None)

# ── 6. default output switched (no exception path) ────────────────────────
cap, got = fresh()
ok = cap.start(timeout=3.0)
check("switch: starts on A", ok and cap._device_id == "A")
fake.default_id = "B"
moved = wait_for(lambda: cap.running and cap._device_id == "B" and cap.reconnects == 1, 3.0)
check("switch: poll detects new default and re-opens on B", moved, (cap._device_id, cap.reconnects, cap.error))
check("switch: WARNING mentions the new device", logs.has(logging.WARNING, "default output changed"))
check("switch: A's recorder closed, B's opened",
      fake.loopbacks["A"].closed == 1 and fake.loopbacks["B"].opened == 1)
cap.stop()

# ── 7. start failures never leak a thread ─────────────────────────────────
cap, got = fresh()
fake.default_id = None
check("no default speaker: start() False + error", cap.start(timeout=1.0) is False and cap.error, cap.error)
check("no default speaker: no thread", cap._thread is None)

cap, got = fresh({"fail_enter": 1})
ok = cap.start(timeout=2.0)
check("first recorder open fails: start() False, error set", not ok and "0x88890004" in (cap.error or ""), cap.error)
time.sleep(0.3)
check("first recorder open fails: NO retry loop / orphan thread",
      cap._thread is not None and not cap._thread.is_alive() and not logs.has(logging.WARNING, "reconnecting"))
check("first recorder open fails: logged as WARNING", logs.has(logging.WARNING, "could not open loopback"))
cap.stop()

# ── 8. meetings.py surfacing contract ─────────────────────────────────────
import app.meetings as meetings  # noqa: E402
sess = object.__new__(meetings.MeetingSession)
sess._sys_cap = None
check("meetings: no sys cap → None", sess._sys_audio_state() is None)


class _Cap:
    running = True; error = None


sess._sys_cap = _Cap()
check("meetings: healthy → None", sess._sys_audio_state() is None)
_Cap.running = False; _Cap.error = "system audio lost (x) — gave up"
mlog = _LogCatcher(); meetings.logger.addHandler(mlog)
check("meetings: lost → error string", sess._sys_audio_state() == _Cap.error)
sess._sys_audio_state()
check("meetings: 'lost' logged exactly once",
      sum(1 for r in mlog.records if "system audio lost" in r.getMessage()) == 1)

# ── summary ───────────────────────────────────────────────────────────────
failed = [r for r in _results if not r[1]]
print("\n%d/%d passed" % (len(_results) - len(failed), len(_results)))
sys.exit(1 if failed else 0)
