"""Voice fingerprinting (widget 33d) — LOCAL-ONLY speaker recognition.

At meeting end each speaker gets a lightweight embedding (mean+std of log-mel
frames over their transcript segments in the meeting WAV, numpy only — no ML
deps). Named speakers update a rolling per-name print in
``config['voice_prints']``; still-unnamed speakers ("Speaker N") are auto-named
when they match a stored print decisively.

Privacy: prints NEVER leave the machine (config only — same posture as
"meeting text never goes to analytics"). Everything here fails closed: any
error returns {} and the meeting pipeline proceeds untouched.
"""
import logging
import os
import re
import wave

import numpy as np

logger = logging.getLogger("verbal.voiceprint")

SR = 16000
N_FFT = 512
HOP = 160            # 10 ms
WIN = 400            # 25 ms
N_MELS = 40
MIN_SPEAKER_SECS = 5.0    # need this much speech before trusting a print
MAX_SPEAKER_SECS = 60.0   # cap per meeting (plenty for a mean/std print)
MATCH_THRESHOLD = 0.92    # cosine — conservative for a filterbank print
MATCH_MARGIN = 0.02       # best must beat runner-up by this
MAX_PRINT_N = 50          # running-average cap

_DEFAULT_NAME = re.compile(r"^\s*speaker\s*\d+\s*$", re.I)

_MEL_FB = None


