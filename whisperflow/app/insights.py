"""
insights.py — dictation statistics behind the dashboard's Insights page.

Shared by macOS (`main.py`) and Windows (`win_main.py`); the UI is the shared
`flume_dashboard_html.py` + `DashboardApi.get_insights`/`refresh_insights`.

HARD GUARANTEES (Hard Rule #1): every public function is fail-closed. Stats are
a peripheral feature — any error here is swallowed (logged at debug) and the
record→transcribe→inject path proceeds untouched.

Data model (all local, in ~/.verbal/config.json — no Supabase columns):

  stats_daily   {"YYYY-MM-DD": {"w","n","s","fx","apps":{name:[words,dictations]},"hh":{"0".."23":words}}}
                (app values were a bare words int in the first build — readers
                accept both shapes; writers upgrade an int in place)
                The per-day ledger this device accumulates at dictation time.
                Bounded to LEDGER_MAX_DAYS (lifetime numbers survive pruning
                via stats_total).
  stats_total   {"w","n","s","fx"} — lifetime counters for THIS device.
  stats_since   "YYYY-MM-DD" — the day the ledger started existing. Load-bearing
                for the cloud merge rule below.
  stats_cloud   {"days":{d:{"w","n"}}, "hh":{...}, "last_ts":iso, "fetched_at":iso}
                Incremental aggregate of the account's `transcriptions` rows.

Merge rule (prevents double counting without losing anything):
  - a cloud row from a day BEFORE stats_since counts regardless of device
    (the ledger has nothing for those days — pre-feature history, any device);
  - a cloud row from a day ON/AFTER stats_since counts only when it came from
    ANOTHER device (this device's words are already in the ledger).
  A merged day is therefore ledger + eligible-cloud, never both for one row.
Speaking-time, per-app and polish stats exist only in the ledger (the cloud
rows carry no duration/app), so WPM and "time saved" are this-device numbers.
"""

import logging
import threading
from datetime import date, datetime, timedelta

logger = logging.getLogger("verbal.insights")

LEDGER_MAX_DAYS = 800          # ~2.2 years of per-day detail
APPS_PER_DAY_CAP = 30          # per-day app keys before folding into "Other"
TYPING_WPM = 40                # the classic average-typist baseline for "time saved"
CLOUD_PAGE = 1000              # PostgREST page size
CLOUD_MAX_PAGES = 40           # safety valve per refresh (40k rows)
_cloud_lock = threading.Lock()  # one cloud refresh at a time per process


def _today() -> str:
    return str(date.today())


# ── capture (called from the dictation pipeline, AFTER the paste) ─────────────

def record_dictation(config, save_config_fn, words, seconds=0.0,
                     app_name="", fx_words=0):
    """Accumulate one finished dictation into the local ledger. Never raises."""
    try:
        if not isinstance(words, int) or words <= 0:
            return
        day = _today()
        ledger = config.get("stats_daily")
        if not isinstance(ledger, dict):
            ledger = {}
        config.setdefault("stats_since", day)
        d = ledger.get(day)
        if not isinstance(d, dict):
            d = {"w": 0, "n": 0, "s": 0.0, "fx": 0, "apps": {}, "hh": {}}
        d["w"] = int(d.get("w", 0)) + words
        d["n"] = int(d.get("n", 0)) + 1
        try:
            d["s"] = round(float(d.get("s", 0.0)) + max(0.0, float(seconds)), 1)
        except Exception:
            pass
        try:
            d["fx"] = int(d.get("fx", 0)) + max(0, int(fx_words))
        except Exception:
            pass
        apps = d.get("apps") if isinstance(d.get("apps"), dict) else {}
        name = (app_name or "Other").strip() or "Other"
        if name not in apps and len(apps) >= APPS_PER_DAY_CAP:
            name = "Other"
        cur = apps.get(name)
        if isinstance(cur, list) and len(cur) == 2:      # current shape [w, n]
            apps[name] = [int(cur[0]) + words, int(cur[1]) + 1]
        elif isinstance(cur, (int, float)):              # first-build shape: bare words
            apps[name] = [int(cur) + words, 1]
        else:
            apps[name] = [words, 1]
        d["apps"] = apps
        hh = d.get("hh") if isinstance(d.get("hh"), dict) else {}
        hour = str(datetime.now().hour)
        hh[hour] = int(hh.get(hour, 0)) + words
        d["hh"] = hh
        ledger[day] = d
        # prune oldest days beyond the cap (lifetime numbers live in stats_total)
        if len(ledger) > LEDGER_MAX_DAYS:
            for k in sorted(ledger.keys())[:len(ledger) - LEDGER_MAX_DAYS]:
                ledger.pop(k, None)
        config["stats_daily"] = ledger
        tot = config.get("stats_total")
        if not isinstance(tot, dict):
            tot = {"w": 0, "n": 0, "s": 0.0, "fx": 0}
        tot["w"] = int(tot.get("w", 0)) + words
        tot["n"] = int(tot.get("n", 0)) + 1
        try:
            tot["s"] = round(float(tot.get("s", 0.0)) + max(0.0, float(seconds)), 1)
            tot["fx"] = int(tot.get("fx", 0)) + max(0, int(fx_words))
        except Exception:
            pass
        config["stats_total"] = tot
        save_config_fn(config)
    except Exception as e:
        logger.debug("record_dictation skipped: %s", e)


