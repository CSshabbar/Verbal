"""Fixture checks for app/insights.py — the Insights page's data layer.

Run:  .venv/bin/python insights_fixtures.py

Pins the load-bearing behaviours:
  1. record_dictation accumulates words/count/seconds/fx/apps and stats_total.
  2. Streaks: the current run may end today OR yesterday; best is all-time.
  3. The cloud merge rule combines ledger + cloud days without double counting.
  4. The WPM→"Top X% of typists" mapping stays monotonic and sane.
  5. polish_delta counts changed words and is 0 on identical/empty input.
  6. compute() and record_dictation() are fail-closed (Hard Rule #1).
"""
from datetime import date, timedelta

from app import insights

PASS = 0


def ok(cond, label):
    global PASS
    assert cond, label
    PASS += 1
    print(f"  ok — {label}")


def main():
    cfg = {}
    saves = {"n": 0}

    def save(c):
        saves["n"] += 1

    # 1. accumulation
    insights.record_dictation(cfg, save, 42, seconds=18.0, app_name="Cursor", fx_words=3)
    insights.record_dictation(cfg, save, 20, seconds=8.0, app_name="Slack")
    t = str(date.today())
    d = cfg["stats_daily"][t]
    ok(d["w"] == 62 and d["n"] == 2 and abs(d["s"] - 26.0) < 0.01 and d["fx"] == 3,
       "ledger accumulates words/count/seconds/fx")
    ok(cfg["stats_total"]["w"] == 62 and cfg["stats_since"] == t,
       "lifetime totals + stats_since stamped")
    ok(d["apps"] == {"Cursor": [42, 1], "Slack": [20, 1]},
       "per-app words + dictation counts recorded")

    # 1b. legacy first-build shape (bare int) upgrades in place on next write
    cfg["stats_daily"][t]["apps"]["Cursor"] = 42          # simulate old data
    insights.record_dictation(cfg, save, 8, seconds=3.0, app_name="Cursor")
    ok(cfg["stats_daily"][t]["apps"]["Cursor"] == [50, 1],
       "legacy int app value upgrades to [w, n]")
    cfg["stats_daily"][t]["w"] -= 8                        # undo for later spans
    cfg["stats_total"]["w"] -= 8

    # 2. streaks
    for i in (1, 2, 3):
        cfg["stats_daily"][str(date.today() - timedelta(days=i))] = {
            "w": 10, "n": 1, "s": 5.0, "fx": 0, "apps": {}, "hh": {}}
    for i in range(50, 55):
        cfg["stats_daily"][str(date.today() - timedelta(days=i))] = {
            "w": 10, "n": 1, "s": 5.0, "fx": 0, "apps": {}, "hh": {}}
    p = insights.compute(cfg)
    ok(p["current_streak"] == 4, "current streak includes today + run")
    ok(p["best_streak"] == 5, "best streak found in older history")

    # 2b. per-app stats: 30-day and all-time windows, count/avg, legacy tolerance
    old_day = str(date.today() - timedelta(days=90))
    cfg["stats_daily"][old_day] = {"w": 30, "n": 1, "s": 10.0, "fx": 0,
                                   "apps": {"Cursor": 30}, "hh": {}}  # legacy int
    p = insights.compute(cfg)
    cur30 = next(a for a in p["apps"] if a["name"] == "Cursor")
    ok(cur30["words"] == 50 and cur30["count"] == 1 and cur30["avg"] == 50,
       "30-day per-app row carries words/count/avg")
    cur_all = next(a for a in p["apps_all"] if a["name"] == "Cursor")
    ok(cur_all["words"] == 80 and cur_all["count"] == 1,
       "all-time window includes legacy-int days (count-less)")

    # 3. merge rule
    cfg["stats_cloud"] = {"days": {t: {"w": 100, "n": 2}}, "hh": {"9": 100},
                          "last_ts": "x", "fetched_at": "y"}
    p = insights.compute(cfg)
    ok(p["today_words"] == 162, "cloud day merges additively with the ledger")

    # 4. percentile mapping
    for wpm, lo, hi in ((52, 45, 55), (100, 3.5, 4.5), (150, 0.4, 0.6),
                        (200, 0.05, 0.2), (30, 98, 100)):
        v = insights._percentile(wpm)
        ok(lo <= v <= hi, f"percentile({wpm}) = {v} within [{lo}, {hi}]")

    # 5. polish delta
    ok(insights.polish_delta("um so the the cat sat", "The cat sat.") > 0,
       "polish_delta counts cleanup edits")
    ok(insights.polish_delta("same words here", "same words here") == 0,
       "polish_delta 0 on identical text")
    ok(insights.polish_delta("", "x") == 0, "polish_delta 0 on empty raw")

    # 6. fail-closed
    junk = insights.compute({"stats_daily": "garbage", "stats_cloud": 5})
    ok(isinstance(junk, dict), "compute survives junk config")

    def boom(c):
        raise RuntimeError("disk full")

    insights.record_dictation(cfg, boom, 10, seconds=1)
    ok(True, "record_dictation swallows a failing save")

    print(f"\nALL {PASS} INSIGHTS FIXTURES PASS")


if __name__ == "__main__":
    main()
