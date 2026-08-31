"""
Meetings — capture state machine + chunked transcription pipeline
(MEETINGS_DESIGN_HANDOFF.md; macOS only).

A meeting records TWO sources in parallel:
  - the microphone (you)      → its own sounddevice.InputStream — NEVER the
                                shared dictation Recorder (Rule #1: hotkey
                                dictation must keep working during a meeting)
  - system audio (the call)   → system_audio.SystemAudioCapture (ScreenCaptureKit)

Each source is chunked on silence boundaries (~8–22 s), transcribed through the
existing transcriber pipeline (Groq→Gemini→local, dictionary bias, 850-char
prompt cap), and appended to the transcript as an utterance:

    {"speaker": "self"|"s<N>", "t0": secs, "t1": secs, "text": "..."}

Speaker model (v2, 2026-08-28 — the Granola model): source-based, TWO speakers.
Mic = "self", labelled with the signed-in user's name (`self_speaker_label()`,
"You" when signed out); ALL system audio = "s1", labelled "Them" (everyone else
on the call). No acoustic diarization, no "Speaker N" guesses: without a bot in
the meeting nobody gets reliable per-person names from a mixed system-audio
stream, and a wrong split shown with confidence costs trust. Rename is still
retroactive per-id (rename_speaker) — in a 1:1, "Them" → "Alice" is one
double-click. The v1 gap heuristic / AssemblyAI re-partition code below is
retired (flag `meetings_diarize_enabled` now defaults OFF) and kept only for
the fixtures.

States: idle → preparing → recording ⇄ paused → stopping → processing → ready|failed

HARD GUARANTEES (Rule #1): every public method is try/except'd and fails
closed. A meeting failure never touches the dictation path.
"""
import json
import logging
import os
import re
import threading
import time
import uuid
import wave

import numpy as np

from app.config import save_config, MEETINGS_CAP

logger = logging.getLogger("verbal.meetings")

SELF_FALLBACK_LABEL = "You"
THEM_LABEL = "Them"          # the single system-audio speaker (id "s1")


def self_speaker_label(config):
    """Display label for the mic ("self") speaker: the signed-in user's name
    (Google `full_name`/`name` stored in config['auth']['name']), else "You".
    `auth.name` falls back to the e-mail address at sign-in, so an address is
    treated as "no name". Never raises."""
    try:
        auth = (config or {}).get("auth") or {}
        name = str(auth.get("name") or "").strip()
        if name and "@" not in name:
            return name
    except Exception:
        pass
    return SELF_FALLBACK_LABEL


def with_self_name(speakers, config):
    """Return a copy of a speakers map where a placeholder "self" label (missing
    or the legacy literal "You") is replaced by `self_speaker_label(config)`.
    Meetings recorded before 2026-08-28 persisted "You"; a user-typed rename of
    "self" is left untouched. Pure; never raises."""
    try:
        if not isinstance(speakers, dict):
            return speakers
        cur = str(speakers.get("self") or "").strip()
        if cur and cur != SELF_FALLBACK_LABEL:
            return speakers
        label = self_speaker_label(config)
        if label == SELF_FALLBACK_LABEL and cur:
            return speakers
        out = dict(speakers)
        out["self"] = label
        return out
    except Exception:
        return speakers


def _cloud_gate(cfg) -> bool:
    """May this meeting talk to Supabase for the current account? (IDI-170)

    `sync_user_id` alone is NOT enough: it used to survive `sign_out()`, so
    every meeting insert/patch/upload here kept writing into the account the
    user had just left. Both halves are required — an account id to key the
    rows by AND a real signed-in session (`auth.cloud_allowed`).

    Meetings are deliberately NOT gated on the `sync_enabled` toggle
    (IDI-171): they are capture artifacts, not "sync". Fail-closed."""
    try:
        if not (cfg or {}).get("sync_user_id"):
            return False
        from app import auth
        return bool(auth.cloud_allowed(cfg))
    except Exception:
        return False


SR = 16000                      # both sources normalized to 16 kHz mono float32
CHUNK_MIN_S = 8.0               # earliest silence-aligned cut
CHUNK_MAX_S = 22.0              # hard cut
SILENCE_RMS = 0.008             # "quiet" threshold for a cut window
SILENCE_WIN_S = 0.7             # trailing window that must be quiet to cut
SPEAKER_GAP_S = 90.0            # v1 only (retired): silence gap → new speaker id
SELF_CLUSTER_SHARE = 0.7        # diarized cluster is "the user" only at >=70% self overlap
MEETINGS_DIR = os.path.expanduser("~/.verbal/meetings")
TRANSCRIPT_CHAR_BUDGET = 24000  # LLM input cap: head + tail kept, middle elided

# Post-meeting summary — STRICT JSON contract consumed by the 31e renderer and
# the hybrid-notes widget (#21). The model is a summarizer, never an assistant.
_SUMMARY_SYSTEM = """You summarize meeting transcripts. Reply with ONE JSON object, no prose, no code fences:
{"summary": "2-5 sentence plain-language summary of what the meeting covered and concluded",
 "decisions": ["each explicit decision made, one string each; [] if none"],
 "action_items": [{"owner": "<speaker id like self/s1, or null if unclear>", "task": "the commitment",
                   "due": "<short due label like 'Thursday', 'Jul 24', 'EOW' ONLY if a deadline was said, else null>"}],
 "hybrid_notes": [{"user_line": "<verbatim line from USER NOTES>", "ai_addition": "<ONE short sentence of context from the transcript, or empty string>"}]}
Rules:
- Use only information present in the transcript/notes. Never invent facts, names, dates or numbers.
- Speakers: "self" is the user (named in SPEAKERS); "s1" ("Them") is EVERYONE else on the call, mixed
  together. When the transcript makes clear which other person said or owns something (they introduce
  themselves, or are addressed by name), use that name in the summary/task text; otherwise say "the
  other participant(s)". Never guess a name.
- decisions are things the participants AGREED or RESOLVED, not topics discussed.
- action_items owner must be one of the speaker ids given, else null.
- action_items due: only when the transcript states a deadline for THAT task; keep it under 12
  characters (weekday, date or shorthand); null otherwise. Never guess a date.
- hybrid_notes: one entry PER non-empty line of USER NOTES, in order, user_line copied verbatim;
  ai_addition adds transcript context the note is missing (or "" when the note needs nothing).
- Write EVERY output field (summary, decisions, tasks, ai_addition) in the OUTPUT
  LANGUAGE stated in the user message — no other language, never translate.
- Valid JSON only. No trailing commas."""

# ISO code → name the summary LLM is told to write in. The model must NEVER
# judge the language itself (it once produced a Russian summary for an English
# meeting) — we detect/pin it and state it explicitly.
_LANG_NAMES = {
    "en": "English", "ur": "Urdu", "hi": "Hindi", "ar": "Arabic", "es": "Spanish",
    "fr": "French", "de": "German", "pt": "Portuguese", "tr": "Turkish",
    "id": "Indonesian", "ru": "Russian", "zh": "Chinese", "ja": "Japanese",
}

# Whisper silence hallucinations — a meeting utterance that is EXACTLY one of
# these is noise, never content (dictation is untouched: someone may really
# dictate "Thank you." — but a bare one inside a meeting chunk is hallucination).
_MEETING_HALLUCINATIONS = {
    "thank you.", "thank you", "thanks.", "thanks", "you", "you.", "bye.", "bye",
    "thanks for watching.", "thank you for watching.", ".", "...",
}


def _summary_output_language(config, transcript, session_language=""):
    """Deterministic output language for the summary/notes prose. Independent of
    the meeting's *spoken* (transcription) language — `meetings_notes_language`
    defaults to "en" so e.g. an Urdu meeting still gets English notes; set it to
    "auto" to fall back to: per-meeting pin > global spoken-language pin > script
    detection over the transcript text > English."""
    notes_pref = (config.get("meetings_notes_language") or "en").strip().lower()
    if notes_pref != "auto":
        return _LANG_NAMES.get(notes_pref, "English")
    lang = (session_language or config.get("spoken_language") or "en").strip().lower()
    if lang and lang != "auto":
        return _LANG_NAMES.get(lang, "English")
    text = " ".join((u.get("text") or "") for u in (transcript or []))[:4000]
    counts = {"ar": 0, "hi": 0, "ru": 0, "zh": 0, "ja": 0, "latin": 0}
    for ch in text:
        o = ord(ch)
        if 0x0600 <= o <= 0x06FF:
            counts["ar"] += 1        # Arabic script (Arabic/Urdu)
        elif 0x0900 <= o <= 0x097F:
            counts["hi"] += 1
        elif 0x0400 <= o <= 0x04FF:
            counts["ru"] += 1
        elif 0x4E00 <= o <= 0x9FFF:
            counts["zh"] += 1
        elif 0x3040 <= o <= 0x30FF:
            counts["ja"] += 1
        elif ch.isalpha():
            counts["latin"] += 1
    best = max(counts, key=counts.get)
    if best == "latin" or counts[best] == 0:
        return "English"             # Latin-script detail beyond scope of v1
    return _LANG_NAMES.get("ur" if best == "ar" else best, "English")


def _now_iso():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def map_diarized_speakers(transcript, dz):
    """Re-partition system-audio speaker ids from real diarization.

    `transcript`: the session's utterance list ({"speaker","t0","t1","text"}).
    `dz`: diarized turns [{"speaker": "A", "start": s, "end": e}] in SECONDS on the
    same timeline (the meeting WAV is a timeline-accurate mixdown, so AssemblyAI's
    clock IS the transcript's clock).

    Returns (new_ids, remap_hint) where `new_ids` is a per-utterance list of speaker
    ids (unchanged entries keep their old id) and `remap_hint` maps old sid ->
    the new sid that received the MAJORITY of its utterances (used to carry a name
    the user typed mid-meeting over to the re-partitioned id).

    Rules, in order of why they exist:
    - "self" utterances are never touched: the mic channel is ground truth for who
      the user is, and no statistical model gets to overrule it.
    - The diarized speaker whose talk-time lands mostly on self utterances IS the
      user (the WAV mixes the mic in, so AAI labels the user's voice too) — that
      cluster is excluded from mapping, otherwise the user would appear a second
      time as a phantom "Speaker N".
    - A system utterance is only relabelled when a diarized turn overlaps >= 30% of
      it; anything murkier keeps its old label. Wrongly MERGING two people is worse
      than the status quo, which the user can already fix by renaming.
    - New ids are s1, s2, ... in order of first appearance, so labels stay familiar.

    Pure and total: no I/O, never raises, empty inputs -> everything unchanged.
    """
    try:
        if not transcript or not dz:
            return [u.get("speaker") for u in (transcript or [])], {}

        def overlap(u, d):
            return max(0.0, min(float(u.get("t1") or 0), d["end"])
                       - max(float(u.get("t0") or 0), d["start"]))

        # Which diarized cluster is the user?
        self_ov, sys_ov = {}, {}
        for d in dz:
            for u in transcript:
                ov = overlap(u, d)
                if ov <= 0:
                    continue
                bucket = self_ov if u.get("speaker") == "self" else sys_ov
                bucket[d["speaker"]] = bucket.get(d["speaker"], 0.0) + ov
        # A cluster is "the user" only on a CLEAR majority of its overlap landing on
        # self utterances (>=70%). A bare plurality used to be enough, which let a
        # remote participant who talked over the user get excluded as a phantom —
        # i.e. a real person silently disappeared from the speaker list.
        self_clusters = {k for k, v in self_ov.items()
                         if v >= SELF_CLUSTER_SHARE * (v + sys_ov.get(k, 0.0))}

        order, alias = [], {}
        new_ids, votes = [], {}          # votes: old sid -> {new sid: count}
        for u in transcript:
            old = u.get("speaker")
            if old == "self":
                new_ids.append("self")
                continue
            dur = max(0.001, float(u.get("t1") or 0) - float(u.get("t0") or 0))
            best, best_ov = None, 0.0
            for d in dz:
                if d["speaker"] in self_clusters:
                    continue
                ov = overlap(u, d)
                if ov > best_ov:
                    best, best_ov = d["speaker"], ov
            if best is None or best_ov < 0.3 * dur:
                new_ids.append(old)
                continue
            if best not in alias:
                order.append(best)
                alias[best] = f"s{len(order)}"
            sid = alias[best]
            new_ids.append(sid)
            votes.setdefault(old, {})
            votes[old][sid] = votes[old].get(sid, 0) + 1
        remap_hint = {old: max(vs, key=vs.get) for old, vs in votes.items() if vs}
        return new_ids, remap_hint
    except Exception:
        return [u.get("speaker") for u in (transcript or [])], {}


