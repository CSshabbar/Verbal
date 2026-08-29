"""Stress fixture for config.py's lock discipline (rule #3 / 2026-08-28 fix).

Run:  cd whisperflow && .venv/bin/python config_lock_fixtures.py   (needs python-dotenv)

What it checks
  * CONFIG_DIR / CONFIG_FILE are redirected to a throwaway temp dir BEFORE any
    load/save happens, so the real ~/.verbal is never touched.
  * 8 writer threads each own a distinct key and, for ~2 s, do
        load_config() -> bump my key -> save_config()
    while holding `config._config_lock` across the three steps (the RLock is
    the documented way for a caller to make read->modify->write atomic; the
    nested load_config/save_config lock acquisitions must not deadlock).
  * A "loader" thread hammers plain load_config() and, via a sentinel added to
    DEFAULT_CONFIG that the writers keep deleting from disk, is forced down the
    `changed -> save_config` path on every call. Before the fix that save ran
    AFTER load_config had released the lock, so it could overwrite a writer's
    save that landed in the gap (lost update). Now it is inside the same
    critical section, so no writer increment may ever be lost.
  * A reader thread verifies every load_config() result is a dict with all
    writer keys monotonically non-decreasing.
  * Finally the on-disk JSON must parse and each key must equal the number of
    successful saves that writer made.

Exit code 0 = all passed, 1 = a check failed.
"""
import copy
import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import app.config as cfg  # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="flume-cfglock-"))
cfg.CONFIG_DIR = TMP / ".verbal"
cfg.CONFIG_FILE = cfg.CONFIG_DIR / "config.json"
cfg.LOG_DIR = cfg.CONFIG_DIR / "logs"
cfg.ENV_FILE = TMP / "no.env"          # keep the real .env's GEMINI_API_KEY out
os.environ.pop("GEMINI_API_KEY", None)

SENTINEL = "__lock_fixture_sentinel__"
cfg.DEFAULT_CONFIG = copy.deepcopy(cfg.DEFAULT_CONFIG)
cfg.DEFAULT_CONFIG[SENTINEL] = True    # forces load_config's persist path

N_WRITERS = 8
DURATION = 2.0
results = []


def check(name, ok, detail=""):
    results.append((name, ok, detail))
    print(("PASS " if ok else "FAIL ") + name + (("  -- " + detail) if detail else ""))


assert isinstance(cfg._config_lock, type(threading.RLock())), "_config_lock must be an RLock"

# Seed the file.
cfg.save_config({**copy.deepcopy(cfg.DEFAULT_CONFIG), **{f"w{i}": 0 for i in range(N_WRITERS)}})

stop = threading.Event()
saves = [0] * N_WRITERS
errors = []
loader_calls = [0]
reader_calls = [0]
reader_regressions = []


def writer(i):
    key = f"w{i}"
    while not stop.is_set():
        try:
            with cfg._config_lock:
                c = cfg.load_config()
                c[key] = c.get(key, 0) + 1
                c.pop(SENTINEL, None)      # re-arm the loader's migration path
                cfg.save_config(c)
                saves[i] += 1
        except Exception as e:  # noqa: BLE001
            errors.append(("writer", i, repr(e)))
        # Yield between iterations: a thread re-taking an RLock in a tight loop
        # starves everyone else on macOS (unfair handoff), which turns the test
        # into one writer + idle bystanders instead of real contention.
        time.sleep(0.001)


def loader():
    while not stop.is_set():
        try:
            c = cfg.load_config()          # takes the changed->save path when SENTINEL is missing
            loader_calls[0] += 1
            if SENTINEL not in c:
                errors.append(("loader", "sentinel missing after load", None))
        except Exception as e:  # noqa: BLE001
            errors.append(("loader", repr(e), None))


def reader():
    last = [0] * N_WRITERS
    while not stop.is_set():
        try:
            c = cfg.load_config()
            reader_calls[0] += 1
            if not isinstance(c, dict):
                reader_regressions.append("non-dict")
                continue
            for i in range(N_WRITERS):
                v = c.get(f"w{i}", 0)
                if v < last[i]:
                    reader_regressions.append(f"w{i} went {last[i]}->{v}")
                last[i] = v
        except Exception as e:  # noqa: BLE001
            errors.append(("reader", repr(e), None))


threads = [threading.Thread(target=writer, args=(i,), daemon=True) for i in range(N_WRITERS)]
threads += [threading.Thread(target=loader, daemon=True), threading.Thread(target=reader, daemon=True)]
t0 = time.time()
for t in threads:
    t.start()
time.sleep(DURATION)
stop.set()
for t in threads:
    t.join(timeout=10)
elapsed = time.time() - t0

check("all threads finished (no deadlock)", all(not t.is_alive() for t in threads))
check("no exceptions", not errors, repr(errors[:5]))

raw = cfg.CONFIG_FILE.read_bytes()
try:
    final = json.loads(raw.decode("utf-8"))
    check("final config.json parses", isinstance(final, dict))
except Exception as e:  # noqa: BLE001
    final = {}
    check("final config.json parses", False, repr(e))

lost = {f"w{i}": (saves[i], final.get(f"w{i}")) for i in range(N_WRITERS) if final.get(f"w{i}") != saves[i]}
check("no lost writer updates", not lost, f"expected==on-disk per key; mismatches: {lost}")
check("writers actually contended", sum(saves) > 50 and min(saves) > 0, f"saves per writer={saves}")
check("loader took the persist path", loader_calls[0] > 10, f"loader_calls={loader_calls[0]}")
check("reader saw monotonic keys", not reader_regressions, repr(reader_regressions[:5]))
check("no temp litter left", not list(cfg.CONFIG_DIR.glob(".config-*.tmp")))
check("UNREAD_DEFAULTS_KEY never persisted", cfg.UNREAD_DEFAULTS_KEY not in final)

print(f"\n{elapsed:.1f}s  writer saves={sum(saves)}  loader loads={loader_calls[0]}  reader loads={reader_calls[0]}  dir={TMP}")
failed = [r for r in results if not r[1]]
print(f"{len(results) - len(failed)}/{len(results)} checks passed")
sys.exit(1 if failed else 0)