def polish_delta(raw_text, final_text):
    """How many words the pipeline changed between the raw transcript and what
    was pasted (AI cleanup + snippets). Word-level SequenceMatcher; cheap for
    dictation-sized texts. Never raises."""
    try:
        a = (raw_text or "").split()
        b = (final_text or "").split()
        if not a or not b or a == b:
            return 0
        import difflib
        changed = 0
        for op, i1, i2, j1, j2 in difflib.SequenceMatcher(a=a, b=b).get_opcodes():
            if op != "equal":
                changed += max(i2 - i1, j2 - j1)
        return changed
    except Exception:
        return 0


# ── cloud backfill (account-wide history from `transcriptions`) ───────────────

def refresh_cloud(config, save_config_fn):
    """Incrementally aggregate the account's transcriptions into stats_cloud.
    Returns True when new rows were folded in. Network — call off the UI thread.
    Fail-closed: any error leaves the existing cache untouched."""
    try:
        uid = (config.get("sync_user_id") or "").strip()
        if not uid:
            return False
        if not _cloud_lock.acquire(blocking=False):
            return False
        try:
            return _refresh_cloud_locked(config, save_config_fn, uid)
        finally:
            _cloud_lock.release()
    except Exception as e:
        logger.debug("insights cloud refresh skipped: %s", e)
        return False


def _refresh_cloud_locked(config, save_config_fn, uid):
    import httpx
    from app.auth import auth_header
    from app.supabase_config import REST_URL
    from app.config import get_device_id

    cache = config.get("stats_cloud")
    if not isinstance(cache, dict):
        cache = {"days": {}, "hh": {}, "last_ts": "", "fetched_at": ""}
    days = cache.get("days") if isinstance(cache.get("days"), dict) else {}
    hh = cache.get("hh") if isinstance(cache.get("hh"), dict) else {}
    last_ts = cache.get("last_ts") or ""
    since = config.get("stats_since") or ""
    my_dev = get_device_id(config)

    changed = False
    for _ in range(CLOUD_MAX_PAGES):
        params = {
            "select": "created_at,device_id,text",
            "user_id": f"eq.{uid}",
            "order": "created_at.asc",
            "limit": str(CLOUD_PAGE),
        }
        if last_ts:
            params["created_at"] = f"gt.{last_ts}"
        resp = httpx.get(f"{REST_URL}/transcriptions", params=params,
                         headers=auth_header(config), timeout=30)
        if resp.status_code != 200:
            logger.debug("insights cloud fetch %s: %s", resp.status_code, resp.text[:120])
            break
        rows = resp.json()
        if not isinstance(rows, list) or not rows:
            break
        for row in rows:
            ts = row.get("created_at") or ""
            last_ts = ts or last_ts
            words = len((row.get("text") or "").split())
            if not words:
                continue  # tombstoned / empty rows
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone()
            except Exception:
                continue
            day = str(dt.date())
            # Merge rule: after the ledger began, this device's rows are
            # already counted locally — only other devices add here.
            if since and day >= since and (row.get("device_id") or "") == my_dev:
                continue
            d = days.get(day)
            if not isinstance(d, dict):
                d = {"w": 0, "n": 0}
            d["w"] = int(d.get("w", 0)) + words
            d["n"] = int(d.get("n", 0)) + 1
            days[day] = d
            hkey = str(dt.hour)
            hh[hkey] = int(hh.get(hkey, 0)) + words
            changed = True
        if len(rows) < CLOUD_PAGE:
            break

    cache.update(days=days, hh=hh, last_ts=last_ts,
                 fetched_at=datetime.now().isoformat(timespec="seconds"))
    config["stats_cloud"] = cache
    save_config_fn(config)
    return changed