def split_utterances_by_turns(transcript, dz, min_words=1):
    """Split system-audio utterances at diarized speaker-turn boundaries using
    per-word timestamps, so `map_diarized_speakers` labels TURNS, not 8–22 s
    Groq chunks.

    Why: one chunk often holds two people ("...sounds good." / "Great, so next
    week..."). With one label per chunk the shorter voice is erased — a third
    participant who only interjects can vanish from the speaker list entirely.

    Each utterance may carry `words`: [[text, t0, t1], ...] in ABSOLUTE seconds.
    Utterances without words (local Whisper, alt ASR providers, older meetings)
    and "self" utterances pass through unchanged. A word belongs to the diarized
    turn containing its midpoint; words in no turn stick with the previous word.
    Splits are only made where the diarized speaker actually changes, and a
    fragment shorter than `min_words` is merged back into its neighbour rather
    than becoming a one-word "utterance".

    Pure and total: never raises; on any doubt returns the input list unchanged.
    Output utterances drop the `words` key (they are consumed here).
    """
    try:
        if not transcript or not dz:
            return [dict((k, v) for k, v in u.items() if k != "words")
                    for u in (transcript or [])]
        turns = sorted(({"speaker": d["speaker"], "start": float(d["start"]),
                         "end": float(d["end"])} for d in dz), key=lambda d: d["start"])

        def turn_at(t):
            for d in turns:
                if d["start"] <= t <= d["end"]:
                    return d["speaker"]
            return None

        out = []
        for u in transcript:
            words = u.get("words")
            base = {k: v for k, v in u.items() if k != "words"}
            if u.get("speaker") == "self" or not isinstance(words, list) or len(words) < 2:
                out.append(base)
                continue
            groups, cur, cur_spk = [], [], None
            for w in words:
                try:
                    txt, ws, we = str(w[0]), float(w[1]), float(w[2])
                except Exception:
                    continue
                spk = turn_at((ws + we) / 2.0)
                if spk is None:
                    spk = cur_spk
                if cur and spk != cur_spk:
                    groups.append((cur_spk, cur))
                    cur = []
                cur_spk = spk
                cur.append((txt, ws, we))
            if cur:
                groups.append((cur_spk, cur))
            if len(groups) <= 1:
                out.append(base)
                continue
            # fold tiny fragments into the previous (or next) group
            merged = []
            for spk, ws in groups:
                if merged and len(ws) < min_words:
                    merged[-1] = (merged[-1][0], merged[-1][1] + ws)
                else:
                    merged.append((spk, list(ws)))
            if len(merged) > 1 and len(merged[0][1]) < min_words:
                merged[1] = (merged[1][0], merged[0][1] + merged[1][1])
                merged = merged[1:]
            if len(merged) <= 1:
                out.append(base)
                continue
            for i, (_, ws) in enumerate(merged):
                t0 = ws[0][1] if i else float(u.get("t0") or ws[0][1])
                t1 = ws[-1][2] if i < len(merged) - 1 else float(u.get("t1") or ws[-1][2])
                text = " ".join(x[0].strip() for x in ws if x[0].strip())
                if not text:
                    continue
                part = dict(base, t0=round(t0, 2), t1=round(max(t1, t0), 2), text=text)
                out.append(part)
        out.sort(key=lambda x: float(x.get("t0") or 0))
        return out
    except Exception:
        return list(transcript or [])


def apply_speaker_names(speakers, names, parsed=None):
    """Apply transcript-derived names (from the summary's `speaker_names`) to a
    speakers map — ONLY onto placeholder labels ("Speaker N"), never over a name
    the user or the voiceprint already set. Returns the list of ids renamed.

    When `parsed` (the summary dict) is given, "Speaker N" mentions in the prose
    it produced are rewritten to the new name too, so the notes read coherently.
    Pure over its inputs (mutates `speakers`/`parsed` in place, never raises)."""
    renamed = []
    try:
        taken = {str(v).strip().lower() for v in (speakers or {}).values()}
        for sid, name in (names or {}).items():
            cur = (speakers or {}).get(sid)
            if cur is None or not re.match(r"(?i)^speaker\s+\d+$", str(cur).strip()):
                continue
            if name.strip().lower() in taken:
                continue
            speakers[sid] = name
            taken.add(name.strip().lower())
            renamed.append((sid, str(cur).strip(), name))
        if parsed and renamed:
            def fix(s):
                for _, old, new in renamed:
                    s = re.sub(r"\b" + re.escape(old) + r"\b", new, s)
                return s
            parsed["summary"] = fix(parsed.get("summary") or "")
            parsed["decisions"] = [fix(d) for d in parsed.get("decisions") or []]
            for it in parsed.get("action_items") or []:
                it["task"] = fix(it.get("task") or "")
            for hn in parsed.get("hybrid_notes") or []:
                hn["ai_addition"] = fix(hn.get("ai_addition") or "")
    except Exception:
        pass
    return [sid for sid, _, _ in renamed]