def _mel_filterbank():
    global _MEL_FB
    if _MEL_FB is not None:
        return _MEL_FB
    def hz2mel(f):
        return 2595.0 * np.log10(1.0 + f / 700.0)
    def mel2hz(m):
        return 700.0 * (10.0 ** (m / 2595.0) - 1.0)
    pts = mel2hz(np.linspace(hz2mel(50.0), hz2mel(SR / 2.0), N_MELS + 2))
    bins = np.floor((N_FFT + 1) * pts / SR).astype(int)
    fb = np.zeros((N_MELS, N_FFT // 2 + 1), dtype=np.float32)
    for i in range(N_MELS):
        a, b, c = bins[i], bins[i + 1], bins[i + 2]
        if b > a:
            fb[i, a:b] = np.linspace(0, 1, b - a, endpoint=False)
        if c > b:
            fb[i, b:c] = np.linspace(1, 0, c - b, endpoint=False)
    _MEL_FB = fb
    return fb


def _load_wav(path):
    with wave.open(path, "rb") as w:
        sr = w.getframerate()
        ch = w.getnchannels()
        data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    x = data.astype(np.float32) / 32768.0
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    if sr != SR and sr > 0:      # meetings write 16 k, but stay tolerant
        n = int(len(x) * SR / sr)
        x = np.interp(np.linspace(0, len(x), n, endpoint=False),
                      np.arange(len(x)), x).astype(np.float32)
    return x


def _logmel_frames(x):
    if len(x) < WIN:
        return None
    n = 1 + (len(x) - WIN) // HOP
    idx = np.arange(WIN)[None, :] + HOP * np.arange(n)[:, None]
    frames = x[idx] * np.hanning(WIN).astype(np.float32)
    spec = np.abs(np.fft.rfft(frames, N_FFT, axis=1)) ** 2
    mel = spec @ _mel_filterbank().T
    logmel = np.log10(np.maximum(mel, 1e-10))
    # drop near-silent frames so pauses don't wash the print out
    energy = logmel.mean(axis=1)
    keep = energy > (energy.max() - 2.5)
    return logmel[keep] if keep.any() else logmel


def _embed(x, segments):
    parts, total = [], 0.0
    for t0, t1 in segments:
        if total >= MAX_SPEAKER_SECS:
            break
        a, b = int(t0 * SR), int(min(t1, t0 + 20.0) * SR)
        if b - a < int(0.4 * SR):
            continue
        seg = x[a:min(b, len(x))]
        if len(seg):
            parts.append(seg)
            total += len(seg) / SR
    if total < MIN_SPEAKER_SECS:
        return None
    frames = _logmel_frames(np.concatenate(parts))
    if frames is None or len(frames) < 40:
        return None
    vec = np.concatenate([frames.mean(axis=0), frames.std(axis=0)])
    nrm = np.linalg.norm(vec)
    return (vec / nrm).astype(np.float32) if nrm > 0 else None


def _cosine(a, b):
    return float(np.dot(a, b))


def _update_print(prints, name, emb):
    p = prints.get(name)
    if p and p.get("vec"):
        n = min(int(p.get("n", 1)), MAX_PRINT_N)
        vec = (np.asarray(p["vec"], dtype=np.float32) * n + emb) / (n + 1)
        nrm = np.linalg.norm(vec)
        if nrm > 0:
            vec = vec / nrm
        prints[name] = {"vec": [round(float(v), 5) for v in vec], "n": n + 1}
    else:
        prints[name] = {"vec": [round(float(v), 5) for v in emb], "n": 1}


def learn_speaker(config, meeting_id, transcript, sid, name):
    """Post-meeting rename → learn that speaker's print from the local WAV.
    This closes the fingerprint loop for the common flow (naming people while
    reading the summary). Local-only; fails closed to False."""
    try:
        name = (name or "").strip()
        if not name or _DEFAULT_NAME.match(name) or sid == "self":
            return False
        from app.meetings import MEETINGS_DIR
        path = os.path.join(MEETINGS_DIR, f"{meeting_id}.wav")
        if not os.path.exists(path):
            return False
        segs = [(float(u.get("t0", 0)), float(u.get("t1", u.get("t0", 0))))
                for u in (transcript or []) if u.get("speaker") == sid]
        if not segs:
            return False
        emb = _embed(_load_wav(path), segs)
        if emb is None:
            return False
        prints = dict(config.get("voice_prints") or {})
        _update_print(prints, name, emb)
        config["voice_prints"] = prints
        from app.config import save_config
        save_config(config)
        logger.info("voiceprint: learned %r from post-meeting rename", name)
        return True
    except Exception as e:
        logger.debug("voiceprint learn_speaker failed closed: %s", e)
        return False


def process_meeting(config, session):
    """Auto-name unnamed speakers from stored prints, then learn/update prints
    for named ones. Returns {sid: {"name":…, "meetings": n}} for auto-named
    speakers (empty dict when nothing matched). Never raises."""
    try:
        from app.meetings import MEETINGS_DIR
        path = os.path.join(MEETINGS_DIR, f"{session.id}.wav")
        if not os.path.exists(path):
            return {}
        segs = {}
        for u in session.transcript or []:
            sid = u.get("speaker")
            if not sid or sid == "self":
                continue
            segs.setdefault(sid, []).append(
                (float(u.get("t0", 0)), float(u.get("t1", u.get("t0", 0)))))
        if not segs:
            return {}
        x = _load_wav(path)
        embs = {}
        for sid, ss in segs.items():
            e = _embed(x, ss)
            if e is not None:
                embs[sid] = e
        if not embs:
            return {}

        prints = dict(config.get("voice_prints") or {})
        recognized = {}

        # 1) auto-name: unnamed speakers vs stored prints
        for sid, emb in embs.items():
            name = (session.speakers or {}).get(sid, "") or ""
            if name and not _DEFAULT_NAME.match(name):
                continue
            scored = sorted(
                ((_cosine(emb, np.asarray(p["vec"], dtype=np.float32)), nm)
                 for nm, p in prints.items() if p.get("vec")),
                reverse=True)
            if not scored:
                continue
            best, second = scored[0], (scored[1] if len(scored) > 1 else (0.0, ""))
            if best[0] >= MATCH_THRESHOLD and best[0] - second[0] >= MATCH_MARGIN:
                session.speakers[sid] = best[1]
                recognized[sid] = {"name": best[1],
                                   "meetings": int(prints[best[1]].get("n", 1))}
                logger.info("voiceprint: %s recognized as %r (cos %.3f)",
                            sid, best[1], best[0])

        # 2) learn: running-average print per REAL name
        for sid, emb in embs.items():
            name = (session.speakers or {}).get(sid, "") or ""
            if not name or _DEFAULT_NAME.match(name):
                continue
            _update_print(prints, name, emb)

        config["voice_prints"] = prints
        from app.config import save_config
        save_config(config)
        return recognized
    except Exception as e:
        logger.debug("voiceprint failed closed: %s", e)
        return {}