# ── payload (everything the Insights screen renders) ─────────────────────────

def _merged_days(config):
    """{date: {"w","n"}} — ledger + eligible cloud days (see merge rule)."""
    out = {}
    ledger = config.get("stats_daily")
    if isinstance(ledger, dict):
        for day, d in ledger.items():
            if isinstance(d, dict):
                out[day] = {"w": int(d.get("w", 0)), "n": int(d.get("n", 0))}
    cloud = config.get("stats_cloud")
    if isinstance(cloud, dict) and isinstance(cloud.get("days"), dict):
        for day, d in cloud["days"].items():
            if not isinstance(d, dict):
                continue
            m = out.get(day, {"w": 0, "n": 0})
            m["w"] += int(d.get("w", 0))
            m["n"] += int(d.get("n", 0))
            out[day] = m
    return out


def _streaks(days):
    """(current, best) run of consecutive days with words>0. The current run may
    end today OR yesterday (today just hasn't happened yet)."""
    active = sorted(d for d, v in days.items() if v.get("w", 0) > 0)
    if not active:
        return 0, 0
    best = run = 1
    prev = None
    for d in active:
        if prev is not None:
            try:
                gap = (date.fromisoformat(d) - date.fromisoformat(prev)).days
            except Exception:
                gap = 99
            run = run + 1 if gap == 1 else 1
        best = max(best, run)
        prev = d
    today = date.today()
    lastd = date.fromisoformat(active[-1])
    current = run if (today - lastd).days <= 1 else 0
    return current, best


def _percentile(wpm):
    """'Top X%' vs global TYPING speeds (avg typist ≈ 52 wpm; 100 ≈ top 4%,
    150 ≈ top 0.5% — the framing Wispr popularized). Piecewise-linear, clamped."""
    pts = [(40, 75.0), (52, 50.0), (65, 25.0), (80, 10.0), (100, 4.0),
           (120, 2.0), (150, 0.5), (180, 0.1)]
    if wpm <= pts[0][0]:
        return 99.0
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if wpm <= x1:
            f = (wpm - x0) / (x1 - x0)
            return round(y0 + f * (y1 - y0), 1)
    return 0.1


def compute(config):
    """Everything the Insights screen needs, as one JSON-safe dict. Never raises
    — on any unexpected failure returns {"empty": True}."""
    try:
        return _compute(config)
    except Exception as e:
        logger.debug("insights compute failed: %s", e)
        return {"empty": True}