def _transcript_text(transcript, speakers, budget=TRANSCRIPT_CHAR_BUDGET):
    """Render utterances as '[m:ss] Name: text' lines, eliding the middle when
    over budget (head + tail preserved — meetings resolve at the ends)."""
    lines = []
    for u in transcript:
        name = speakers.get(u.get("speaker"), u.get("speaker", "?"))
        t = int(u.get("t0", 0))
        lines.append(f"[{t//60}:{t%60:02d}] {name}: {u.get('text','')}")
    text = "\n".join(lines)
    if len(text) <= budget:
        return text
    head = text[: budget // 2]
    tail = text[-(budget // 2):]
    return head + "\n[… middle of meeting elided …]\n" + tail


def _parse_summary_json(raw):
    """Parse the model's JSON (tolerating code fences / stray prose). Returns a
    dict with the four keys or None."""
    if not raw:
        return None
    s = raw.strip()
    if s.startswith("```"):
        s = s.strip("`")
        if s.lower().startswith("json"):
            s = s[4:]
    i, j = s.find("{"), s.rfind("}")
    if i < 0 or j <= i:
        return None
    try:
        data = json.loads(s[i:j + 1])
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    out = {
        "summary": str(data.get("summary", "") or ""),
        "decisions": [str(d) for d in data.get("decisions", []) if str(d).strip()],
        "action_items": [],
        "hybrid_notes": [],
        "speaker_names": {},
    }
    # Names the model read off the transcript — validated hard, because a wrong
    # name is worse than "Speaker 2": sid must be a real non-self id, name must be
    # 1–2 alphabetic words, not itself a placeholder, and unique.
    sn = data.get("speaker_names")
    if isinstance(sn, dict):
        seen = set()
        for sid, name in sn.items():
            sid = str(sid).strip()
            name = " ".join(str(name or "").strip().split())
            if (not re.fullmatch(r"s\d{1,2}", sid) or not name
                    or not re.fullmatch(r"[^\W\d_]+(?: [^\W\d_]+)?", name, re.UNICODE)
                    or len(name) > 32 or re.match(r"(?i)^speaker\b", name)
                    or name.lower() in seen):
                continue
            seen.add(name.lower())
            out["speaker_names"][sid] = name
    for it in data.get("action_items", []) or []:
        if isinstance(it, dict) and str(it.get("task", "")).strip():
            owner = it.get("owner")
            due = it.get("due")
            due = str(due).strip()[:14] if due and str(due).strip().lower() not in ("null", "none") else None
            out["action_items"].append(
                {"owner": str(owner) if owner else None,
                 "task": str(it["task"]).strip(), "done": False, "due": due})
    for hn in data.get("hybrid_notes", []) or []:
        if isinstance(hn, dict) and str(hn.get("user_line", "")).strip():
            out["hybrid_notes"].append(
                {"user_line": str(hn["user_line"]),
                 "ai_addition": str(hn.get("ai_addition", "") or "")})
    return out if out["summary"] else None


def _fmt_ts(secs):
    secs = int(secs or 0)
    h, m, s = secs // 3600, (secs % 3600) // 60, secs % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def export_transcript_txt(row):
    """Plain-text export of a meeting row: header + [m:ss] Name: text lines."""
    speakers = row.get("speakers") or {}
    lines = [
        row.get("title") or "Meeting",
        f"{(row.get('started_at') or '')[:16].replace('T', ' ')} · "
        f"{_fmt_ts(row.get('duration_seconds'))} · "
        f"{', '.join(speakers.values()) if speakers else 'unknown speakers'}",
        "",
    ]
    if (row.get("summary") or "").strip():
        lines += ["SUMMARY", row["summary"].strip(), ""]
    lines.append("TRANSCRIPT")
    for u in row.get("transcript") or []:
        name = speakers.get(u.get("speaker"), u.get("speaker", "?"))
        lines.append(f"[{_fmt_ts(u.get('t0'))}] {name}: {u.get('text', '')}")
    if not (row.get("transcript") or []):
        lines.append("(empty)")
    return "\n".join(lines) + "\n"


def export_transcript_md(row):
    """Markdown export: summary, decisions, action items, marks, transcript."""
    speakers = row.get("speakers") or {}
    out = [f"# {row.get('title') or 'Meeting'}", ""]
    out.append(f"**{(row.get('started_at') or '')[:16].replace('T', ' ')}** · "
               f"{_fmt_ts(row.get('duration_seconds'))}"
               + (f" · {', '.join(speakers.values())}" if speakers else ""))
    out.append("")
    if (row.get("summary") or "").strip():
        out += ["## Summary", "", row["summary"].strip(), ""]
    if row.get("decisions"):
        out += ["## Decisions", ""] + [f"- {d}" for d in row["decisions"]] + [""]
    if row.get("action_items"):
        out += ["## Action items", ""]
        for it in row["action_items"]:
            owner = speakers.get(it.get("owner"), "") if it.get("owner") else ""
            box = "x" if it.get("done") else " "
            out.append(f"- [{box}] {(owner + ': ') if owner else ''}{it.get('task', '')}")
        out.append("")
    if row.get("marked_moments"):
        out += ["## Marked moments", ""]
        for m in row["marked_moments"]:
            out.append(f"- **{_fmt_ts(m.get('t'))}** {m.get('label') or 'Marked moment'}")
        out.append("")
    if (row.get("scratchpad") or "").strip():
        out += ["## Your notes", "", row["scratchpad"].strip(), ""]
    out += ["## Transcript", ""]
    for u in row.get("transcript") or []:
        name = speakers.get(u.get("speaker"), u.get("speaker", "?"))
        out.append(f"**{name}** `[{_fmt_ts(u.get('t0'))}]` — {u.get('text', '')}")
        out.append("")
    if not (row.get("transcript") or []):
        out.append("_(empty)_")
    return "\n".join(out).rstrip() + "\n"


# ── Ask-your-meetings (chat Q&A with keyword retrieval) ─────────────────────────
_ASK_SYSTEM = """You answer questions about the user's recorded meetings using ONLY the meeting
context provided. Rules:
- Ground every claim in the context; never invent facts, dates, names or numbers.
- When citing, name the meeting (its title) the information came from.
- If the context doesn't contain the answer, say so plainly and suggest which
  meeting to check.
- Be concise: a few sentences, or a short list when the question asks for items."""


def _fetch_meeting_rows(config, limit=25):
    """Recent meetings WITH transcripts from the cloud (local meta has none)."""
    try:
        user_id = config.get("sync_user_id", "")
        if not user_id or not _cloud_gate(config):
            return []
        import httpx
        from app.sync import SUPABASE_URL
        from app.auth import auth_header
        r = httpx.get(
            f"{SUPABASE_URL}/rest/v1/meetings?user_id=eq.{user_id}"
            f"&order=started_at.desc&limit={limit}",
            headers=auth_header(config), timeout=15)
        return r.json() if r.status_code == 200 else []
    except Exception as e:
        logger.debug("ask: fetch rows failed: %s", e)
        return []


def _tokens(text):
    import re as _re
    stop = {"the", "a", "an", "and", "or", "of", "in", "on", "at", "to", "is",
            "was", "we", "i", "it", "what", "who", "when", "did", "do", "does",
            "about", "for", "with", "my", "our", "me", "that", "this"}
    return [w for w in _re.findall(r"[a-z0-9']+", (text or "").lower())
            if len(w) > 1 and w not in stop]


def _score_meeting(row, q_tokens):
    hay_title = " ".join(_tokens(row.get("title", ""))) + " "
    hay_sum = " ".join(_tokens(row.get("summary", ""))) + " "
    hay_tx = " ".join(_tokens(" ".join(u.get("text", "")
                                       for u in (row.get("transcript") or []))))
    score = 0.0
    for t in q_tokens:
        if t in hay_title:
            score += 4
        if t in hay_sum:
            score += 2
        score += hay_tx.count(t) * 0.5
    return score


def _context_block(row, q_tokens, budget=3200):
    """One meeting as LLM context: header + summary/decisions/actions + the
    most question-relevant transcript lines (with neighbors)."""
    speakers = row.get("speakers") or {}
    head = [f"MEETING: {row.get('title') or 'Meeting'} "
            f"({(row.get('started_at') or '')[:10]}, {_fmt_ts(row.get('duration_seconds'))})"]
    if (row.get("summary") or "").strip():
        head.append(f"Summary: {row['summary'].strip()}")
    if row.get("decisions"):
        head.append("Decisions: " + "; ".join(row["decisions"]))
    if row.get("action_items"):
        head.append("Action items: " + "; ".join(
            f"{speakers.get(it.get('owner'), 'unassigned')}: {it.get('task', '')}"
            for it in row["action_items"]))
    tx = row.get("transcript") or []
    lines = [f"[{_fmt_ts(u.get('t0'))}] {speakers.get(u.get('speaker'), u.get('speaker', '?'))}: "
             f"{u.get('text', '')}" for u in tx]
    # pick lines containing question tokens (plus a neighbor each side)
    keep = set()
    for i, u in enumerate(tx):
        low = (u.get("text") or "").lower()
        if any(t in low for t in q_tokens):
            keep.update({i - 1, i, i + 1})
    picked = [lines[i] for i in sorted(k for k in keep if 0 <= k < len(lines))]
    if not picked:
        picked = lines[:12]                     # no keyword hits → head of meeting
    body, used = [], 0
    for ln in picked:
        if used + len(ln) > budget:
            body.append("[…]")
            break
        body.append(ln)
        used += len(ln)
    return "\n".join(head) + ("\nTranscript excerpts:\n" + "\n".join(body) if body else "")


def ask_meetings(config, question, rows=None):
    """Answer a question over the user's meetings. Returns
    {'ok', 'answer', 'sources': [titles]} — fails closed with an error dict."""
    try:
        q = (question or "").strip()
        if not q:
            return {"ok": False, "error": "Empty question."}
        rows = rows if rows is not None else _fetch_meeting_rows(config)
        rows = [r for r in rows if (r.get("transcript") or r.get("summary"))]
        if not rows:
            return {"ok": False,
                    "error": "No meetings with content yet — record one first."}
        q_tokens = _tokens(q)
        ranked = sorted(rows, key=lambda r: _score_meeting(r, q_tokens), reverse=True)
        top = ranked[:3]
        context = "\n\n---\n\n".join(_context_block(r, q_tokens) for r in top)
        from app.groq_proxy import chat_via_proxy
        messages = [{"role": "system", "content": _ASK_SYSTEM},
                    {"role": "user",
                     "content": f"MEETINGS CONTEXT:\n\n{context}\n\nQUESTION: {q}"}]
        answer = chat_via_proxy(messages, config, max_tokens=1024, timeout=30.0)
        if not answer:
            return {"ok": False, "error": "The model didn't answer — try again."}
        return {"ok": True, "answer": answer,
                "sources": [r.get("title") or "Meeting" for r in top]}
    except Exception as e:
        logger.error("ask_meetings failed: %s", e)
        return {"ok": False, "error": str(e)}


def generate_meeting_summary(config, transcript, speakers, scratchpad, marked_moments,
                             session_language=""):
    """Run the structured summary LLM call (proxy → one retry). Returns the
    parsed dict or None. Pure function so retry-after-restart can reuse it."""
    try:
        from app.groq_proxy import chat_via_proxy, ProxyPayloadTooLarge
        notes = "\n".join(l for l in (scratchpad or "").splitlines() if l.strip()) or "(none)"
        marks = "\n".join(f"- at {int(m.get('t',0))//60}:{int(m.get('t',0))%60:02d} "
                          f"{m.get('label','') or '(unlabeled)'}"
                          for m in (marked_moments or [])) or "(none)"
        spk = ", ".join(f"{sid} = {name}" for sid, name in (speakers or {}).items()) or "(unknown)"
        out_lang = _summary_output_language(config, transcript, session_language)
        budget = TRANSCRIPT_CHAR_BUDGET
        for attempt in (1, 2, 3):
            user = (f"OUTPUT LANGUAGE: {out_lang}. Every field must be written in {out_lang}.\n\n"
                    f"SPEAKERS: {spk}\n\nUSER NOTES:\n{notes}\n\nMARKED MOMENTS:\n{marks}\n\n"
                    f"TRANSCRIPT:\n{_transcript_text(transcript or [], speakers or {}, budget=budget)}")
            messages = [{"role": "system", "content": _SUMMARY_SYSTEM},
                        {"role": "user", "content": user}]
            # Groq strict JSON mode keeps llama on-contract; attempt 2 drops it in
            # case the model/proxy ever rejects response_format. A 413 means the
            # shared key's tokens-per-minute budget can't fit this request — halve
            # the transcript and retry rather than repeating the identical request.
            try:
                raw = chat_via_proxy(
                    messages, config, max_tokens=2048, timeout=45.0,
                    response_format={"type": "json_object"} if attempt == 1 else None)
            except ProxyPayloadTooLarge:
                logger.warning("summary attempt %d: 413 (token budget) — "
                               "retrying with a smaller transcript", attempt)
                budget //= 2
                continue
            parsed = _parse_summary_json(raw)
            if parsed:
                return parsed
            logger.warning("summary attempt %d unparseable: %r", attempt,
                           (raw or "")[:180])
        return None
    except Exception as e:
        logger.error("summary generation failed: %s", e)
        return None


def merge_action_done(old_items, new_items):
    """Regenerating a summary must not wipe the user's checkboxes: carry the
    done flag over to regenerated items with the same task text."""
    try:
        done = {(it.get("task") or "").strip().lower()
                for it in (old_items or []) if it.get("done")}
        for it in new_items or []:
            if (it.get("task") or "").strip().lower() in done:
                it["done"] = True
    except Exception:
        pass
    return new_items


# Notes model on Ollama Cloud (OpenAI-compatible). Swap this tag to try glm-4.6 /
# qwen3:235b, or set provider=None + a Groq model to go back to Groq-only.
NOTES_MODEL = "gpt-oss:120b"

MEETING_NOTES_SYSTEM = """You are a world-class MEETING ANALYST. You turn a raw, messy call
transcript (plus the user's own quick notes and marked moments) into the notes the
participant WISHED they had taken: complete, beautifully organized, instantly
scannable. Match the depth and polish of a top human analyst's write-up.

THE CONTRACT
- Lose nothing that matters: every decision, commitment, number, amount, date, name,
  option, reason and open question in the transcript appears in the notes.
- Reorganize by MEANING, not the order things were said. Group related points; lead
  with the most consequential.
- Attach reasons to their point ("chose X because Y"). Resolve self-corrections to the
  FINAL value ("Aug 4th, no wait the 5th" → the 5th). Keep stated uncertainty uncertain
  ("~", "roughly", "needs confirming") — never harden a maybe into a fact.
- The user's own notes + marked moments flag what mattered to THEM — fold each in where
  it belongs.
- If part of the audio is garbled or one-sided, reconstruct the missing side ONLY where
  context makes it unambiguous, and say briefly that you did. Never invent facts.
- Write EVERYTHING in the OUTPUT LANGUAGE stated in the user message. Never translate.

STRUCTURE (GitHub markdown). Use the sections that FIT this meeting — a rich advisory
call earns all of them; a 30-second sync earns two lines. In this order:

1. ## TL;DR — 3–6 tight bullets: the answer, the key numbers, the decision, the next
   move. Skip entirely for a trivial note.
2. ## <Topic> sections — one per real topic, logically ordered. One idea per bullet;
   nest sub-bullets for supporting detail; **bold** the load-bearing facts (names, dates,
   amounts, the operative word of a decision).
3. TABLES — this is mandatory, not optional. The MOMENT the meeting covers three or more
   items that share the same fields, render a real Markdown table, never a bullet list.
   Costs/prices, option comparisons, pros/cons, schedules, criteria rankings, before/after,
   anything with amounts or a shared shape becomes a table. Example — a cost discussion
   MUST come out like this, not as bullets:

   | Item | Cost | Notes |
   |---|---|---|
   | Tuition (non-EU) | €10,000–25,000/yr | Public unis €14k–18k |
   | Living funds to show | ~€13,500/yr | Your own money, not a fee |

   Compute derived values the speakers implied (totals, the unit conversions they used) —
   but NEVER invent numbers that weren't given or derivable.
4. ## Decisions — each agreement with its why.
5. ## Action items — "- [ ] task — **owner**, due **date**" (owner = a speaker NAME,
   never an id; omit owner/due when unstated). If the meeting laid out a multi-step plan,
   present it as a PHASED ROADMAP: "### Phase 1 — <name>" then its checkbox items.
6. ## Open questions — unresolved items, disagreements, things to confirm.

QUALITY BAR
- Rich when the meeting is rich, terse when it's thin — never padded, never a wall of text.
- Every heading must carry real content; drop empty ones.
- Sentence-case, clean punctuation, complete phrasing — you are a writer, not a transcript.
- NEVER invent facts, names, numbers or tasks. No preamble, no "Here are the notes", no
  closing remarks. Output the notes only."""


def generate_meeting_notes(config, row, session_language=""):
    """ONE LLM call → full meeting notes (markdown) or None. Cached by the
    caller in the row's notes_md — generated lazily on first open."""
    try:
        from app.groq_proxy import chat_via_proxy
        transcript = row.get("transcript") or []
        if not transcript:
            return None
        speakers = row.get("speakers") or {}
        out_lang = _summary_output_language(config, transcript, session_language)
        notes = "\n".join(l for l in (row.get("scratchpad") or "").splitlines()
                          if l.strip()) or "(none)"
        marks = "\n".join(
            f"- at {int(m.get('t', 0)) // 60}:{int(m.get('t', 0)) % 60:02d} "
            f"{m.get('label', '') or '(unlabeled)'}"
            + (f" — user note: {m['note']}" if m.get("note") else "")
            for m in (row.get("marked_moments") or [])) or "(none)"
        spk = ", ".join(f"{sid} = {name}" for sid, name in speakers.items()) or "(unknown)"
        user = (f"OUTPUT LANGUAGE: {out_lang}. Everything must be written in {out_lang}.\n\n"
                f"SPEAKERS: {spk}\n\nUSER'S OWN NOTES:\n{notes}\n\n"
                f"MARKED MOMENTS:\n{marks}\n\n"
                f"TRANSCRIPT:\n{_transcript_text(transcript, speakers)}")
        msgs = [{"role": "system", "content": MEETING_NOTES_SYSTEM},
                {"role": "user", "content": user}]
        # Notes run on Ollama Cloud's gpt-oss:120b (open-weight, strong at structured
        # markdown + tables). Fall back to Groq llama-3.3 if Ollama is unset/slow/down —
        # notes must never fail to generate. (richer notes: TL;DR + tables + roadmap)
        raw = chat_via_proxy(msgs, config, model=NOTES_MODEL, provider="ollama",
                             max_tokens=4000, timeout=90.0)
        if not (raw or "").strip():
            logger.info("meeting notes: Ollama empty/failed — falling back to Groq")
            raw = chat_via_proxy(msgs, config, max_tokens=4000, timeout=60.0)
        text = (raw or "").strip()
        if text.startswith("```"):
            text = text.strip("`").strip()
            if text.lower().startswith("markdown"):
                text = text[8:].lstrip()
        logger.info("meeting notes generated: %d chars (%s)", len(text), out_lang)
        return text or None
    except Exception as e:
        logger.warning("meeting notes generation failed: %s", e)
        return None


def regenerate_hybrid_addition(config, transcript, speakers, user_line):
    """One focused LLM call: regenerate the AI addition for a single hybrid-note
    line (widget 33i). Returns the new addition string or None."""
    try:
        from app.groq_proxy import chat_via_proxy
        system = ('Given a meeting transcript and ONE line of user notes, reply with ONE JSON '
                  'object: {"ai_addition": "<ONE short factual sentence of transcript context '
                  'for that note, or empty string>"} — use only facts from the transcript, '
                  'never invent. Valid JSON only.')
        user = (f"USER NOTE LINE: {user_line}\n\n"
                f"TRANSCRIPT:\n{_transcript_text(transcript or [], speakers or {}, budget=8000)}")
        raw = chat_via_proxy(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            config, max_tokens=256, timeout=25.0,
            response_format={"type": "json_object"})
        s = (raw or "").strip()
        i, j = s.find("{"), s.rfind("}")
        if i < 0 or j <= i:
            return None
        data = json.loads(s[i:j + 1])
        return str(data.get("ai_addition", "") or "")
    except Exception as e:
        logger.warning("hybrid regenerate failed: %s", e)
        return None


class _SourceChunker:
    """Accumulates float32@16k for one source and yields silence-aligned chunks.

    feed() runs inside the AUDIO CALLBACK, so it must be O(block): the silence
    check uses a small rolling tail buffer — never a concat of the whole
    accumulation (a full concat per callback starved PortAudio's realtime
    thread and stalled the mic stream after ~a minute). The one big
    concatenation happens in the transcription WORKER, not here.
    """

    def __init__(self, name, on_chunk):
        self.name = name
        self._on_chunk = on_chunk        # fn(source, t0_samples, [blocks])
        self._buf = []
        self._buf_len = 0
        self._t0 = 0                     # source-time sample offset of buffer start
        self._tail = np.zeros(int(SILENCE_WIN_S * SR), dtype=np.float32)
        self._tail_fill = 0              # how much of _tail is real data
        self._lock = threading.Lock()

    def feed(self, audio, source_samples):
        """`source_samples` = this source's total samples at the END of the block."""
        with self._lock:
            if self._buf_len == 0:
                self._t0 = max(0, source_samples - len(audio))
                self._tail_fill = 0
            self._buf.append(audio)
            self._buf_len += len(audio)
            # rolling tail window (O(block), no big copies)
            n = len(audio)
            t = self._tail
            if n >= len(t):
                t[:] = audio[-len(t):]
                self._tail_fill = len(t)
            else:
                t[:-n] = t[n:]
                t[-n:] = audio
                self._tail_fill = min(len(t), self._tail_fill + n)
            if self._buf_len / SR < CHUNK_MIN_S:
                return
            cut = self._buf_len / SR >= CHUNK_MAX_S
            if not cut and self._tail_fill >= len(t):
                cut = float(np.sqrt(np.mean(t * t))) < SILENCE_RMS
            if cut:
                self._flush_locked()

    def flush(self):
        with self._lock:
            self._flush_locked()

    def _flush_locked(self):
        if self._buf_len == 0:
            return
        blocks = self._buf
        t0 = self._t0
        self._buf, self._buf_len, self._tail_fill = [], 0, 0
        try:
            self._on_chunk(self.name, t0, blocks)   # worker concatenates
        except Exception as e:
            logger.debug("chunk handoff failed: %s", e)


class MeetingSession:
    """One live meeting. Create per meeting via MeetingManager."""

    def __init__(self, app, title="", use_mic=True, use_system=True, language=""):
        self.app = app
        self.id = str(uuid.uuid4())
        if not title:
            # Default title without the glibc-only '%-d' (no-pad day) directive:
            # the Windows CRT strftime raises ValueError("Invalid format string")
            # on it, so every meeting started without a typed title failed with
            # "manager start failed: Invalid format string" (2026-08-26 report).
            # tm_mday is already unpadded on every platform.
            lt = time.localtime()
            title = (f"Meeting — {time.strftime('%b', lt)} {lt.tm_mday}, "
                     f"{time.strftime('%H:%M', lt)}")
        self.title = title
        self.use_mic = bool(use_mic)
        self.use_system = bool(use_system)
        # spoken language for THIS meeting ('' → global setting; 'auto' → detect)
        self.language = (language or "").strip().lower()
        self.state = "idle"
        self.started_at = None
        self.transcript = []             # utterances, ordered by t0
        self.speakers = {"self": self_speaker_label(getattr(app, "config", {}))}
        self.marked_moments = []
        self.scratchpad = ""
        self.summary = ""
        self.decisions = []
        self.action_items = []
        self.hybrid_notes = []
        self.recognized = {}          # {sid: {name, meetings}} — voiceprint hits
        self.speakers_source = "estimated"   # → "diarized" once AssemblyAI turns are applied
        self.audio_url = None
        self.error = None

        self._mic_stream = None
        self._sys_cap = None
        self._mic_chunker = _SourceChunker("self", self._enqueue_chunk)
        self._sys_chunker = _SourceChunker("sys", self._enqueue_chunk)
        self._queue = []                 # pending (source, t0_samples, audio)
        self._queue_lock = threading.Lock()
        self._queue_evt = threading.Event()
        self._worker = None
        self._ticker = None
        self._stop_evt = threading.Event()

        self._paused = False
        self._elapsed_samples = 0        # mic-source sample counter (chunk timeline)
        self._sys_elapsed_samples = 0
        self._mic_level = 0.0
        # Wall-clock elapsed (excluding pauses) — independent of the mic stream,
        # so the timer never freezes if a source drops.
        self._wall_start = None
        self._paused_total = 0.0
        self._pause_started = None
        # Mic watchdog state
        self._last_mic_ts = 0.0
        self._mic_reopen_ts = 0.0
        self._mic_cb = None
        # Mic taps: dictation-during-a-meeting SHARES this mic feed instead of
        # opening a second InputStream on the same device (two owners of one
        # mic is what made "my voice gets ignored" happen — and a failed second
        # open's PortAudio reinit killed the meeting's stream process-wide).
        self._mic_taps = []
        self._sys_speaker_n = 0          # 0 = none yet
        self._sys_last_end = None        # last system utterance end (secs)
        self._audio_parts = []           # (t0_samples, source, audio) for final WAV
        self._audio_lock = threading.Lock()
        self._cloud_ok = False

    # ── lifecycle ─────────────────────────────────────────────────────────────
    def start(self):
        try:
            return self._start()
        except Exception as e:
            logger.error("meeting start failed: %s", e)
            self.state = "failed"
            self.error = str(e)
            return False

    def _start(self):
        import sounddevice as sd
        self.state = "preparing"
        self.started_at = _now_iso()
        self._emit_state()

        # mic — own stream, normalized to 16 kHz mono inside the callback
        def mic_cb(indata, frames, t, status):
            try:
                mono = indata[:, 0].astype(np.float32, copy=True)
                rate = getattr(self, "_mic_rate", SR)
                if rate != SR and len(mono):   # device-native fallback → resample
                    n_out = max(1, int(len(mono) * SR / rate))
                    mono = np.interp(
                        np.linspace(0.0, len(mono) - 1.0, n_out),
                        np.arange(len(mono), dtype=np.float64), mono,
                    ).astype(np.float32)
                # taps (dictation) get the feed even while the MEETING is paused —
                # dictation must keep working regardless of meeting state
                for tap in list(self._mic_taps):
                    try:
                        tap(mono)
                    except Exception:
                        pass
                if self._paused or self.state not in ("recording", "preparing"):
                    return
                self._elapsed_samples += len(mono)
                self._last_mic_ts = time.time()
                try:
                    self._mic_level = float(min(1.0, float(np.abs(mono).max())))
                except Exception:
                    pass
                with self._audio_lock:
                    self._audio_parts.append((self._elapsed_samples - len(mono), "self", mono))
                self._mic_chunker.feed(mono, self._elapsed_samples)
            except Exception:
                pass  # never throw into the audio callback

        if self.use_mic:
            # A macOS audio-device change (AirPods connect/disconnect) leaves
            # PortAudio's cached device list stale → every open fails with
            # AUHAL '!obj' / paInternalError -9986 until PortAudio is
            # re-initialized. Try 16 kHz; on failure re-init PA and retry at the
            # device's CURRENT native rate, resampling to 16 kHz in the callback.
            self._mic_rate = SR

            def open_mic(rate):
                s = sd.InputStream(samplerate=rate, channels=1, dtype="float32",
                                   callback=mic_cb)
                s.start()
                return s

            self._mic_cb = mic_cb  # kept for the watchdog reopen
            try:
                self._mic_stream = open_mic(SR)
            except Exception as e1:
                logger.warning("meeting mic open failed (%s) — reinit PortAudio + native rate", e1)
                try:
                    rec = getattr(self.app, "recorder", None)
                    if not (rec is not None and getattr(rec, "_stream", None) is not None):
                        sd._terminate()   # never while dictation holds a stream
                        sd._initialize()
                    info = sd.query_devices(kind="input")
                    native = int(info.get("default_samplerate") or 48000)
                    self._mic_rate = native
                    self._mic_stream = open_mic(native)
                    logger.info("meeting mic opened at native %dHz (resampling to %d)", native, SR)
                except Exception as e2:
                    logger.warning("meeting mic retry failed (%s)", e2)
                    self._mic_stream = None  # meeting can still run system-audio-only
            self._last_mic_ts = time.time()

        # system audio — fail closed to mic-only
        def sys_cb(audio):
            try:
                if self._paused or self.state not in ("recording", "preparing"):
                    return
                self._sys_elapsed_samples += len(audio)
                with self._audio_lock:
                    self._audio_parts.append((self._sys_elapsed_samples - len(audio), "sys", audio))
                self._sys_chunker.feed(audio, self._sys_elapsed_samples)
            except Exception:
                pass

        if self.use_system:
            try:
                from app.system_audio import SystemAudioCapture, is_supported
                if is_supported():
                    self._sys_cap = SystemAudioCapture(sys_cb)
                    if not self._sys_cap.start():
                        logger.warning("system audio unavailable: %s", self._sys_cap.error)
                        self._sys_cap = None
                else:
                    # A frozen build missing the ScreenCaptureKit pyobjc wrapper
                    # lands here (v1.0.44 shipped that way) — the meeting still
                    # runs mic-only, but it must never be silent about it.
                    logger.warning("system audio unsupported (ScreenCaptureKit "
                                   "unavailable) — recording mic-only")
            except Exception as e:
                logger.warning("system audio skipped: %s", e)
                self._sys_cap = None

        if self._mic_stream is None and self._sys_cap is None:
            self.state = "failed"
            self.error = "No audio source available."
            self._emit_state()
            return False

        # workers
        self._stop_evt.clear()
        self._worker = threading.Thread(target=self._transcribe_loop, daemon=True)
        self._worker.start()
        self._ticker = threading.Thread(target=self._tick_loop, daemon=True)
        self._ticker.start()

        self.state = "recording"
        self._wall_start = time.time()
        self._emit_state()
        self._persist_local()
        threading.Thread(target=self._cloud_insert, daemon=True).start()
        threading.Thread(target=self._notify_start, daemon=True).start()
        return True

    def toggle_pause(self):
        try:
            now = time.time()
            if self.state == "recording":
                self._paused = True
                self._pause_started = now
                self.state = "paused"
            elif self.state == "paused":
                self._paused = False
                if self._pause_started:
                    self._paused_total += now - self._pause_started
                self._pause_started = None
                self.state = "recording"
            self._emit_state()
        except Exception as e:
            logger.debug("pause toggle failed: %s", e)

    def stop(self):
        """Stop capture, drain transcription, assemble + upload audio, push row.
        Runs synchronously on a daemon thread (MeetingManager.stop_async)."""
        try:
            self._stop_impl()
        except Exception as e:
            logger.error("meeting stop failed: %s", e)
            self.state = "failed"
            self.error = str(e)
            self._emit_state()
            self._persist_local()

    def cancel(self):
        """Discard the meeting outright: stop capture immediately and erase
        anything already persisted, skipping transcription drain, upload and
        summary entirely. Unlike stop(), the recording is thrown away — only
        call this once the user has confirmed. Runs on a daemon thread
        (MeetingManager.cancel_active)."""
        try:
            self._cancel_impl()
        except Exception as e:
            logger.error("meeting cancel failed: %s", e)
            self.state = "failed"
            self.error = str(e)
            self._emit_state()

    def _cancel_impl(self):
        if self.state not in ("preparing", "recording", "paused"):
            return
        try:
            if self._mic_stream:
                self._mic_stream.stop()
                self._mic_stream.close()
        except Exception:
            pass
        self._mic_stream = None
        try:
            if self._sys_cap:
                self._sys_cap.stop()
        except Exception:
            pass
        self._sys_cap = None
        # No drain, no upload, no summary — the whole point of Cancel. Just
        # unblock the transcribe worker so it exits its loop.
        with self._queue_lock:
            self._queue = []
        self._stop_evt.set()
        self._queue_evt.set()
        self.state = "cancelled"
        self._emit_state()
        self._discard()

    def _discard(self):
        """Erase every trace of a cancelled meeting — cloud row, cloud audio,
        local WAV, local meta list. Same cleanup as MeetingManager.delete(),
        but callable mid-flight: delete() refuses while a meeting is still in
        an active/processing state, which Cancel needs to override."""
        try:
            cfg = self.app.config
            user_id = cfg.get("sync_user_id", "")
            if user_id and _cloud_gate(cfg):
                try:
                    import httpx
                    from app.sync import SUPABASE_URL, SUPABASE_KEY
                    from app.auth import auth_header
                    storage_hdrs = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
                    httpx.delete(f"{SUPABASE_URL}/rest/v1/meetings?id=eq.{self.id}",
                                 headers=auth_header(cfg), timeout=10)
                    httpx.delete(f"{SUPABASE_URL}/storage/v1/object/meeting-audio/"
                                 f"{user_id}/{self.id}.wav", headers=storage_hdrs, timeout=10)
                except Exception as e:
                    logger.debug("cancelled-meeting cloud cleanup failed: %s", e)
            try:
                p = os.path.join(MEETINGS_DIR, f"{self.id}.wav")
                if os.path.exists(p):
                    os.remove(p)
            except Exception:
                pass
            cfg["meetings"] = [m for m in cfg.get("meetings", []) if m.get("id") != self.id]
            save_config(cfg)
        except Exception as e:
            logger.debug("cancelled-meeting local cleanup failed: %s", e)

    def _stop_impl(self):
        if self.state not in ("recording", "paused", "preparing"):
            return
        self.state = "stopping"
        self._emit_state()
        # INSTANT feedback: the panel HANDS OFF instead of morphing into a
        # summary (MER-46). The summary lives in the dashboard now, so the panel
        # collapses to the ambient bar and says the notes are still being
        # written; clicking it opens the meeting in the Flume window.
        try:
            win = getattr(self.app, "meeting_window", None)
            if win and win.visible:
                win.set_handoff("processing", self.row())
        except Exception:
            pass

        try:
            if self._mic_stream:
                self._mic_stream.stop()
                self._mic_stream.close()
        except Exception:
            pass
        self._mic_stream = None
        try:
            if self._sys_cap:
                self._sys_cap.stop()
        except Exception:
            pass
        self._sys_cap = None

        # flush partial chunks, then drain the queue (bounded wait)
        self._mic_chunker.flush()
        self._sys_chunker.flush()
        deadline = time.time() + 120
        while time.time() < deadline:
            with self._queue_lock:
                empty = not self._queue
            if empty and not self._busy:
                break
            time.sleep(0.25)
        self._stop_evt.set()
        self._queue_evt.set()

        self.state = "processing"
        self._emit_state()

        # audio file → upload (best-effort)
        try:
            if self.app.config.get("meetings_keep_audio", True):
                path = self._write_wav()
                if path:
                    self._upload_audio(path)
        except Exception as e:
            logger.warning("meeting audio save/upload failed: %s", e)

        # Speaker diarization + voice fingerprinting are RETIRED under the
        # two-speaker model (2026-08-28): system audio is one "Them" bucket, so
        # there is nothing to re-partition or auto-name. `_diarize()` stays
        # behind `meetings_diarize_enabled` (now default OFF) for the fixtures.
        try:
            self._diarize()
        except Exception as e:
            logger.debug("diarization skipped: %s", e)

        # post-meeting summary (31e). Silent meeting → ready with empty summary;
        # LLM failure → 'failed' (Summary card shows Retry; transcript is intact).
        if not self.transcript:
            self.summary = ""
            self.state = "ready"
        else:
            parsed = self.run_summary()
            self.state = "ready" if parsed else "failed"
            if not parsed:
                self.error = "Summary generation failed — transcript saved. Retry from the summary view."
        self._emit_state()
        self._persist_local()
        self._cloud_update(final=True)
        # hand the finished meeting to the bar: "Notes ready →" (or "Notes
        # failed"), which opens the dashboard's meeting detail when clicked.
        hidden = True
        try:
            win = getattr(self.app, "meeting_window", None)
            if win and win.visible:
                hidden = False
                win.set_handoff(self.state, self.row())
        except Exception:
            pass
        # The window can be closed mid-`processing` (unlike `stopping`, which
        # collapses to the ambient bar instead of closing) — so if nobody is
        # watching, say the notes landed (IDI-178). Fails closed.
        if hidden:
            self._notify_done()

    def _notify_done(self):
        try:
            ov = getattr(self.app, "overlay", None)
            if not (ov and hasattr(ov, "show_briefly")):
                return
            msg = ("⚠️ Meeting notes failed — retry from Meetings"
                   if self.state == "failed" else "✦ Meeting notes ready")
            self.app._on_main(lambda: ov.show_briefly(msg, duration=3.0))
        except Exception as e:
            logger.debug("meeting done notice skipped: %s", e)

    def run_summary(self):
        """Generate (or regenerate) the structured summary. True on success."""
        try:
            parsed = generate_meeting_summary(
                self.app.config, self.transcript, self.speakers,
                self.scratchpad, self.marked_moments,
                session_language=getattr(self, "language", ""))
            if not parsed:
                return False
            # Names read off the transcript ("thanks Sara" / "I'm Marco") replace
            # placeholder labels only; a renamed speaker also feeds the voiceprint
            # learner so the same person is auto-named next meeting.
            for sid in apply_speaker_names(self.speakers, parsed.get("speaker_names"), parsed):
                try:
                    from app import voiceprint
                    voiceprint.learn_speaker(self.app.config, self.id, self.transcript,
                                             sid, self.speakers.get(sid))
                except Exception:
                    pass
            self.summary = parsed["summary"]
            self.decisions = parsed["decisions"]
            self.action_items = merge_action_done(self.action_items, parsed["action_items"])
            self.hybrid_notes = parsed["hybrid_notes"]
            return True
        except Exception as e:
            logger.error("run_summary failed: %s", e)
            return False

    # ── transcription pipeline ────────────────────────────────────────────────
    _busy = False

    def _enqueue_chunk(self, source, t0_samples, blocks):
        with self._queue_lock:
            self._queue.append((source, t0_samples, blocks))
        self._queue_evt.set()

    def _transcribe_loop(self):
        from app.transcriber import transcribe_with_status
        while not self._stop_evt.is_set() or self._pending():
            self._queue_evt.wait(0.5)
            item = None
            with self._queue_lock:
                if self._queue:
                    item = self._queue.pop(0)
                else:
                    self._queue_evt.clear()
            if item is None:
                continue
            source, t0_samples, blocks = item
            self._busy = True
            try:
                # heavy concat happens HERE, on the worker — never in the audio callback
                audio = np.concatenate(blocks) if isinstance(blocks, list) else blocks
                peak = float(np.abs(audio).max()) if audio.size else 0.0
                if peak < 0.01:
                    continue  # silence gate — matches the dictation pipeline
                # Per-word timestamps (system audio only) let the post-meeting
                # diarization split a chunk at real speaker turns. Best-effort:
                # only the Groq-proxy path returns them; empty otherwise.
                side = {}
                text, status = transcribe_with_status(
                    audio, self.app.config, sample_rate=SR,
                    language=self.language or None,
                    sidecar=side, words=(source != "self"))
                if text and text.strip().lower() in _MEETING_HALLUCINATIONS:
                    logger.debug("meeting: dropped hallucination chunk %r", text)
                    text, status = "", "silent"
                if status != "ok" or not (text or "").strip():
                    continue
                t0 = t0_samples / SR
                t1 = t0 + len(audio) / SR
                speaker = self._speaker_for(source, t0, t1)
                utt = {"speaker": speaker, "t0": round(t0, 2), "t1": round(t1, 2),
                       "text": text.strip()}
                words = side.get("words") if isinstance(side, dict) else None
                if source != "self" and isinstance(words, list) and len(words) >= 2:
                    try:
                        utt["words"] = [[str(w.get("word", "")).strip(),
                                         round(t0 + float(w.get("start", 0)), 2),
                                         round(t0 + float(w.get("end", 0)), 2)]
                                        for w in words if str(w.get("word", "")).strip()]
                    except Exception:
                        utt.pop("words", None)
                self.transcript.append(utt)
                self.transcript.sort(key=lambda u: u["t0"])
                pub = {k: v for k, v in utt.items() if k != "words"}
                self._emit("utterance", dict(pub, speakers=self.speakers, mid=self.id))
                now = time.time()
                if now - getattr(self, "_last_live_push", 0.0) > 4.0:
                    self._last_live_push = now
                    threading.Thread(target=self._cloud_push_live, daemon=True).start()
            except Exception as e:
                logger.debug("chunk transcribe failed: %s", e)
            finally:
                self._busy = False

    def _pending(self):
        with self._queue_lock:
            return bool(self._queue) or self._busy

    def _diarize(self, poll_every=4.0, max_wait=120.0):
        """Post-meeting speaker re-partition. Runs on the end-flow worker thread
        (state is 'working', so a minute of extra latency here is expected time,
        not perceived lag). Every exit path leaves the transcript usable."""
        from app.config import feature_flag
        if not feature_flag(self.app.config, "meetings_diarize_enabled", False):
            return          # retired 2026-08-28 (two-speaker model)
        if not self.audio_url or not self.transcript:
            return
        if not any(u.get("speaker") != "self" for u in self.transcript):
            return          # nothing but the user's own mic — nothing to partition
        from app.groq_proxy import diarize_submit, diarize_poll
        # The meeting's spoken language (or auto-detect) — turn detection on
        # code-switched speech degrades when the model is pinned to English.
        tid = diarize_submit(self.audio_url, self.app.config,
                             language=(self.language or None))
        if not tid:
            return
        deadline, dz = time.time() + max_wait, None
        while time.time() < deadline:
            got = diarize_poll(tid, self.app.config)
            if got is False:
                return
            if got is not None:
                dz = got
                break
            time.sleep(poll_every)
        if not dz:
            logger.warning("diarization timed out after %.0fs — keeping gap labels", max_wait)
            return
        # 1) split chunks at speaker-turn boundaries (needs per-word timestamps;
        #    utterances without them pass through), 2) map turns → speaker ids.
        before = len(self.transcript)
        self.transcript = split_utterances_by_turns(self.transcript, dz)
        new_ids, remap_hint = map_diarized_speakers(self.transcript, dz)
        changed = sum(1 for u, nid in zip(self.transcript, new_ids)
                      if u.get("speaker") != nid)
        self.speakers_source = "diarized"
        logger.info("diarization: %d utterances → %d after turn split", before, len(self.transcript))
        # Rebuild the speakers map around the new partition. A name the user typed
        # mid-meeting follows the id that received the majority of that speaker's
        # utterances; everything else gets the familiar default.
        old_names = dict(self.speakers)
        for u, nid in zip(self.transcript, new_ids):
            u["speaker"] = nid
        fresh = {"self": old_names.get("self") or self_speaker_label(self.app.config)}
        for u in self.transcript:
            sid = u.get("speaker")
            if sid and sid != "self" and sid not in fresh:
                fresh[sid] = f"Speaker {sid[1:]}" if sid.startswith("s") else sid
        for old_sid, new_sid in remap_hint.items():
            name = old_names.get(old_sid, "")
            if name and not name.startswith("Speaker ") and new_sid in fresh:
                fresh[new_sid] = name
        self.speakers = fresh
        logger.info("diarization: %d clusters, %d/%d utterances relabelled",
                    len([s for s in fresh if s != 'self']), changed, len(self.transcript))

    def _speaker_for(self, source, t0, t1):
        if source == "self":
            return "self"
        # system audio: ONE bucket — "Them" (Granola model, 2026-08-28). The
        # silence-gap "new speaker" guess is gone; it split one person in two
        # far more often than it separated two people.
        self._sys_speaker_n = 1
        self.speakers.setdefault("s1", THEM_LABEL)
        self._sys_last_end = t1
        return "s1"

    # ── moments / scratchpad / title (bridge surface) ─────────────────────────
    @property
    def elapsed(self):
        """Wall-clock seconds excluding pauses — never freezes if a source drops."""
        if self._wall_start is None:
            return 0
        ref = self._pause_started if (self._paused and self._pause_started) else time.time()
        return max(0, int(ref - self._wall_start - self._paused_total))

    def mark_moment(self, label=""):
        m = {"t": self.elapsed, "label": (label or "").strip()[:80]}
        self.marked_moments.append(m)
        self._emit("moment", dict(m, mid=self.id))
        return m

    def set_scratchpad(self, text):
        self.scratchpad = str(text or "")

    def set_title(self, title):
        t = (title or "").strip()
        if t:
            self.title = t[:120]
            self._emit_state()

    @property
    def mic_running(self):
        try:
            return self._mic_stream is not None and self._mic_stream.active
        except Exception:
            return False

    def add_mic_tap(self, fn):
        """Register a 16 kHz-mono block consumer (dictation shares the mic)."""
        try:
            if fn not in self._mic_taps:
                self._mic_taps.append(fn)
        except Exception:
            pass

    def remove_mic_tap(self, fn):
        try:
            self._mic_taps.remove(fn)
        except Exception:
            pass

    def rename_speaker(self, speaker_id, name):
        name = (name or "").strip()[:60]
        if speaker_id in self.speakers and name:
            self.speakers[speaker_id] = name
            self._emit("speakers", self.speakers)

    # ── ticker (elapsed + levels → UI, plus the mic watchdog) ─────────────────
    def _tick_loop(self):
        while not self._stop_evt.is_set() and self.state in ("recording", "paused", "preparing"):
            try:
                self._emit("elapsed", {
                    "secs": self.elapsed,
                    "paused": self.state == "paused",
                    "mic": round(self._mic_level, 3),
                    "sys": round(self._sys_cap.level, 3) if self._sys_cap else 0.0,
                    # Windows WASAPI capture reconnects on its own (Rule #76); once it
                    # has given up `.running` is False and `.error` says why. Surface
                    # it (UI may ignore the key) and log ONCE so a mic-only tail is
                    # never silent in the logs.
                    "sysErr": self._sys_audio_state(),
                })
                self._mic_watchdog()
            except Exception:
                pass
            time.sleep(1.0)

    def _sys_audio_state(self):
        """None while system audio is healthy (or not in use); otherwise the
        capture's error string. Logs the transition to 'lost' exactly once."""
        cap = self._sys_cap
        if cap is None:
            return None
        try:
            if cap.running:
                return None
            err = cap.error or "system audio stopped"
        except Exception:
            return None
        if not getattr(self, "_sys_lost_logged", False):
            self._sys_lost_logged = True
            logger.warning("meeting system audio lost — continuing mic-only: %s", err)
        return err

    def _mic_watchdog(self):
        """Reopen the mic if its callbacks went silent (>5 s) while recording —
        a stalled PortAudio stream otherwise leaves the meeting system-audio-only."""
        if not self.use_mic or self.state != "recording" or self._mic_cb is None:
            return
        now = time.time()
        stalled = (now - self._last_mic_ts) > 5.0
        try:
            inactive = self._mic_stream is None or not self._mic_stream.active
        except Exception:
            inactive = True
        if not (stalled or inactive):
            return
        if now - self._mic_reopen_ts < 10.0:   # throttle reopen attempts
            return
        self._mic_reopen_ts = now

        def reopen():
            import sounddevice as sd
            logger.warning("meeting mic watchdog: stream stalled — reopening")
            try:
                if self._mic_stream is not None:
                    try:
                        self._mic_stream.stop()
                        self._mic_stream.close()
                    except Exception:
                        pass
                    self._mic_stream = None
                # sd._terminate() tears down EVERY PortAudio stream in the
                # process — never do it while the dictation Recorder has a live
                # stream (Rule #1).
                rec = getattr(self.app, "recorder", None)
                if not (rec is not None and getattr(rec, "_stream", None) is not None):
                    sd._terminate()
                    sd._initialize()
                info = sd.query_devices(kind="input")
                native = int(info.get("default_samplerate") or 48000)
                for rate in (SR, native):
                    try:
                        s = sd.InputStream(samplerate=rate, channels=1,
                                           dtype="float32", callback=self._mic_cb)
                        s.start()
                        self._mic_rate = rate
                        self._mic_stream = s
                        self._last_mic_ts = time.time()
                        logger.info("meeting mic reopened at %dHz", rate)
                        return
                    except Exception:
                        continue
                logger.warning("meeting mic reopen failed — continuing system-audio-only")
            except Exception as e:
                logger.debug("mic watchdog reopen error: %s", e)
        threading.Thread(target=reopen, daemon=True).start()

    # ── persistence ───────────────────────────────────────────────────────────
    def meta(self):
        return {
            "id": self.id, "title": self.title, "started_at": self.started_at,
            "duration_seconds": self.elapsed, "status": self.state,
            "speakers": self.speakers, "utterances": len(self.transcript),
            "audio_url": self.audio_url, "cloud": self._cloud_ok,
            # "diarized" (real who-spoke-when) vs "estimated" (90 s-gap guess).
            # LOCAL-ONLY for now — no cloud column; get_meeting() merges it in.
            "speakers_source": getattr(self, "speakers_source", "estimated"),
        }

    def row(self):
        cfg = self.app.config
        return {
            "id": self.id,
            "user_id": cfg.get("sync_user_id", "") or "",
            "title": self.title,
            "started_at": self.started_at,
            "ended_at": _now_iso() if self.state in ("ready", "failed", "processing") else None,
            "duration_seconds": self.elapsed,
            "audio_url": self.audio_url,
            "transcript": self._public_transcript(),
            "speakers": self.speakers,
            "scratchpad": self.scratchpad,
            "summary": self.summary,
            "decisions": self.decisions,
            "action_items": self.action_items,
            "marked_moments": self.marked_moments,
            "hybrid_notes": self.hybrid_notes,
            "recognized": getattr(self, "recognized", {}) or {},
            # cloud column added 2026-08-27 (migration meetings_speakers_source)
            "speakers_source": getattr(self, "speakers_source", "estimated"),
            "device_id": cfg.get("sync_device_name", "") or "",
            "device_name": cfg.get("sync_device_name", "") or "",
            "status": {"ready": "ready", "failed": "failed"}.get(self.state, "processing"),
            "live": self.state in ("preparing", "recording", "paused"),
            "updated_at": _now_iso(),
            # MER-31: stamped from the user's current setting at capture time —
            # changing the setting later only affects meetings captured after
            # the change, not retroactively. 0/None = never expire (default).
            "retention_days": cfg.get("meetings_keep_audio_days") or 0,
        }

    def _public_transcript(self):
        """Transcript as persisted/synced: per-word timestamps (`words`) are a
        transient diarization aid and never leave the session."""
        return [{k: v for k, v in u.items() if k != "words"} if "words" in u else u
                for u in self.transcript]

    def _persist_local(self):
        try:
            cfg = self.app.config
            lst = [m for m in cfg.get("meetings", []) if m.get("id") != self.id]
            lst.insert(0, self.meta())
            cfg["meetings"] = lst[:MEETINGS_CAP]
            save_config(cfg)
        except Exception as e:
            logger.debug("meeting local persist failed: %s", e)

    def _notify_start(self):
        """Tell the user's other devices a meeting just started (push). Best-effort,
        fires the notify-meeting-start edge function; never blocks capture."""
        try:
            uid = self.app.config.get("sync_user_id")
            if not uid or not _cloud_gate(self.app.config):
                return
            import httpx
            from app.sync import SUPABASE_URL, SUPABASE_KEY
            httpx.post(
                f"{SUPABASE_URL}/functions/v1/notify-meeting-start",
                headers={"apikey": SUPABASE_KEY,
                         "Authorization": f"Bearer {SUPABASE_KEY}",
                         "Content-Type": "application/json"},
                json={"user_id": uid, "meeting_id": self.id, "title": self.title,
                      "source": self.app.config.get("sync_device_name", "your Mac")},
                timeout=8)
        except Exception as e:
            logger.debug("meeting start notify failed: %s", e)

    def _cloud_push_live(self):
        """Push just the live-mirror fields to the cloud so a phone can watch the
        transcript stream in. Transcript-only PATCH (never touches scratchpad —
        mobile owns that during the meeting). Fails closed; throttled by caller."""
        try:
            if not _cloud_gate(self.app.config) or not self._cloud_ok:
                return
            import httpx
            from app.sync import SUPABASE_URL
            from app.auth import auth_header
            httpx.patch(
                f"{SUPABASE_URL}/rest/v1/meetings?id=eq.{self.id}",
                headers=auth_header(self.app.config, json=True),
                json={"transcript": self._public_transcript(), "speakers": self.speakers,
                      "duration_seconds": self.elapsed, "live": True,
                      "status": "processing", "updated_at": _now_iso()}, timeout=10)
        except Exception as e:
            logger.debug("meeting live push failed: %s", e)

    def _cloud_insert(self):
        try:
            if not _cloud_gate(self.app.config):
                return
            import httpx
            from app.sync import SUPABASE_URL
            from app.auth import auth_header
            r = httpx.post(
                f"{SUPABASE_URL}/rest/v1/meetings",
                headers={**auth_header(self.app.config, json=True),
                         "Prefer": "resolution=merge-duplicates"},
                content=json.dumps(self.row(), default=str), timeout=15)
            self._cloud_ok = r.status_code in (200, 201)
        except Exception as e:
            logger.debug("meeting cloud insert failed: %s", e)

    def _cloud_update(self, final=False):
        try:
            if not _cloud_gate(self.app.config):
                return
            import httpx
            from app.sync import SUPABASE_URL
            from app.auth import auth_header
            row = self.row()
            r = httpx.patch(
                f"{SUPABASE_URL}/rest/v1/meetings?id=eq.{self.id}",
                headers=auth_header(self.app.config, json=True),
                content=json.dumps(row, default=str), timeout=20)
            if r.status_code in (200, 204) and not self._cloud_ok:
                # row may not exist yet (insert failed earlier) — upsert it
                self._cloud_insert()
            self._cloud_ok = self._cloud_ok or r.status_code in (200, 204)
            self._persist_local()
        except Exception as e:
            logger.debug("meeting cloud update failed: %s", e)

    # ── audio assembly ────────────────────────────────────────────────────────
    def _write_wav(self):
        """Mix mic + system parts onto one 16 kHz mono timeline → int16 WAV."""
        try:
            with self._audio_lock:
                parts = list(self._audio_parts)
                self._audio_parts = []
            if not parts:
                return None
            total = max(t0 + len(a) for t0, _s, a in parts)
            mix = np.zeros(total, dtype=np.float32)
            for t0, _source, a in parts:
                mix[t0:t0 + len(a)] += a
            peak = float(np.abs(mix).max()) or 1.0
            if peak > 0.98:
                mix *= 0.98 / peak
            os.makedirs(MEETINGS_DIR, exist_ok=True)
            path = os.path.join(MEETINGS_DIR, f"{self.id}.wav")
            with wave.open(path, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(SR)
                w.writeframes((mix * 32767).astype(np.int16).tobytes())
            return path
        except Exception as e:
            logger.warning("meeting wav write failed: %s", e)
            return None

    def _upload_audio(self, path):
        try:
            user_id = self.app.config.get("sync_user_id", "")
            if not user_id or not _cloud_gate(self.app.config):
                return
            import httpx
            from app.sync import SUPABASE_URL, SUPABASE_KEY
            object_path = f"{user_id}/{self.id}.wav"
            with open(path, "rb") as f:
                data = f.read()
            r = httpx.post(
                f"{SUPABASE_URL}/storage/v1/object/meeting-audio/{object_path}",
                headers={"apikey": SUPABASE_KEY,
                         "Authorization": f"Bearer {SUPABASE_KEY}",
                         "Content-Type": "audio/wav",
                         "x-upsert": "true"},
                content=data, timeout=120)
            if r.status_code in (200, 201):
                # Bare object path, not a public URL — meeting-audio is private
                # (MER-27); consumers sign a short-lived URL at read time.
                self.audio_url = object_path
        except Exception as e:
            logger.debug("meeting audio upload failed: %s", e)

    # ── events ────────────────────────────────────────────────────────────────
    def _emit(self, event, payload):
        try:
            win = getattr(self.app, "meeting_window", None)
            if win:
                win.emit(event, payload)
        except Exception:
            pass

    def _emit_state(self):
        self._emit("state", {
            "id": self.id, "state": self.state, "title": self.title,
            "elapsed": self.elapsed, "speakers": self.speakers,
            "error": self.error,
        })
        try:  # keep the menubar item text in sync (main thread)
            refresh = getattr(self.app, "_refresh_meeting_menu", None)
            if refresh:
                self.app._on_main(refresh)
        except Exception:
            pass
        try:  # tell the dashboard (separate window) to refresh its meetings list
            if self.state in ("recording", "ready", "failed"):
                dash = getattr(self.app, "dashboard", None)
                if dash and hasattr(dash, "_emit"):
                    dash._emit("meetingsUpdated", {"id": self.id, "state": self.state})
        except Exception:
            pass


class MeetingManager:
    """App-level singleton: owns the active session + list/get plumbing."""

    def __init__(self, app):
        self.app = app
        self.session = None

    @property
    def active(self):
        s = self.session
        return s if s and s.state in ("preparing", "recording", "paused", "stopping") else None

    @property
    def processing(self):
        """The session is past capture but STILL WORKING (drain → upload →
        summary). Deliberately separate from `active`, whose meaning ("audio is
        being captured") gates the mic/HUD/menubar — this one only answers "is
        it safe to walk away from the window?" (IDI-178)."""
        s = self.session
        return s if s and s.state in ("stopping", "processing") else None

    def start(self, title="", use_mic=True, use_system=True, language=""):
        try:
            if self.active:
                return {"ok": False, "error": "A meeting is already recording."}
            if not self.app.config.get("meetings_enabled", True):
                return {"ok": False, "error": "Meetings are disabled in Settings."}
            self.session = MeetingSession(self.app, title, use_mic=use_mic,
                                          use_system=use_system, language=language)
            ok = self.session.start()
            return {"ok": ok, "id": self.session.id,
                    "error": self.session.error if not ok else None}
        except Exception as e:
            logger.error("manager start failed: %s", e)
            return {"ok": False, "error": str(e)}

    def delete(self, meeting_id):
        """Remove a meeting everywhere: cloud row, cloud audio, local WAV, local meta."""
        try:
            s = self.session
            if s and s.id == meeting_id and s.state in (
                    "preparing", "recording", "paused", "stopping", "processing"):
                # deleting mid-pipeline races the drain/upload/summary worker,
                # which would re-upsert a zombie row afterwards
                return {"ok": False, "error": "Still processing — try again in a moment."}
            cfg = self.app.config
            user_id = cfg.get("sync_user_id", "")
            if user_id and _cloud_gate(cfg):
                try:
                    import httpx
                    from app.sync import SUPABASE_URL, SUPABASE_KEY
                    from app.auth import auth_header
                    storage_hdrs = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}
                    httpx.delete(f"{SUPABASE_URL}/rest/v1/meetings?id=eq.{meeting_id}",
                                 headers=auth_header(cfg), timeout=10)
                    httpx.delete(f"{SUPABASE_URL}/storage/v1/object/meeting-audio/"
                                 f"{user_id}/{meeting_id}.wav", headers=storage_hdrs, timeout=10)
                except Exception as e:
                    logger.debug("cloud delete failed: %s", e)
            try:
                p = os.path.join(MEETINGS_DIR, f"{meeting_id}.wav")
                if os.path.exists(p):
                    os.remove(p)
            except Exception:
                pass
            cfg["meetings"] = [m for m in cfg.get("meetings", [])
                               if m.get("id") != meeting_id]
            save_config(cfg)
            if self.session and self.session.id == meeting_id:
                self.session = None
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def stop_async(self):
        try:
            s = self.active
            if not s:
                return {"ok": False, "error": "No active meeting."}
            threading.Thread(target=s.stop, daemon=True).start()
            return {"ok": True, "id": s.id}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def cancel_active(self):
        """Discard the live meeting — see MeetingSession.cancel(). `active`
        already excludes any state cancel() would set (`cancelled`), so no
        extra bookkeeping is needed here to free the manager up for a new
        meeting once the thread flips the state."""
        try:
            s = self.active
            if not s:
                return {"ok": False, "error": "No active meeting."}
            threading.Thread(target=s.cancel, daemon=True).start()
            return {"ok": True, "id": s.id}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def list_meetings(self):
        try:
            a = self.active
            # Pull the shared cloud list into the local cache once every few
            # seconds so meetings recorded on other devices (mobile, other
            # desktop) appear here too. Fail-closed: cloud outage → local only.
            self._hydrate_from_cloud_if_stale()
            metas = [dict(m, speakers=with_self_name(m.get("speakers") or {}, self.app.config))
                     if isinstance(m, dict) else m
                     for m in self.app.config.get("meetings", [])]
            return {"ok": True,
                    "meetings": metas,
                    "opened": list(self.app.config.get("meetings_opened") or []),
                    "active_id": a.id if a else None,
                    "active_title": a.title if a else None,
                    "active_elapsed": a.elapsed if a else 0,
                    "active_state": a.state if a else None}
        except Exception as e:
            return {"ok": False, "error": str(e), "meetings": []}

    _CLOUD_LIST_TTL_S = 30.0
    _cloud_list_hydrated_at = 0.0

    def _hydrate_from_cloud_if_stale(self):
        """Merge recent cloud meeting rows into config['meetings'] so this
        device sees meetings recorded elsewhere (mobile, other desktop).
        Synchronous but bounded (short httpx timeout inside
        `_fetch_meeting_rows`); throttled to at most once per TTL.
        Any failure is silently swallowed — local list is authoritative
        as a fallback."""
        try:
            user_id = self.app.config.get("sync_user_id", "")
            if not user_id:
                return
            now = time.time()
            if (now - self._cloud_list_hydrated_at) < self._CLOUD_LIST_TTL_S:
                return
            self._cloud_list_hydrated_at = now
            rows = _fetch_meeting_rows(self.app.config, limit=MEETINGS_CAP)
            if not rows:
                return
            # Convert each cloud row into the compact meta shape stored locally.
            cloud_metas = []
            for r in rows:
                try:
                    cloud_metas.append({
                        "id": r.get("id"),
                        "title": r.get("title") or "",
                        "started_at": r.get("started_at") or "",
                        "duration_seconds": r.get("duration_seconds") or 0,
                        "status": r.get("status") or "ready",
                        "speakers": r.get("speakers") or {},
                        "utterances": len(r.get("transcript") or []),
                        "audio_url": r.get("audio_url") or "",
                        "cloud": True,
                    })
                except Exception:
                    continue
            # Merge: local wins on same id (active session may be more current),
            # then cloud fills in the rest. Sort newest first, cap.
            local = list(self.app.config.get("meetings", []))
            by_id = {m.get("id"): m for m in local if m.get("id")}
            for cm in cloud_metas:
                if cm.get("id") and cm["id"] not in by_id:
                    by_id[cm["id"]] = cm
            merged = list(by_id.values())
            merged.sort(key=lambda m: m.get("started_at") or "", reverse=True)
            merged = merged[:MEETINGS_CAP]
            self.app.config["meetings"] = merged
            try:
                save_config(self.app.config)
            except Exception as e:
                logger.debug("meetings cache save failed: %s", e)
        except Exception as e:
            logger.debug("meetings hydrate skipped: %s", e)

    def retry_summary(self, meeting_id):
        """Regenerate the summary — for the in-memory session when it matches,
        else from the cloud row (works after an app restart)."""
        try:
            s = self.session
            if s and s.id == meeting_id:
                def rerun():
                    s.state = "processing"
                    s._emit_state()
                    ok = s.run_summary()
                    s.state = "ready" if ok else "failed"
                    s._emit_state()
                    s._persist_local()
                    s._cloud_update(final=True)
                    # The retry button lives in the dashboard's detail view now
                    # (MER-46) and _emit_state already told it to refresh — the
                    # panel has no summary to hand a row to.
                threading.Thread(target=rerun, daemon=True).start()
                return {"ok": True}

            got = self.get_meeting(meeting_id)
            if not got.get("ok"):
                return got
            row = got["meeting"]

            def rerun_row():
                try:
                    parsed = generate_meeting_summary(
                        self.app.config, row.get("transcript", []),
                        row.get("speakers", {}), row.get("scratchpad", ""),
                        row.get("marked_moments", []))
                    speakers = dict(row.get("speakers") or {})
                    if parsed:
                        apply_speaker_names(speakers, parsed.get("speaker_names"), parsed)
                    patch = ({"summary": parsed["summary"], "decisions": parsed["decisions"],
                              "action_items": merge_action_done(
                                  row.get("action_items"), parsed["action_items"]),
                              "hybrid_notes": parsed["hybrid_notes"], "speakers": speakers,
                              "status": "ready", "updated_at": _now_iso()}
                             if parsed else {"status": "failed", "updated_at": _now_iso()})
                    row.update(patch)
                    if _cloud_gate(self.app.config):
                        import httpx
                        from app.sync import SUPABASE_URL
                        from app.auth import auth_header
                        httpx.patch(
                            f"{SUPABASE_URL}/rest/v1/meetings?id=eq.{meeting_id}",
                            headers=auth_header(self.app.config, json=True),
                            content=json.dumps(patch, default=str), timeout=20)
                    # refresh local metadata status
                    cfg = self.app.config
                    for m in cfg.get("meetings", []):
                        if m.get("id") == meeting_id:
                            m["status"] = patch["status"]
                    save_config(cfg)
                    # Tell the DASHBOARD (MER-46): a retry started from its detail
                    # view, and no state event covers this path.
                    try:
                        dash = getattr(self.app, "dashboard", None)
                        if dash and hasattr(dash, "_emit"):
                            dash._emit("meetingsUpdated",
                                       {"id": meeting_id, "state": patch["status"]})
                    except Exception:
                        pass
                except Exception as e:
                    logger.error("retry summary (row) failed: %s", e)
            threading.Thread(target=rerun_row, daemon=True).start()
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _mutate_meeting_field(self, meeting_id, field, mutate):
        """Load → mutate → save one jsonb LIST field of a meeting row.

        `mutate(list) -> list | None` (None = index out of range / no-op).
        Local trimmed rows are only touched when they actually carry the
        field; the cloud copy is always fetched before writing so we never
        overwrite a list we didn't load (the action-items wipe lesson)."""
        try:
            wrote = False
            # live session first (marks/action items can be edited mid-meeting)
            s = self.session
            if s and s.id == meeting_id:
                cur = getattr(s, field, None)
                if isinstance(cur, list):
                    new = mutate(list(cur))
                    if new is not None:
                        setattr(s, field, new)
                        wrote = True
            for m in self.app.config.get("meetings", []):
                if m.get("id") == meeting_id and m.get(field):
                    new = mutate(list(m[field]))
                    if new is not None:
                        m[field] = new
                        save_config(self.app.config)
                        wrote = True
                    break
            if _cloud_gate(self.app.config):
                import httpx
                from app.sync import SUPABASE_URL
                from app.auth import auth_header
                hdrs = auth_header(self.app.config)
                r = httpx.get(
                    f"{SUPABASE_URL}/rest/v1/meetings?id=eq.{meeting_id}"
                    f"&select={field}&limit=1", headers=hdrs, timeout=10)
                rows = r.json() if r.status_code == 200 else []
                if rows:
                    new = mutate(list(rows[0].get(field) or []))
                    if new is not None:
                        httpx.patch(
                            f"{SUPABASE_URL}/rest/v1/meetings?id=eq.{meeting_id}",
                            headers={**hdrs, "Content-Type": "application/json"},
                            json={field: new}, timeout=10)
                        wrote = True
            return {"ok": True} if wrote else {"ok": False, "error": "not found"}
        except Exception as e:
            logger.warning("mutate %s failed: %s", field, e)
            return {"ok": False, "error": str(e)}

    def set_transcript_text(self, meeting_id, index, text):
        """Inline transcript edit (widget 33a) — flags the segment `edited`."""
        index, text = int(index), str(text)

        def mut(items):
            if 0 <= index < len(items):
                items[index]["text"] = text
                items[index]["edited"] = True
                return items
            return None
        return self._mutate_meeting_field(meeting_id, "transcript", mut)

    def delete_marked_moment(self, meeting_id, index):
        """Delete one bookmark (widget 33b)."""
        index = int(index)

        def mut(items):
            if 0 <= index < len(items):
                items.pop(index)
                return items
            return None
        return self._mutate_meeting_field(meeting_id, "marked_moments", mut)

    def set_speaker_name(self, meeting_id, sid, name):
        """Rename a speaker from the SUMMARY view (widget 33d). Live sessions go
        through rename_speaker; finished meetings update local meta + cloud row
        and feed the voice-fingerprint learner from the local WAV."""
        try:
            name = str(name or "").strip()
            if not name:
                return {"ok": False, "error": "empty name"}
            s = self.session
            if s and s.id == meeting_id:
                return self.rename_speaker(sid, name)
            got = self.get_meeting(meeting_id)
            if not got.get("ok"):
                return got
            row = got["meeting"]
            speakers = dict(row.get("speakers") or {})
            speakers[sid] = name
            for m in self.app.config.get("meetings", []):
                if m.get("id") == meeting_id:
                    m["speakers"] = speakers
                    break
            save_config(self.app.config)
            if _cloud_gate(self.app.config):
                import httpx
                from app.sync import SUPABASE_URL
                from app.auth import auth_header
                httpx.patch(
                    f"{SUPABASE_URL}/rest/v1/meetings?id=eq.{meeting_id}",
                    headers=auth_header(self.app.config, json=True),
                    json={"speakers": speakers}, timeout=10)
            learned = False
            try:
                from app import voiceprint
                learned = voiceprint.learn_speaker(
                    self.app.config, meeting_id, row.get("transcript") or [], sid, name)
            except Exception:
                pass
            return {"ok": True, "learned": bool(learned)}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def get_meeting_notes(self, meeting_id, regenerate=False):
        """Full AI meeting notes (markdown). Cached in the row's notes_md;
        generated on first open (cost rule: LLM only for meetings you read)."""
        try:
            got = self.get_meeting(meeting_id)
            if not got.get("ok"):
                return got
            row = got["meeting"]
            if row.get("status") == "processing":
                return {"ok": False, "error": "Meeting is still processing."}
            cached = (row.get("notes_md") or "").strip()
            if cached and not regenerate:
                return {"ok": True, "notes_md": cached, "cached": True}
            s = self.session
            lang = s.language if (s and s.id == meeting_id) else ""
            notes = generate_meeting_notes(self.app.config, row, session_language=lang)
            if not notes:
                return {"ok": False, "error": "Could not generate notes — try again."}
            if s and s.id == meeting_id:
                s.notes_md = notes
            if _cloud_gate(self.app.config):
                try:
                    import httpx
                    from app.sync import SUPABASE_URL
                    from app.auth import auth_header
                    httpx.patch(
                        f"{SUPABASE_URL}/rest/v1/meetings?id=eq.{meeting_id}",
                        headers=auth_header(self.app.config, json=True),
                        json={"notes_md": notes}, timeout=15)
                except Exception as e:
                    logger.debug("notes_md persist failed: %s", e)
            return {"ok": True, "notes_md": notes, "cached": False}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def set_meeting_pinned(self, meeting_id, pinned):
        """Pin/unpin a meeting (widget 33j). Local meta + cloud column."""
        try:
            pinned = bool(pinned)
            for m in self.app.config.get("meetings", []):
                if m.get("id") == meeting_id:
                    m["pinned"] = pinned
                    break
            save_config(self.app.config)
            if _cloud_gate(self.app.config):
                import httpx
                from app.sync import SUPABASE_URL
                from app.auth import auth_header
                httpx.patch(
                    f"{SUPABASE_URL}/rest/v1/meetings?id=eq.{meeting_id}",
                    headers=auth_header(self.app.config, json=True),
                    json={"pinned": pinned}, timeout=10)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def set_meeting_title_by_id(self, meeting_id, title):
        """Rename a meeting BY ID — local meta + cloud column (MER-46).

        `DashboardApi.set_meeting_title` only ever addressed the live session,
        which was fine while the summary lived in the meeting panel. The summary
        now lives in the dashboard, where the meeting on screen is usually a past
        one, so the id form is what the title field needs. The live session is
        still handled first so renaming an in-progress meeting keeps emitting
        state to the bar/live screen."""
        try:
            title = str(title or "").strip()
            if not title:
                return {"ok": False, "error": "empty title"}
            s = self.session
            if s and s.id == meeting_id:
                s.set_title(title)
                return {"ok": True}
            for m in self.app.config.get("meetings", []):
                if m.get("id") == meeting_id:
                    m["title"] = title[:120]
                    break
            save_config(self.app.config)
            if _cloud_gate(self.app.config):
                import httpx
                from app.sync import SUPABASE_URL
                from app.auth import auth_header
                httpx.patch(
                    f"{SUPABASE_URL}/rest/v1/meetings?id=eq.{meeting_id}",
                    headers=auth_header(self.app.config, json=True),
                    json={"title": title[:120]}, timeout=10)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def mark_meeting_opened(self, meeting_id):
        """Read-tracking for the NEW indicator (widget 33j). Local-only."""
        try:
            opened = self.app.config.get("meetings_opened") or []
            if meeting_id not in opened:
                opened = ([meeting_id] + opened)[:200]
                self.app.config["meetings_opened"] = opened
                save_config(self.app.config)
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def regenerate_hybrid(self, meeting_id, index):
        """Regenerate ONE hybrid-note AI addition (widget 33i). Fetches the row
        (transcript + note line), runs the focused LLM call, persists."""
        try:
            index = int(index)
            got = self.get_meeting(meeting_id)
            if not got.get("ok"):
                return got
            row = got["meeting"]
            notes = row.get("hybrid_notes") or []
            if not (0 <= index < len(notes)):
                return {"ok": False, "error": "no such note"}
            new = regenerate_hybrid_addition(
                self.app.config, row.get("transcript") or [],
                row.get("speakers") or {}, notes[index].get("user_line", ""))
            if new is None:
                return {"ok": False, "error": "regenerate failed"}

            def mut(items):
                if 0 <= index < len(items):
                    items[index]["ai_addition"] = new
                    return items
                return None
            self._mutate_meeting_field(meeting_id, "hybrid_notes", mut)
            return {"ok": True, "ai_addition": new}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def set_mark_note(self, meeting_id, index, note):
        """Attach/edit the user note on a bookmark (widget 33b)."""
        index, note = int(index), str(note)

        def mut(items):
            if 0 <= index < len(items):
                if note.strip():
                    items[index]["note"] = note.strip()
                else:
                    items[index].pop("note", None)
                return items
            return None
        return self._mutate_meeting_field(meeting_id, "marked_moments", mut)

    def set_action_item_text(self, meeting_id, index, text):
        """Inline action-item edit (widget 33c) — flags the item `edited`."""
        index, text = int(index), str(text)

        def mut(items):
            if 0 <= index < len(items):
                items[index]["task"] = text
                items[index]["edited"] = True
                return items
            return None
        return self._mutate_meeting_field(meeting_id, "action_items", mut)

    def delete_action_item(self, meeting_id, index):
        """Remove a wrongly-extracted action item (widget 33c)."""
        index = int(index)

        def mut(items):
            if 0 <= index < len(items):
                items.pop(index)
                return items
            return None
        return self._mutate_meeting_field(meeting_id, "action_items", mut)

    def set_action_item_done(self, meeting_id, index, done):
        """Persist an action-item checkbox (widget 33c). Local meta always;
        cloud row too when signed in. Fails closed — never raises."""
        try:
            index = int(index)
            done = bool(done)
            # Local meta first — but local rows may be trimmed (no action_items
            # key at all). NEVER write a list we didn't actually load: patching
            # [] would wipe the cloud's items.
            items = None
            for m in self.app.config.get("meetings", []):
                if m.get("id") == meeting_id:
                    if m.get("action_items"):
                        items = m["action_items"]
                        if 0 <= index < len(items):
                            items[index]["done"] = done
                        from app.config import save_config
                        save_config(self.app.config)
                    break
            if _cloud_gate(self.app.config):
                import httpx
                from app.sync import SUPABASE_URL
                from app.auth import auth_header
                if not items:
                    r = httpx.get(
                        f"{SUPABASE_URL}/rest/v1/meetings?id=eq.{meeting_id}"
                        "&select=action_items&limit=1",
                        headers=auth_header(self.app.config), timeout=10)
                    rows = r.json() if r.status_code == 200 else []
                    items = (rows[0].get("action_items") if rows else None) or []
                    if 0 <= index < len(items):
                        items[index]["done"] = done
                if items:   # only patch when there is something real to write
                    httpx.patch(
                        f"{SUPABASE_URL}/rest/v1/meetings?id=eq.{meeting_id}",
                        headers=auth_header(self.app.config, json=True),
                        json={"action_items": items}, timeout=10)
            return {"ok": True}
        except Exception as e:
            logger.warning("set_action_item_done failed: %s", e)
            return {"ok": False, "error": str(e)}

    def get_meeting(self, meeting_id):
        """Active session first, then cloud row, then local metadata."""
        try:
            s = self.session
            if s and s.id == meeting_id:
                return {"ok": True, "meeting": self._named(s.row()), "live": bool(self.active)}
            if _cloud_gate(self.app.config):
                import httpx
                from app.sync import SUPABASE_URL
                from app.auth import auth_header
                r = httpx.get(
                    f"{SUPABASE_URL}/rest/v1/meetings?id=eq.{meeting_id}&limit=1",
                    headers=auth_header(self.app.config), timeout=10)
                rows = r.json() if r.status_code == 200 else []
                if rows:
                    row = rows[0]
                    # speakers_source lives only in local metadata (no cloud column)
                    for m in self.app.config.get("meetings", []):
                        if m.get("id") == meeting_id and m.get("speakers_source"):
                            row = dict(row, speakers_source=m["speakers_source"])
                            break
                    return {"ok": True, "meeting": self._named(row), "live": False}
            for m in self.app.config.get("meetings", []):
                if m.get("id") == meeting_id:
                    return {"ok": True, "meeting": self._named(m), "live": False}
            return {"ok": False, "error": "not found"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _named(self, row):
        """Read-side view of a meeting row with the "self" speaker shown as the
        signed-in user's name (legacy rows persisted "You"). Never mutates the
        stored row; falls back to the row itself on any error."""
        try:
            if isinstance(row, dict):
                return dict(row, speakers=with_self_name(row.get("speakers") or {}, self.app.config))
        except Exception:
            pass
        return row