def _compute(config):
    days = _merged_days(config)
    today = date.today()
    tstr = str(today)

    def span(n, end_offset=0):
        """Total words/dictations over the n days ending `end_offset` days ago."""
        w = n_ = 0
        for i in range(n):
            d = str(today - timedelta(days=end_offset + i))
            v = days.get(d)
            if v:
                w += v.get("w", 0)
                n_ += v.get("n", 0)
        return w, n_

    total_w = sum(v.get("w", 0) for v in days.values())
    total_n = sum(v.get("n", 0) for v in days.values())
    today_w, today_n = span(1)
    week_w, _ = span(7)
    m_w, _ = span(30)
    pm_w, _ = span(30, 30)
    month_delta = round((m_w - pm_w) / pm_w * 100) if pm_w > 0 else None

    # This-device ledger extras: speech time, apps, hours, polish
    ledger = config.get("stats_daily") if isinstance(config.get("stats_daily"), dict) else {}
    tot = config.get("stats_total") if isinstance(config.get("stats_total"), dict) else {}
    led_w = int(tot.get("w", 0))
    led_s = float(tot.get("s", 0.0))
    wpm = round(led_w / (led_s / 60.0)) if led_s >= 60 and led_w else None
    pct = _percentile(wpm) if wpm else None

    def saved_minutes(w, s):
        return max(0.0, w / TYPING_WPM - s / 60.0)

    m_led_w = m_led_s = 0.0
    for i in range(30):
        d = ledger.get(str(today - timedelta(days=i)))
        if isinstance(d, dict):
            m_led_w += int(d.get("w", 0))
            m_led_s += float(d.get("s", 0.0))
    saved_month = round(saved_minutes(m_led_w, m_led_s)) if m_led_s > 0 else None
    saved_all = round(saved_minutes(led_w, led_s)) if led_s > 0 else None

    def _apps_stats(day_dicts, top=7):
        """Aggregate per-app words + dictation counts over the given day dicts.
        Accepts both app-value shapes ([w, n] current, bare int first-build —
        the int shape has no count, so those takes read as count 0)."""
        agg = {}
        for d in day_dicts:
            if not (isinstance(d, dict) and isinstance(d.get("apps"), dict)):
                continue
            for name, v in d["apps"].items():
                w, n = (int(v[0]), int(v[1])) if isinstance(v, list) and len(v) == 2 \
                    else (int(v or 0), 0)
                cw, cn = agg.get(name, (0, 0))
                agg[name] = (cw + w, cn + n)
        rows = sorted(agg.items(), key=lambda kv: -kv[1][0])
        if len(rows) > top:
            ow = sum(v[0] for _, v in rows[top - 1:])
            on = sum(v[1] for _, v in rows[top - 1:])
            rows = rows[:top - 1] + [("Other", (ow, on))]
        total = sum(v[0] for _, v in rows) or 1
        return [
            {
                "name": name,
                "words": w,
                "count": n,
                "pct": round(w / total * 100),
                "avg": round(w / n) if n else None,
            }
            for name, (w, n) in rows
        ]

    apps_30 = _apps_stats(ledger.get(str(today - timedelta(days=i)))
                          for i in range(30))
    apps_all = _apps_stats(ledger.values())

    hours = [0] * 24
    for d in ledger.values():
        if isinstance(d, dict) and isinstance(d.get("hh"), dict):
            for h, w in d["hh"].items():
                try:
                    hours[int(h) % 24] += int(w or 0)
                except Exception:
                    pass
    cloud = config.get("stats_cloud") if isinstance(config.get("stats_cloud"), dict) else {}
    if isinstance(cloud.get("hh"), dict):
        for h, w in cloud["hh"].items():
            try:
                hours[int(h) % 24] += int(w or 0)
            except Exception:
                pass
    hours_total = sum(hours)
    peak_hour = hours.index(max(hours)) if hours_total else None
    morning_share = (round(sum(hours[5:12]) / hours_total * 100)
                     if hours_total else None)

    current_streak, best_streak = _streaks(days)
    busiest = max(days.items(), key=lambda kv: kv[1].get("w", 0), default=None)

    # Heatmap series: last 53 weeks, aligned so the grid can start on a Sunday.
    series = []
    start = today - timedelta(days=370)
    d = start
    while d <= today:
        v = days.get(str(d))
        series.append([str(d), v.get("w", 0) if v else 0])
        d += timedelta(days=1)

    fx = int(tot.get("fx", 0))
    rules = auto_rules = 0
    try:
        from app import dictionary
        dd = dictionary.get(config)
        rules = len(dd.get("replacements") or [])
        auto_rules = sum(1 for r in (dd.get("replacements") or []) if r.get("auto"))
    except Exception:
        pass

    return {
        "empty": total_w == 0,
        "total_words": total_w,
        "total_dictations": total_n,
        "today_words": today_w,
        "today_dictations": today_n,
        "week_words": week_w,
        "month_words": m_w,
        "month_delta_pct": month_delta,
        "wpm": wpm,
        "wpm_percentile": pct,
        "typing_wpm": TYPING_WPM,
        "saved_month_min": saved_month,
        "saved_all_min": saved_all,
        "current_streak": current_streak,
        "best_streak": best_streak,
        "busiest_day": list(busiest) if busiest and busiest[1].get("w", 0) > 0 else None,
        "series": series,
        "apps": apps_30,
        "apps_all": apps_all,
        "hours": hours,
        "peak_hour": peak_hour,
        "morning_share": morning_share,
        "polished_words": fx,
        "dict_rules": rules,
        "auto_rules": auto_rules,
        "cloud_fetched_at": (cloud.get("fetched_at") or ""),
        "since": config.get("stats_since") or "",
    }
