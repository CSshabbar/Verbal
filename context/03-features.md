# 03 — Features & Implementation

> Part of the `context/` knowledge set. See `context/README.md` for the maintenance rule.
> **Keep this current:** when you add/change a feature, update its section here (desktop + mobile impl,
> status, limitations) AND the matrix in `01-product.md`. Reference code by file/function, not pasted code.

Each feature: **what it does · desktop impl · mobile impl · backend · status/limitations.**

---

## Recording & transcription

- **What:** capture mic audio, produce cleaned text.
- **Desktop:** `recorder.py::Recorder` — `sounddevice.InputStream`, mono float32 at the mic's native
  rate (default 48k), capped 300s (keeps the beginning), normalizes to peak 0.5; `toggle_pause` for the
  overlay pause button. The noise-reduction/enhancement chain exists but is **disabled** (it "destroyed
  speech content"). `transcriber.py::transcribe_with_status` returns `(text, status ∈ ok|silent|failed)`;
  silence gate `peak<0.01`. **Fallback chain:** ① Groq `whisper-large-v3-turbo` (each key), ② Gemini
  `gemini-2.0-flash`, ③ local `faster_whisper` (cpu/int8, 16 kHz). `main._transcribe_with_retry` retries
  `failed` ×3 with backoff.
  **The upload is 16 kHz mono FLAC**, downsampled once via `_to_16k_array` — not the native-rate WAV it
  used to be (5–6× fewer bytes, median −24% round-trip, no WER change; the WAV for Gemini/local is written
  lazily and only if Groq fails). **Nothing persists before the paste:** `inject_text` runs first, then
  `add_to_history` / `update_daily_words`, then autolearn / sync push / cloud upload. See
  `05-conventions.md` Hard Rule #37, which also covers the archive write running off the critical path,
  the overlay-hide wait that replaced a fixed `sleep(0.3)`, and the three ordering constraints that the
  post-paste persist has to respect.
- **Mobile:** `flume-ui/hooks/useRecorder.ts` — `expo-audio` capture; `stop()` **persists audio first**
  (so a failed transcription is never lost → `status:'failed'`, retryable) then runs the ONE shared
  pipeline `lib/dictationPipeline.runDictation(uri, {cleanup:true})` (transcribe → AI cleanup → snippets —
  IDI-179; retry uses the identical call, and `StopResult.raw` carries the pre-cleanup transcript so the
  note editor's own formatter never double-cleans, Hard Rule #12), stashing the result in a module-level
  `lastRecording` read once via `consumeLastRecording()`. **IDI-180:** `formatText` (cleanup)
  now has the desktop-style resilience — Groq primary with a 12s timeout, ONE retry via the proxy's
  `provider:'ollama'` passthrough on 429/413/5xx/timeout/empty, keep-raw on total failure; Settings →
  **Spoken language** (10 options incl. Auto-detect) writes `flume_spoken_language`, which drives in-app +
  both keyboards' Whisper `language` param AND meeting-notes output language ('auto' → "same language as
  the transcript"); local recordings are swept once per launch (keep 100 / 30 days, never touching audio
  referenced by history OR note segments — both live in `documentDirectory/recordings/`). **Recording modal (IDI-159):**
  Cancel routes to `cancel()` (discard — no upload, no history entry, silent per the Cancel convention),
  a `busy` latch shows "Transcribing…" + spinner and blocks double-taps (one pipeline run per stop), stop/
  cancel handlers are try/catch'd so a hard failure can never strand the user in the modal
  (`gestureEnabled:false`), and the unmount cleanup cancels via refs (hardware-back releases the mic).
  The **Confirmation screen is truthful**: `variant: 'sent'|'saved'|'failed'|'empty'` — "Sent to <device>"
  only when sync is on AND a target is set; otherwise "Saved to history"; failed/empty get warning/neutral
  presentations with no success badge and pruned actions (retry-from-History for failed).
- **Backend:** all Groq calls (transcription + cleanup) now route through the **`groq-proxy` Edge Function**
  — the Groq key is server-side only, clients hold none, and the **in-app API-key entry has been removed**
  on macOS/mobile **and Windows** (mobile Settings card + desktop dashboard field + the menu-bar "Groq/Gemini
  API Key…" items are gone on all three platforms — macOS's `main.py::_manage_groq_keys` was dead code,
  unattached to any `rumps.MenuItem`, and was DELETED in IDI-178;
  Windows's `win_main.py::_tray_manage_groq`/`_tray_manage_gemini` and
  their tray `MenuItem`s were removed MER-34, 2026-07, closing the one platform that still exposed reachable
  key entry). A user's pre-existing local Groq/Gemini key still works as a silent *fallback* (the read path
  in `transcriber.py`/`ai_cleanup.py` was untouched — only the management UI is gone) — the proxy is always
  tried first. Audio → `recordings` bucket. See `05-conventions` Hard Rule #15.
- **Status:** solid. Local Whisper is a desktop-only offline fallback (`faster_whisper` bundled).

## AI cleanup / formatting

- **What:** turn a raw transcript into clean, correctly-formatted text without adding content.
- **Desktop:** `ai_cleanup.py::process_text` — ① `clean_raw_transcript` (regex: strip hallucinations,
  fillers, doubled words; capitalize; terminal punctuation), ② LLM format via Groq
  `openai/gpt-oss-120b` (was llama-3.3-70b, retired by Groq 2026-08-18) (`cleanup_with_groq`) → Gemini fallback with key rotation. `SYSTEM_PROMPT` =
  18 rules ("you are a TEXT FORMATTER, not an assistant") — rule 18 (MER-42, 2026-07; hardened MER-43,
  2026-07) resolves spoken self-corrections to the final value ("ticket RBR 343, sorry, RBR 344" →
  "ticket RBR 344") the same way the notes/meeting-notes prompts already did, but hardened for injected
  dictation text: collapses only with an explicit repair cue (in any language — Roman-Urdu code-switching,
  e.g. "nahi"/"sorry", is the v1-priority case) **+** a same-kind value swap **+** tight adjacency **+** no
  nearby list grammar: bare adjacent numbers/ticket-IDs/phone numbers are **never** collapsed without an
  explicit cue (fail-closed — keep both when unsure). Rule 18 is evaluated **before** rule 7's filler
  stripping — MER-43 fixed a contradiction where rule 7 told the model to strip "I mean" as filler while
  rule 18 relied on it as a repair cue. Also covers: multiple corrections in one breath resolve to the
  LAST value; a correction can occur inside a real list without eating the other items; a cue word with
  no candidate same-kind value nearby is ordinary content, not a repair (e.g. "I want to say sorry to the
  team"); "and" directly before a repair cue is not a list veto ("343 and sorry 344" still collapses).
  This is cleanup, not Transform — no new mode/gate, stays inside `SYSTEM_PROMPT`. Live-verified against
  the real model via `whisperflow/self_correction_fixtures.py` (unlike this repo's other `*_fixtures.py`,
  this one calls the live groq-proxy path deliberately, since a prompt's real behavior can't be verified
  by stubbing the LLM) — covers the full content-type matrix (numbers, dates, currency, percentages,
  names, places, emails, URLs, code identifiers), punctuation-shape invariance, hard/edge cases, and the
  multilingual seed set (Roman-Urdu, Hindi, Spanish, French, Arabic).
- **Context grounding (MER-44 Phase 0, 2026-07):** `process_text(text, config, active_app=None)` prepends
  a `build_context_block()` preamble to the cleanup call — the user's **known terms** (dictionary
  vocabulary + the corrected side of replacement rules, via `dictionary.known_terms()`, so auto-learned
  fixes ground the cleanup too) plus the **active app** name (from `injector.get_focused_app_name()` at the
  `main.py`/`win_main.py` inject sites). It's framed as *grounding data, never a directive to collapse* —
  so it helps the model prefer a known spelling/ID over a phonetic guess without raising the
  identifier over-collapse rate (rule 18 still governs *when* to collapse). Gated by
  `context_grounding_enabled` (default on), fully fail-closed (any error → no context, cleanup proceeds).
  Distinct from `build_prompt()`, which still feeds *Whisper's* transcription bias (vocabulary only).
  Pure-logic harness `context_grounding_fixtures.py`. **Phase 1 (fine-tuned correction model) and Phase 2
  (opt-in flywheel + words-only implicit correction) are explicitly deferred** — they need a paid
  fine-tune serving provider + a plateau signal on the prompt+context path; not started. Separate
  `NOTES_FORMATTER_SYSTEM_PROMPT`; `build_notes_system_prompt(structure_detection, autotitle)` appends the
  checklist/structure-detection and `TITLE:` rules only when those flags are on (see §Notes).
  `format_note(text, cfg, …)` returns `{title, formatted_content}`; `_parse_note_response` peels a leading
  `TITLE:` line.
- **Latency: `speed_mode` (2026-08-14, desktop; default ON since 2026-08-29 together with `chained_mode` and `hybrid_mode` = the **Hybrid** pipeline, the product default; transcription model default stays `asr_model="auto"`. Older configs are moved once by `load_config` (`pipeline_default_v3`) unless `pipeline_choice_explicit`, which Settings sets on any pipeline pick).** One master switch in `DEFAULT_CONFIG` so
  the pre-tuning behaviour stays reachable for A/B. When on: transcripts of **≤ 8 words**
  (`ai_cleanup._SKIP_CLEANUP_MAX_WORDS`) skip the LLM entirely; `SYSTEM_PROMPT` (~2,428 tokens) is replaced
  by `LEAN_SYSTEM_PROMPT` (~677); formatting runs on `SPEED_CLEANUP_MODEL` instead of `openai/gpt-oss-120b`.
  Measured: prompt size has **~zero** latency effect — the win comes from the skip rule and the smaller
  model, not from the shorter prompt.
  **`SPEED_CLEANUP_MODEL` is `openai/gpt-oss-20b` (2026-08-18 — was `llama-3.1-8b-instant`, retired by Groq
  the same day every other `llama-3.x` model was; every call 404'd `model_not_found` until this swap).**
  This is a REGRESSION the code comment above `SPEED_CLEANUP_MODEL` measures explicitly: gpt-oss-20b is a
  reasoning model, so it burns hidden "thinking" tokens before answering even a purely mechanical
  formatting request — 1.54s / 430 output tokens vs the old 8b-instant's 0.82s / 51 tokens on the same
  task. Both gpt-oss calls (`SPEED_CLEANUP_MODEL` in `speed_mode`, `openai/gpt-oss-120b` otherwise, in both
  `process_text()` and `build_chain_spec()`'s chained payload) now pass **`reasoning_effort="low"`**
  (2026-08-22) to claw most of that back — Groq's own default for the gpt-oss family is `"medium"`, which
  is where the hidden-token cost comes from; there is no way to disable reasoning outright, only to turn
  it down. The `chained_mode` path needed the Edge Function's `chainFormat()` updated too (a new
  `chain_reasoning_effort` form field, since that request body is hand-built server-side rather than
  forwarded wholesale) — the plain (unchained) `/chat/completions` JSON branch needed no server change, it
  already forwards the whole client payload through as-is.
- **Settings → Dictation → "Speed & pipeline" (2026-08-15).** A radio group exposing the three real
  pipelines, plus a **Transcription model** select (`asr_model`: `auto` | `whisper-large-v3-turbo` |
  `whisper-large-v3`; `auto` keeps the language-based routing at `transcriber.py`, an explicit pick applies
  to every language, and an unrecognised value falls back to `auto` rather than reaching Groq).
  The radio is **DERIVED from `speed_mode` + `chained_mode`, never stored separately** — those two are what
  the dictation path reads, so a third key would be a copy free to disagree with what actually runs:
  `Original` = both off · `Two round trips` = speed only · `One round trip` = both on.
  Saving goes through `DashboardApi.save_settings`, which honours `PIPELINE_FLAGS` with the same
  "only overwrite when present" rule as `NOTES_FEATURE_FLAGS` and validates `asr_model` against the allowed
  set. `get_state()` now returns `speed_mode`/`chained_mode`/`asr_model` so the pane renders real state.
  **`settingsBase()` in the dashboard JS must NOT send `recording_mode`** — it is absent from
  `STATE.settings`, and `save_settings` only preserves the stored value when the field is MISSING, so
  sending a default would flip a hold-to-talk user to toggle on every pipeline change.
  **Alternate ASR providers are LIVE (2026-08-15).** `transcriber.ASR_CHOICES` is the single table mapping
  each `asr_model` value to a `{provider, model, bias}` triple, so the UI, the validator
  (`save_settings`) and the request builder cannot drift: `auto` / `whisper-large-v3-turbo` /
  `whisper-large-v3` (Groq), `eleven-scribe-v1`, `aai-universal-2`, `aai-universal-3-5-pro`,
  `gemini-3-5-transcribe`, `gemini-3-5-transcribe-smart`.
  Non-Groq choices send `asr_provider` + `asr_alt_model` multipart fields; `groq-proxy` holds
  `ELEVENLABS_API_KEY` / `ASSEMBLYAI_API_KEY` / `GEMINI_API_KEY` as **function secrets** (Hard Rule #15 — no
  provider key ever reaches a client) and normalizes every reply to Groq's `{text}` shape, so no client
  needs per-provider response handling and `chain=1` still works on top of any of them.
  **Gemini 3.5 Transcribe (2026-08-27, TRIAL rows in every picker — desktop, Windows, mobile).** Provider
  `gemini` → `transcribeGemini()` in `groq-proxy` (v17): one synchronous POST to the Gemini **Interactions
  API** with the audio inline as base64 (no Files API round trip), model `gemini-3.5-transcribe`; the
  `asr_alt_model` field carries the transcription **mode**, not a model id — `verbatim` (raw words, then
  Flume's normal formatting hop; the apples-to-apples row) or `smart` (Gemini removes fillers, applies
  self-corrections and punctuates itself; today Flume still formats on top — skipping that hop when smart
  is chosen is the follow-up that would actually cut latency). Independent numbers (Artificial Analysis):
  AA-WER 2.6 % vs Groq Whisper Turbo 4.6 %; speed factor 78× vs 165×; ~$5 vs $0.67 per 1,000 min.
  `custom_vocabulary` (dictionary → up to 1,000 terms) is NOT wired yet (`bias: False`). Requires the
  `GEMINI_API_KEY` function secret; unset → 503 → falls back to Groq like every other provider.
  Three rules that matter:
  - **Fails closed to Groq.** A provider that is unconfigured, down or out of credit returns 502 and
    `transcribe_with_status` immediately retries on Groq for that dictation. The provider is a preference,
    never a dependency.
  - **`bias: False` on non-Whisper providers.** Only Whisper accepts a glossary, so `dictionary.build_prompt`
    output is not sent to them — and `finalize(..., biased=False)` then skips `strip_prompt_echo`, whose
    heuristics would otherwise hunt an echo that cannot exist and could clip real words. The user's
    replacement rules still apply afterwards.
  - **They are slower**, and the UI says so per option: Groq ~1.0s, ElevenLabs ~1.75s, AssemblyAI ~5s
    (upload-then-poll). They buy accuracy, not speed.
- **Platform parity for pipeline + model (2026-08-15).** All three clients offer the SAME option ids in
  the SAME order, so the product describes one thing:
  - **macOS** `flume_dashboard_html.py` — Settings group renamed `dictation` -> `models`. Pipeline and
    model are plain rows (name, one line, the wait) above a **canvas blueprint**: a rotating wireframe of
    the route, drawn from the selected pipeline's own topology (`bpScene`), with packets animating along
    the real lanes and a waveform at YOU for hybrid. Hand-rolled projection, no library. It must be
    stopped when its pane unmounts — `renderSettings()` calls `bpMount()`/`bpUnmount()`, and `renderActive()`
    calls `bpUnmount()` when leaving Settings, or a rAF loop keeps drawing into a detached canvas.
    Honours `prefers-reduced-motion` by drawing one static frame.
  - **Windows** `win_dashboard.py` — same four pipelines as radios + the six models as a combobox.
    `_derive_pipeline`/`_pipeline_flags`/`_win_asr_value` mirror the macOS derivation exactly, including
    writing `hybrid_mode` on EVERY choice so switching away cannot leave it streaming. `win_main.py` has
    the same hybrid start/consume blocks as `main.py` (the `Recorder` and its tap are shared code).
  - **Mobile** `flume-ui/screens/ModelsScreen.tsx` (new, reached from Settings -> Voice -> Models, route
    `Models` on `MenuStack`). Tables live in `lib/groq.ts` (`PIPELINES`, `ASR_MODELS`) and the prefs are
    local AsyncStorage (`flume_pipeline`, `flume_asr_model`) — a per-device speed/accuracy trade, not
    account state. `transcribeAudio` sends `asr_provider`/`asr_alt_model` for non-Groq picks, skips the
    glossary and the echo scrub for them, and **retries once on Groq** if the provider call fails.
    **`hybrid` is deliberately absent on mobile** — it streams while you speak and mobile records to a file
    then uploads, so it would be a switch that does nothing.
- **Hybrid pipeline — BUILT (2026-08-15, `hybrid_mode`; default ON since 2026-08-29 — it is the product default pipeline).** Streams mic audio to the new
  `asr-stream` Edge Function *while you speak*, then uses the streamed transcript for takes at/over
  `asr_stream.HYBRID_THRESHOLD_SEC` (8.0s, the measured crossover) and falls back to the ordinary chained
  path below it, because Groq is genuinely faster on short takes. Selecting it in Settings writes
  `speed_mode=True, chained_mode=True, hybrid_mode=True`; every other pipeline explicitly writes
  `hybrid_mode=False`, so switching away can never leave it silently streaming.
  - `app/asr_stream.py` — `AsrStream` opens the socket at record-start; `Recorder.set_tap()` feeds it each
    block. **The tap runs on the PortAudio realtime thread**, so it only decimates to 16 kHz and puts bytes
    on a bounded queue; a separate pump thread does all I/O. `_audio_callback` wraps the tap and drops it
    permanently on its first exception — losing the stream costs latency, losing the callback costs the
    dictation. `Recorder.stop()` clears the tap after its settle so no stale tap survives into the next take.
  - Frames are a fixed 100 ms with the remainder carried; AssemblyAI closes the session on any frame under
    50 ms (this is the bug that broke the playground — see 05 §Hard rules).
  - **AssemblyAI only.** Deno's `WebSocket` cannot set request headers, so a vendor must accept a credential
    in the URL; AssemblyAI mints one (`GET /v3/token`, verified working) while ElevenLabs' realtime API
    documents only an `xi-api-key` header and returns 404 on every token path probed. Not guessed at.
  - **The streamed transcript bypasses `transcriber.finalize()`**, so `main.py` applies
    `dictionary.apply_replacements` to it explicitly — otherwise the dictionary would silently stop working
    on exactly the long dictations this path serves. No prompt-echo scrub (no glossary is sent).
  - **Caveat surfaced in the UI:** the streaming engine writes Roman-Urdu in Devanagari, so hybrid is the
    wrong choice for long code-switched dictation. Payoff over one-round-trip is 0.24–0.37s, above 8s only.
  - Fails closed at every step (no socket, dropped blocks, no final, any exception) → ordinary upload path.
- **Latency: `chained_mode` (2026-08-14, desktop; default ON since 2026-08-29, see `speed_mode`).** INDEPENDENT of `speed_mode` and composes
  with it: it changes only the **network path**, never the prompt, model, or output. Off, dictation costs two
  client round trips (transcribe, then format) — 8 internet crossings for ~370 ms of model work. On,
  `ai_cleanup.build_chain_spec()` builds `{system, user, model, replace}` (the `user` wrapper carries
  `{{TEXT}}` as the transcript slot), `groq_proxy.transcribe_via_proxy(chain=…, sidecar=…)` sends it as
  `chain=1` multipart fields, and `groq-proxy` (edge fn **v10**) transcribes then formats server-side,
  returning `chain:{formatted, ok, asr_ms, fmt_ms}`. The client hands that to
  `process_text(…, chained_result=…)`, which still applies every rule around the formatting (local cleanup,
  the `speed_mode` skip, the 429 fallback) — only the second network call is skipped.
  **Measured: 6/6 clips byte-identical output and identical accuracy to the two-trip path, median +0.59 s
  faster (2.0 s → 1.2 s).** Wired on both `main.py` and `win_main.py`. Fails closed at every layer: no chain
  spec, a non-Groq fallback provider, or `chain.ok=false` all fall through to the ordinary two-trip path, so
  the fast path being unavailable costs latency and never a dictation. Two ordering rules make chained output
  identical rather than merely similar — see 05 §Hard rules #40.
- **Streaming ASR — MEASURED AND DEFERRED (2026-08-14).** The remaining gap to Wispr Flow is that Verbal
  sends nothing until you stop speaking. Groq **cannot** close it: its audio API is file-only (no
  WebSocket), and its **10-second minimum billed duration** makes client-side chunking cost multiples of
  the real audio on a 28,800 audio-sec/day free tier. ElevenLabs `scribe_v2_realtime` (WebSocket, own key,
  ~$0.39/hr) can, and was measured over the 20 own-voice clips:
  - **Tail after you stop speaking is FLAT ~0.32 s** at every length (2.4 s of speech and 65 s both ~0.3 s)
    — the work happens during speech. Groq's wait grows with length (0.72 s → 1.16 s → 1.29 s).
  - **But formatting still needs its own round trip (~0.75 s)**, which streaming cannot chain away, so the
    end-to-end win is only **0.24–0.37 s** and only above ~8 s of speech. **The two curves cross at ~8 s**
    — that is where a length-based router would switch, derived from the data, not chosen.
  - **Accuracy is a wash, not a win**: realtime scored 93.3% vs Groq's 92.9% on plain English and **80.0%
    vs 81.3% on Roman-Urdu code-switching**, where it fails badly (clip `s07`: 38.9% vs Groq's 77.8%,
    "matlab it's not working" → "but love, it's not working"). Note the 95.7% figure belongs to
    ElevenLabs' *file* model; the realtime model is weaker. Given this user code-switches routinely, the
    speed win costs accuracy exactly where it hurts. **Not implemented in the product** — it is selectable
    in the out-of-repo eval platform (`~/.verbal-eval/collect/`, `live.py`, `/playground`) as the
    `stream_el` / `hybrid_el` versions so the trade can be felt before anything is built.
  - **AssemblyAI universal streaming v3** (`wss://streaming.assemblyai.com/v3/ws`, `Authorization: <key>`
    with NO Bearer prefix, raw binary PCM frames, `{"type":"Terminate"}` to flush) was added as a second
    realtime engine (`stream_aai` / `hybrid_aai`). **Spot-checked on 4 clips only** — not swept, to save
    credits — and on those it beat ElevenLabs realtime on both axes: tail **0.0 s** (it finalises a turn off
    trailing silence, so the transcript can be ready *before* the speaker stops) vs 0.285 s, and it got
    `Supabase` where ElevenLabs produced `Superbase`. On `s05` it scored **100%** where Groq scored 80%.
    Batch rows also exist for the models table (`aai-universal-3-5-pro`, `aai-universal-2`); note
    `speech_model` is rejected as deprecated — the field is now the **list** `speech_models`. Universal-3.5
    Pro transcribed the Roman-Urdu clip `s07` into **Devanagari script** despite `language_code: "en"`
    (scored 0% — right meaning, useless for dictation into English), while Universal-2 handled the same clip
    best of any model tested at 83.3%. So model choice there is not a simple "newer is better".
- **Mobile:** `lib/groq.ts::formatText` (same `openai/gpt-oss-120b` (was llama-3.3-70b, retired by Groq 2026-08-18)) — used on **retry** and where
  screens call it. Brought to full **logic parity** with desktop's self-correction rule in MER-43 (same
  cue families, 4-part test, anti-cues, and-carve-out, asymmetry, punctuation-invariance, directionality —
  terser prose, no dropped rules; MER-42 had shipped it with several gaps vs. desktop, closed in MER-43).
  Kept in sync deliberately, same discipline as the notes/meeting-notes prompts — each file's rule 18 /
  SELF-CORRECTIONS block carries a comment pointing at its counterpart. `formatText` also prepends the
  MER-44 Phase-0 grounding preamble (known terms via `dictionary.knownTerms()`; mobile has **no**
  active-app signal, so it's known-terms only), fail-closed. `formatNotes` /
  `formatNoteWithTitle(text, apiKey, {timeoutMs, detectStructure,
  withTitle})` are now **wired into the note editor** via `useNotes.saveDictation` (see §Notes) — mobile
  notes are no longer stored raw-only.
- **Status:** desktop runs cleanup on every dictation. Notes cleanup (both platforms) runs **once** per
  dictated save, not on every edit (Decision 2 — see §Notes).

## Custom dictionary (vocabulary + replacement rules)

- **What:** two mechanisms — **vocabulary** biases the model toward names/terms; **replacement rules**
  deterministically rewrite a misheard word (`{from,to}`).
- **Desktop:** `dictionary.py` — `build_prompt` ("Glossary: w1, w2, …", the **last** ≤80 terms / ≤600
  chars) injected into the Whisper `prompt`, and `strip_prompt_echo` taking it back out of the result
  (see below); `apply_replacements` (word-boundary, case-insensitive `re.sub`); `add_replacement`
  de-dupes by `from`, tags auto rules `auto:True` (✨ in UI). `known_terms(config, limit=60)` (MER-44)
  returns vocabulary + replacement `to`-targets, deduped — this is what grounds the **cleanup** LLM (see
  §AI cleanup), distinct from `build_prompt` which grounds *Whisper*. Stored `config["dictionary"]`, synced
  to Supabase `dictionary` (one row/user) via `fetch_remote`/`_push_remote`.
- **Mobile:** `lib/dictionary.ts` — direct mirror (`buildPrompt`, `stripPromptEcho`, `knownTerms`,
  `applyReplacements`, `addReplacement`, `fetchRemote`), AsyncStorage `flume_dictionary` + Supabase
  upsert. Managed in
  `SettingsScreen`.
- **Backend:** `dictionary` table (`user_id` PK, `vocabulary` jsonb, `replacements` jsonb, `updated_at`).
- **Sync is CAS, not last-write-wins (IDI-174, 2026-08):** writes are filtered on the last-witnessed
  `updated_at`; a conflict refetches, merges (vocab union / snippets by trigger / replacements by `from`)
  and retries once — two devices editing in one session no longer clobber each other, and a vocab edit
  can't drop snippets. Mobile blocks pushes until the first fetch resolves (the edit-before-load wipe),
  sequences push→keyboard-sync (no self-clobber race), requires a real identity (`getCloudUserId()`), and
  surfaces "Couldn't sync — will retry" on double failure in both editing UIs.
- **Bias-prompt echo is stripped from every transcript (2026-08):** Whisper's `prompt` is a
  *continuation* prompt, so on quiet/short/speech-free audio the model kept writing the glossary and the
  list itself was injected as the "transcription" (`"Glossary, M.T.:"`) — the same mechanism that
  sprinkles stray vocabulary words into unrelated sentences. All four dictation front doors now (a) send
  a much shorter, tail-weighted glossary and (b) run `strip_prompt_echo` / `stripPromptEcho` on the result
  **before** replacements/snippets/tagging: label-introduced runs (`Glossary:`/`Files:`, whether followed
  by sent terms or standing alone as a bare heading) and comma-lists of ≥2 sent terms are deleted, while
  a lone dictionary word, a label that runs on inside its clause, and any label word we did not actually
  send that call are always kept. An echo-only transcript becomes `""` → reported as **silence** ("No
  speech detected" on the keyboards), never as a failure and never retried on another provider.
  **Follow-up fix (2026-08):** a bare heading we invented (`glossary`/`vocabulary`, never `files`) counts
  as an echo on ANY punctuation, not just a fragment-ending one — the comma form (`"Glossary, Right now,"`)
  is what Whisper actually emits and it survived the first fix, since a comma reads as "this clause keeps
  going, so it's speech". See
  `05-conventions.md` Hard Rule #6; `whisperflow/prompt_echo_fixtures.py` pins 46 cases (every echo shape
  removed, real speech untouched).
- **Status:** full parity. Rule shape `{from, to, auto?}`.

## Snippets (spoken trigger → text expansion)

- **What:** a generalization of replacement rules — a spoken `trigger` **phrase** expands into a longer
  saved `expansion` block (LinkedIn URL, email signature, scheduling link, disclaimer). Spoken naturally
  inside normal speech (no command syntax); expands in place, rest of the sentence untouched. Stored on
  the same per-user `dictionary` row (third array beside vocabulary + replacements).
- **Desktop:** `dictionary.py` — `apply_snippets(text, config, save_config_fn=None)` (phrase-boundary,
  case-insensitive, multi-word aware) plus CRUD `add_snippet`/`update_snippet`/`remove_snippet`/
  `get_snippets` (dedupe by trigger, mirror `add_replacement`). Runs in `main.py` **after**
  `ai_cleanup.process_text` and **before** injection. Match rules: **longest trigger first** (so a
  substring trigger can't shadow a longer one) and **single pass only** — an inserted expansion is never
  re-scanned (no recursive/nested expansion, no cascades or loops). On each match the snippet's `used`
  counter is bumped and persisted. Dashboard **Snippets** tab in `flume_dashboard_html.py`. Assertion
  harness `snippets_fixtures.py`.
- **Mobile:** `lib/dictionary.ts` — direct mirror (`applySnippets`, `getSnippets`, `addSnippet`,
  `updateSnippet`, `removeSnippet`, `Snippet` type), same longest-first/single-pass algorithm and `used`
  bump; `flume-ui/screens/SnippetsScreen.tsx` + `flume-ui/hooks/useSnippets.ts` (mock contract
  `useSnippets.mock.ts`). Both NATIVE keyboards now also carry true longest-first/single-pass/no-cascade
  mirrors with blank-expansion skipping (iOS added in IDI-161; Android's cascading version fixed in
  IDI-162) — `lib/dictionary.ts` stays the reference all three must match.
- **Backend:** `dictionary.snippets` jsonb column (default `'[]'`), `supabase_snippets.sql` (idempotent
  `ADD COLUMN IF NOT EXISTS`). Snippet shape `{id, trigger, expansion, label, used, created_at, updated_at}`.
  Same sync path as the rest of the dictionary (one row/user, last-write-wins). `_push_remote` preserves
  the sibling `snippets` array so a vocab/replacement save never wipes it.
- **Caps:** `trigger` ≤ 40 chars, `expansion` ≤ 500 chars (match the design mockups; enforced both sides on normalize + CRUD + UI counters).
- **Status:** full parity (desktop + mobile). Fails closed — any `apply_snippets` error returns the text
  unchanged, never breaking the transcribe → inject path.

## Team / Organization (IDI-216, Aug 2026)

- **What:** a named group ABOVE the single-user account. An owner creates a team, invites people by
  email, manages roles, and shares a dictionary + snippets with everyone on it; members share usage
  counts (on by default) and the owner can switch on a team leaderboard for everyone. **One team per user** — enforced by a partial unique index on
  `organization_members(user_id) where status='active'`, not by app code, so a racing invite claim
  cannot create a second membership.
- **Why it did NOT need IDI-29 first.** The obvious reading of "team mode" is cross-account access, which
  on the legacy tables would be a real security hole (they are scoped, not enforced). The shipped design
  avoids the premise: the shared dictionary lives in its OWN table (`organization_dictionary`), and
  cross-member reads go through SECURITY DEFINER RPCs that check membership themselves. So nothing here
  reads another user's row in `dictionary`/`transcriptions`/…, the four new tables carry real
  `auth.uid()` RLS from their first row, and `supabase_auth_uid_rls.sql` stays an independent ticket
  with its pairing trade-off still open. See `04-data-model.md` §Organization layer.
- **Roles:** `owner` (exactly one, immovable, the only role that can toggle the leaderboard org-wide) ·
  `admin` (invite, remove, change roles, edit the shared dictionary) · `member` (read the roster + shared
  dictionary; manage their own consent; leave). Membership and invites are READ-only over REST — every
  write goes through an RPC, because Postgres RLS cannot restrict which *columns* a policy lets you
  write, so a "members may update their own row" policy would also let a member set their own role.
- **Invites:** `invite-member` Edge Function → `organization_invites` row + a one-time token → Resend
  email. The DB stores only the token's **sha256**, so a leaked row can't be replayed. The claim RPC
  (`org_claim_invite`) fails closed in order — unknown token, expired, already used, already in a team,
  no seats, and finally the **email guard**: the signed-in account's address must match the address the
  invite was sent to, or a forwarded link would grant membership to whoever opened it first. Seats are
  counted as active members + pending invites so an admin can't over-invite and discover it at claim
  time. **No partial invite** — if the mail fails to send, the row is deleted again.
- **Shared dictionary (the merge rule).** Dictation applies **personal ∪ team**. Nothing is dropped from
  either set; only a genuine same-key collision needs a tiebreak — identical vocabulary word
  (case-insensitive), identical replacement `from`, identical snippet `trigger` — and there **personal
  wins**. That is the non-destructive choice: joining a team can never silently change what your existing
  snippet trigger expands to. Team entries are ordered FIRST and personal LAST, because `build_prompt`
  keeps the *tail* of the vocabulary (Whisper conditions on the last ~224 tokens and trimming happens
  from the front) — reversed, joining a team would quietly evict your own words from the bias prompt.
  Desktop `dictionary.effective()`/`merge_with_team()`; mobile `getEffectiveDictionary()`/`mergeWithTeam()`.
  Both read a LOCAL cache (`config['org']` / AsyncStorage `flume_org`), so the dictation path still makes
  no network call, and both fail closed to personal-only on any error.
  **It is EDITED on the Dictionary screen, not on Team** (2026-08-21). Both platforms put a scope switch —
  `Mine | <team name>` — at the top of Dictionary; Team carries only a one-line summary that links across.
  A dictionary is a dictionary, people look for one under Dictionary, and two homes for one concept meant
  two places to learn it. Admins edit the shared scope, members see it read-only with "your admins
  maintain these". Desktop `DICT_SCOPE`/`renderTeamDictionary()`/`tdSave()` (a CAS through
  `save_team_dictionary`, because two admins can be editing at once); mobile `DictionaryScreen`'s
  `scope` state, which falls back to `personal` if the team disappears mid-session.
- **Daily series for the charts.** `org_usage_series(p_org, p_days)` returns per-member per-day word
  counts in ONE call — the roster sparklines and the per-member heatmap need the breakdown that
  `org_usage_summary`'s totals can't give, and N round trips (one per member) would be silly. Same
  privacy contract; visibility differs by role on purpose — owner/admin get every consenting member,
  anyone else gets only their own row, so a member can see their own sparkline without the screen
  becoming a way to read colleagues' activity.
- **Team-wide stats visibility (2026-08-25).** `organizations.stats_visible_to_members` (owner-only
  toggle — desktop Settings > Team privacy > "Team-wide visibility", mobile Team screen): when on,
  every active member sees the same per-person stats owners/admins do (`org_usage_summary`/
  `org_usage_series`/`org_app_breakdown` all honor it). Each member's own `usage_consent` still wins —
  the org switch widens the audience, never overrides an individual opt-out, exactly the
  `leaderboard_enabled` vs `leaderboard_opt_in` contract. Client member-views switch voice on the flag
  (desktop `TEAM.stats_visible_to_members`, mobile `seeAll`), since the RPCs decide the rows either way.
  **Ranking under team-wide visibility (2026-08-26):** with the flag on, desktop's `tmBoardRows()` ranks
  members from the usage rows they can already see instead of the opt-in board — an opt-in ranking of
  already-visible numbers is pure friction (live case: ranking on, stats open, member's board empty
  because nobody had opted in). `leaderboard_opt_in` still gates the board for teams that keep stats
  admin-only. Mobile needs no change: its usage list is already rendered ranked with bars.
- **Usage insights + leaderboard (opt-in, counts only).** `org_usage_summary` (every active member — an
  owner/admin gets all consenting members, anyone else gets their own row) and
  `org_leaderboard` (every active member, once the owner enables it org-wide) are SECURITY DEFINER RPCs
  that read `transcriptions` to COUNT words and sum durations and return **only** aggregates — there is
  no column in either return type that could carry transcript text. A member who hasn't set
  `usage_consent` is **absent from the result entirely** rather than shown as zeroes, so their silence
  isn't itself a signal. **The leaderboard is owner-controlled and all-or-nothing (2026-08-27):**
  `org_leaderboard` lists every active member with `usage_consent` once `leaderboard_enabled` is on; the
  per-member `leaderboard_opt_in` column no longer gates it and the "Show me on the ranking" toggle is
  gone from both Settings screens (owner decision — "either open for everyone or closed for everyone").
  Turning `usage_consent` off still removes you from the board, because it removes you from every
  cross-member view.
  **The toggles live in Settings, not on Team** (2026-08-21): desktop adds a `privacy` group to
  `SETTINGS_GROUPS` (label "Team privacy", rail badge `sharing`/`private`), mobile a `TEAM PRIVACY`
  section. Both are rendered **only when the user is on a team**, and desktop falls the group back to
  `account` if you leave while sitting on it. "Where do I turn that off?" had two answers before; now it
  has the same answer as every other data switch in the product. The team payload therefore feeds two
  screens, so `teamRepaint()` paints whichever is showing — a consent toggle that does not move while the
  backend has already changed reads as broken.
  **Leave team moved with it, and is hidden for an owner**: `org_remove_member` returns
  `cannot_remove_owner`, so the old unconditional button on the Team screen always failed for the one
  person most likely to press it.
- **Where each person writes (2026-08-21).** `org_app_breakdown(p_org, p_days)` answers the question an
  admin asks first — *which app is each person actually dictating into?* Until now the only per-app data
  existed in `config['stats_daily'].apps` on each user's own machine, which is why Insights could chart it
  and Team could not. `transcriptions.app` is written by both desktops from the **pre-injection**
  frontmost app; **iOS writes nothing** (no frontmost window on a phone). Rendered as a stacked share
  strip per member on the team overview and a ranked list on each member page.
  **Historic rows are NULL and unbackfillable**, so both surfaces state the 21 Aug 2026 cutoff in prose
  rather than rendering an empty panel that reads as a bug — the same discipline as the blank-WPM-gauge
  fix. This is also the one place the team layer's "counts and durations only" promise had to widen; the
  copy on every Team surface now names app names explicitly.
- **Entitlements (Phase 3):** `organizations.plan`/`seats`. `groq_check_rate_limit_org` is the MER-30
  limiter plus a `p_user_id` it uses to look up the caller's org plan and RAISE their tier — folded into
  the round trip the limiter already makes, so team entitlements cost the hot path **zero** extra DB
  calls. `groq-proxy` falls back to the original `groq_check_rate_limit` if the org RPC is absent (and
  latches that off after one 404), so the function and the migration can deploy in either order.
- **Desktop UI — four views off one screen** (`flume_dashboard_html.py::renderTeam()`, backed by
  `app/organizations.py` through `DashboardApi`). Both desktops render the same `flume_html()` against
  the same backend class, so **Windows has this at parity automatically**.
  1. **No team** — the create/join screen. Leads with the value rather than a form: the same sentence
     shown as a new teammate would hear it (`Ideas` struck through) beside how the team hears it
     (`Idiaz`), then ONE primary action. The join path stays findable but quiet — someone joining
     normally clicks a link in an email and never sees this screen.
  2. **Just created** — a two-step setup that did not exist in the first cut, where creating a team
     dropped you onto an empty roster with no next step. Step 1 offers to **copy the owner's own
     dictionary into the team's** (`seed_team_dictionary`), because a team that starts empty has no
     reason to be used; step 2 is the first invite. Seats are drawn as dots, not a fraction. Dismissed
     by sending an invite, seeding the dictionary, or Skip; tracked in the local-only config key
     `org_setup_done` (a per-device nudge — deliberately NOT a Supabase column) and reset on account
     switch by `auth._clear_account_caches`.
  3. **The team** — a permanent roster column (each row carrying a 14-day sparkline) beside a detail
     pane titled "How <team> flows", echoing Insights' "How you flow". The **contribution ring** is the
     team's answer to the WPM gauge: total in the middle, per-member split around it, so an unbalanced
     team is visible at a glance. Then the pastel `.itile` band (words · dictations · team pace · seats),
     the **ranking**, "Where the team writes", and one-line pointers to the shared dictionary and to the
     consent toggles. **Neither is edited here** — the dictionary lives under Dictionary → <team>, the
     consent toggles under Settings → Team privacy. Each pointer states the current state in a sentence
     ("you are sharing your dictation counts…") so the jump is informed, not exploratory.
     The **ranking** (`tmLeaderboardCard`) is a table, not a bar chart: rank, avatar, name, a
     dictations/wpm/top-app subline and the word count on one row, with the bar as a background wash —
     people compare themselves to the row above, so those have to read together. It draws from
     `TEAM_USAGE` for owners/admins (the fuller, consent-gated set they already see) and from the opt-in
     `TEAM_BOARD` for everyone else; **same rows, same order, different audience**. This is why a new
     admin no longer sees an empty "nobody has opted in yet" board, which was the single most confusing
     thing about the first cut.
     **A plain member's overview is their own numbers, in second person** — "You on <team>", "Your words",
     "Your pace", their own app mix, no contribution ring (one contributor always reads 100%), and a line
     saying the team's totals stay with the admins. Before 2026-08-21 that page was all zeroes: every
     total comes from `org_usage_summary`, which was admin-only in SQL *and* gated client-side twice, so a
     member's team looked like it had never dictated anything. The empty-state copy was the tell — it said
     "usage appears here as people turn sharing on" while everyone was already sharing. Empty states that
     name a cause must be able to tell that cause apart from the others: `TEAM_USAGE` null (not loaded),
     `rows: []` for an admin (nobody dictated), and `rows: []` for a member (you didn't) are now three
     different sentences.
  4. **One member** — that person's numbers given the full Insights treatment: the same semicircular
     WPM gauge, the same pastel band, the same 14-week activity heatmap, then "Where <name> writes".
     Role control and Remove sit in the header (**always visible and labelled**, not hover-revealed — a
     control nobody can find is a control that doesn't exist). A member who has not consented shows a
     locked empty state, never zeroes, and no app panel either: an explanation of missing app data would
     still be a page about them.
  **The screen reuses the Insights CSS deliberately** (`.inshero`/`.itile`/`.inscard`/`.inshm`/
  `.insabar`): "numbers about you" already has a house style, and a Team screen that invented its own
  would read as a different product. Only the roster column, the ring and the onboarding screens carry
  new CSS.
- **Per-member WPM is derived, not stored** — `org_usage_summary` returns `words` and `speech_ms`, so
  the client divides. It is suppressed below **120 s** of measured audio: `transcriptions.duration_ms`
  is NULL on older rows (193 of 430 on the founding account), and a thin sample would invent a number
  rather than report one.
- **Mobile UI:** `flume-ui/screens/TeamScreen.tsx` via `flume-ui/hooks/useOrganization.ts` (+ `.mock.ts`),
  reached from the SidePanel's Tools group and hosted in the `Menu` modal stack — so it carries its own
  chevron-back and uses native-Alert `confirm()` (Hard Rule #14). **Split in two (2026-08-26):** the main
  view is read-only numbers (stat tiles, usage ranking, "Where the team writes", leaderboard list); a gear
  in the title row opens **Team settings** — roster (role toggle/remove), pending invites, the on-demand
  invite form, the owner's leaderboard + team-wide-visibility switches, the dictionary/privacy pointers
  and Leave team (hidden for the owner). One long scroll with all of it read as "complicated"; the
  numbers are what people open the screen for, the management is a tap away. **The numbers block is the
  shared `flume-ui/components/TeamInsights.tsx`** (stat tiles, usage ranking + sparklines, "Where the team
  writes", leaderboard list) — the Team screen's main view renders it, and so does **Insights under a
  `Mine | <team>` segment** (2026-08-27; same control as Dictionary's scope, drawn only when `hasTeam`,
  snaps back to Mine if the team disappears, hides the share-recap button in team scope). One component so
  the two views can't drift. Same sections as desktop: the shared
  dictionary is a pointer here too (the editing is a `Mine | <team>` scope on `DictionaryScreen`), the
  usage list is a ranking with the bar behind the text rather than beside it (a separate chart column
  leaves no room for a name at phone width), and "Where the team writes" renders the same stacked share
  strip, and the privacy toggles are a `TEAM PRIVACY` section in `SettingsScreen` rather than a block on
  Team. Still first-pass relative to desktop: no join popup, no invite modal, no domain card.
- **Deep-linked invites (mobile):** `lib/pendingInvite.ts` parks the token from a
  `verbal://team-invite?t=…` link and claims it after sign-in — the usual order, since the recipient taps
  the link in their email before they have a session. Single-use by construction: the token is removed
  *before* the claim is attempted, so a failed claim can't silently retry on every launch.
- **Account teardown:** the org cache is account-scoped in the strongest sense and is wiped by both
  platforms' sign-out/account-switch paths (`auth._clear_account_caches` sets `config['org']`;
  `clearAccountData` removes `flume_org` AND calls `clearOrgCache()` for the in-memory mirror). Without
  it the next account signed in on that machine would dictate with a team it was never in.
- **Fails closed, everywhere.** No team, an offline device, a 403 and an unapplied migration are
  indistinguishable to callers — all return the "no org" shape. A paired-but-never-signed-in device
  sends the anon key, reads zero org rows, and simply has no team.
- **Status (2026-08-19):** built and **backend LIVE**. Migrations `organizations_team_layer_idi216` +
  `organizations_revoke_anon_execute_idi216` are applied to `ovpcthjingugwvpxlsna`, and `invite-member`
  is deployed (v1, `verify_jwt` on). Verified live in a rolled-back transaction with simulated JWT
  claims for two real users: an owner sees only their own org/roster/shared dictionary, a non-member
  sees **zero** rows in all four tables, anon sees zero, and a member's direct `UPDATE` to promote
  themselves to `owner` affects 0 rows (there is no write policy at all). The invite function refuses
  both a missing Authorization header (gateway 401) and the anon key (role `anon` ≠ `authenticated` →
  `not_authenticated`).
  **Email is live (2026-08-20):** `RESEND_API_KEY` + `INVITE_FROM_EMAIL=sraza@idiaz.io` are set, and
  `idiaz.io` is **verified** in Resend (DKIM + SPF MX + SPF TXT, added at Squarespace — the domain's
  nameservers are `ns-cloud-*.googledomains.com`, inherited from the Google Domains acquisition, so the
  Squarespace DNS panel is the right place). Two things cost time and are worth knowing next time:
  Squarespace's **NAME** field takes the subdomain only (`send`, not `send.idiaz.io`), and the SPF TXT
  first went in as `include:amazonses.com~all` — **the space before `~all` is load-bearing**; without it
  SPF parses the whole thing as the include target and the record has no `all` mechanism. Verification
  only passed after the corrected record had propagated to public resolvers and the check was
  re-triggered. The Resend MX lives on the `send` subdomain and does NOT disturb the Google Workspace
  MX at the root.
  **Invite email redesigned (2026-08-20, IDI-225):** `inviteEmail()` now echoes the real
  idiaz.io/flume site instead of a generic transactional layout — the nav's icon+wordmark lockup, the
  dotted-border mono eyebrow pill, the bold headline with a terracotta trailing period, the product
  screenshots' three-dot window-chrome (wrapping the same "what changes" before/after line), and the
  hero's numbered `01`/`02` mono-index feature rows, and (2026-08-20, follow-up) the actual mascot mark
  rasterized from the site nav's own SVG. **That icon rides as a Resend `cid:` inline attachment
  (`flume-icon.ts`, base64 PNG), not a hosted `<img src>`** — deliberately, so showing it needed no new
  public storage bucket/CDN to stand up or secure, and it still renders for recipients who block remote
  images (only their client's own inline-image gate applies). This is the one exception to the earlier
  "no images" rule; the Outlook-safe table button, `color-scheme` meta, preheader, and plain-text mirror
  are all unchanged. **Gotcha (2026-08-21): keep this asset small.** The first deploy embedded a 300×328
  icon (~16k-char base64) directly in the `deploy_edge_function` MCP tool call — that payload silently
  truncated mid-call (v7 shipped with a ~3.1k-char, invalid, non-4-multiple base64 string; a confused
  follow-up agent then made it worse across several more versions before being stopped). Fixed by
  shrinking the source PNG to 58×64 (~4.7k-char base64, still 2× the email's largest display size,
  30×33) and redeploying directly rather than through another long-running agent — verified after by
  independently re-fetching the deployed source and checking the base64's exact length. **Never trust a
  giant inline string in a single tool call without an independent length/hash check post-deploy; a
  fresh short-context agent check is more reliable than eyeballing or a long-context retype.** `CLAIM_BASE`
  now defaults to `https://idiaz.io/flume/download.html` (was the
  nonexistent `flume.app/join`) — a real, live page, but it does not yet consume the `?t=` token to
  auto-claim; that still happens by pasting the link/token into "Have an invite?". **Still needed:**
  wiring `download.html` (or a dedicated page) to read `?t=` and deep-link into
  `verbal://team-invite?t=…`, root SPF + DMARC for `idiaz.io` (Hard Rule gap, no root SPF/DMARC today —
  Workspace human mail from `@idiaz.io` is unauthenticated), moving `INVITE_FROM_EMAIL` off the
  personal `sraza@idiaz.io` mailbox, Resend bounce/complaint webhooks → suppression list, and the
  **`groq-proxy` redeploy** for Phase-3 entitlements (deployed version still calls the old limiter — a
  no-op difference until teams exist), and **IDI-217** (account deletion orphans a team).
- **Migration gotcha worth remembering:** `revoke all on function … from public` revokes from the PUBLIC
  pseudo-role and does NOT undo Supabase's `ALTER DEFAULT PRIVILEGES` grant of `EXECUTE` to **`anon`** on
  new functions in `public`. The org RPCs were briefly anon-callable because of it (harmless — each
  derives its caller from `auth.uid()`, which is NULL for anon, so they returned `not_authenticated` /
  `forbidden` / an empty set), and were explicitly revoked in a follow-up migration. **Revoke from
  `anon` by name**, not just from `public`, on any future SECURITY DEFINER function.

## Auto-learn from corrections (desktop only)

- **What:** after inserting a transcript, if you fix a mis-transcribed word in the target field, offer to
  add a replacement rule so it's fixed forever. See the spec `AUTOLEARN_DICTIONARY_SWARM.md`.
- **Impl:** `autolearn.py` — **pure core** (stdlib, unit-tested by `autolearn_fixtures.py`):
  `align()` (Needleman-Wunsch token diff), `classify(inserted, edited, config)` → Decision
  `{action: offer|silent_learn|ignore, old, new, confidence, is_proper_noun, reason}`. The intelligence
  (`§2` of the spec): edit-shape gate (**exactly one substitution, no insert/delete** — distinguishes a
  *correction* from a deletion/rephrase) → changed-ratio → **Double Metaphone** phonetic gate → Levenshtein
  orthographic gate → case/punct filter → **common-word filter** (`COMMON_WORDS` = inline set ∪
  `/usr/share/dict/words`, so real words aren't offered, proper nouns are). Anti-nag: `record_offered`/
  `is_declined` in `config['autolearn_declined']`; `apply_observation_guard` drops OS-autocorrect (change
  <300 ms post-insert, no keystrokes).
  - **`EditWatcher`** (AX read-back, daemon thread): armed by `main._arm_autolearn` after injection; polls
    `AXValue` (0.15 s interval, **1.6 s debounce**, 30 s deadline) on the original focused element. Fails
    **closed**: skips secure fields, terminals, and cases where the inserted text isn't found (Electron
    reads are flaky). Never touches the clipboard/injection path.
  - **UI:** `autolearn_widget.py::AutoLearnWidget` — a **non-activating cream pill** (matches the dashboard
    "Words today" card: bg `#EADFCE`, dark ink, near-black "Add to dictionary" button) shown bottom-center;
    never steals focus. Title names the word: *Add "Ramiz" to your dictionary?* / *Replaces "Rameez"…*.
    Add → `main._autolearn_result` → `dictionary.add_replacement(..., auto=True)` + `sounds.play_added()`
    chime + forces the dashboard to re-fetch (`loadDict()`).
  - History-view edits (`DashboardApi.edit_text` → `_learn_from_edit`) run the same `classify()`.
- **Gated by** `config['autolearn_enabled']` (default off). Toggle on Dictionary **and** Settings screens.
- **Known limits:** in-place watching is best-effort — reliable in native Cocoa fields, skipped in
  Electron/terminal/secure. Typo-of-a-typo can still be *offered* (the confirm widget is the user's gate).

## File tagging — spoken filenames → `@name.ext` (desktop only)

- **What:** in a supported IDE, saying a filename inserts a real editor `@`-reference. Spec: `FILE_TAGGING_SWARM.md`.
- **Impl:** `filetags.py` — detect IDE (`supported_ide`: Cursor, Windsurf, VS Code, Antigravity, Kiro via
  bundle-id sets + name match; `TAGGING_IDES`). Harvest open files via **macOS Accessibility**:
  **set `AXManualAccessibility`+`AXEnhancedUserInterface`** on the app element (Electron/Chromium hide
  their web AX tree otherwise), settle ~1.3 s (lazy tree), then a bounded BFS (≤4000 nodes, depth ≤40)
  reads `AXTitle`/`AXDescription` → `name.ext`. `harvest_async` runs the deep walk at record-start off the
  critical path. Seen files persisted (`config['filetag_files']`, LRU 200). `prompt_fragment` biases
  Whisper; `tag()` rewrites references in 4 passes (extension-present / strong-prefix / trailing-"file" /
  bare-multi-token-with-trigger), handling spoken separators ("dot"/"underscore") + extension homophones.
  Real `@`-chip insertion happens in `injector.py::_inject_with_mentions` (types `@`+name, Enter-selects
  the IDE picker).
- **Gated by** `config['filetag_enabled']`. **Not on mobile** (no IDEs).

## Text injection & target-app tracking (desktop)

- `injector.py`: `save_focused_app()` at record-start stores `_previous_app_{pid,name,bundle}` (the
  **dictation target**, not the live frontmost app which may be the overlay). `inject_text(text,
  allow_mentions=)` = `pyperclip` + `restore_focused_app` + Cmd+V CGEvent; when mentions are enabled and
  the text has an `@name.ext` in a tagging IDE, routes to `_inject_with_mentions` (falls back to plain
  paste on any failure). Windows equivalent: `win_injector.py` (clipboard + `_press_ctrl_v()` SendInput,
  `user32` foreground-window save/restore).
- **Windows clipboard save/restore (2026-08-28).** Dictation used to clobber the user's clipboard for good.
  `win_injector.inject_text(text, allow_mentions=, restore_clipboard=True)` now (1) snapshots the clipboard
  TEXT before copying the transcript (`snapshot_clipboard()`, Win32 `OpenClipboard`/`GetClipboardData`
  CF_UNICODETEXT via ctypes; retried 6× at 20 ms if another app holds it — still locked → paste proceeds
  with **no restore**), (2) records `GetClipboardSequenceNumber()` once the transcript landed, (3) after a
  successful Ctrl+V schedules a **delayed restore** on a daemon thread (`CLIPBOARD_RESTORE_DELAY_S` = 0.4 s,
  so the target has consumed WM_PASTE first) that is a **no-op if the clipboard changed since** (sequence
  number differs or text ≠ transcript). Non-text clipboards (image, files) and an empty clipboard are NOT
  restored — the transcript stays, as before. **Never restores on the fallback path**: UIPI-blocked paste,
  exception, or the sync-receive copy (`win_main._on_sync_receive` passes `restore_clipboard=False`) — there
  the user needs the transcript on the clipboard. Config `restore_clipboard` (default True) disables it;
  the dictation call site reads it from `self.config`. Pure decision logic is `should_restore_clipboard()`
  (tested in `win_bugs_fixtures.test_clipboard_restore_decision`, runs on any OS). macOS `injector.py` does
  **not** restore (only `transform.capture_selection` does, via try/finally) — parity is a follow-up.
- **Blocked-paste detection** (`paste_guard.py`, 2026-08): both paste primitives can be refused by the OS
  *without failing*, so `inject_text` used to report success while nothing arrived. macOS —
  `CGEventPost` is a **silent no-op without the Accessibility grant**; `inject_text` now pre-flights
  `paste_guard.can_paste()` (`AXIsProcessTrusted`, re-read every dictation so granting it mid-session works
  on the next one) and on failure copies the text, restores focus, returns **False**, and reports.
  Windows — **UIPI** refuses synthetic input aimed at a higher-integrity window (target running as
  administrator) and `SendInput` returns 0 inserted events, which the old `pyautogui.hotkey("ctrl","v")`
  discarded; `_press_ctrl_v()` checks the count instead (and always sends the key-ups, so a partial
  delivery can't leave Ctrl stuck). `report_blocked` shows a popup **once per reason per run** (re-armed if
  the grant flips) via a hook registered by `main.py::_prompt_paste_blocked` (`rumps.alert` on the main
  thread) / `win_main.py::_prompt_paste_blocked` (tkinter `askyesno`). Its confirm button runs
  `open_fix()`: macOS opens Privacy & Security → Accessibility; Windows relaunches elevated via
  `ShellExecuteW "runas"` — which **must close the singleton mutex handle first** (see `05-conventions.md`).
  The transcription is always on the clipboard before any of this, so a blocked paste is never lost and the
  pill reads "In clipboard · paste with ⌘V".

## Recordings — save / playback / retry

- **Desktop:** `recordings.py` — every capture saved as **16 kHz mono WAV** in `~/.verbal/recordings/{id}.wav`
  (LRU 60), written on a **background thread** so the archive never delays transcription (Hard Rule #37).
  `upload_cloud` → `recordings` bucket (`{user_id}/{id}.wav`), the bare **object path** (not a
  URL — bucket is private, MER-27) stored on the history entry. `DashboardApi._ensure_local_audio` signs a
  short-lived URL (`recordings.sign_url`) before downloading — the one choke point for
  `play_recording`/`get_audio` (base64 data-URI)/`retry_transcription`. Failed transcriptions saved
  `status:'failed'` for retry from History.
- **Mobile:** `lib/recordings.ts` mirror — `persist` (copy temp → `documentDirectory/recordings/`),
  `uploadCloud` (Storage binary upload, returns a bare object path), `ensureLocal` (signs via
  `signUrl`/`resolvePlaybackUrl` then downloads if needed); `historyStore.retryEntry`/`playEntry` both
  delegate to `ensureLocal`. Playback via `expo-audio`, prefers local then cloud.
- **Backend:** `recordings` bucket, **private** (MER-27, 2026-07 — was public), path `<user_id>/<id>.<ext>`.
  Signed URLs generated on demand (~180s TTL); a format-tolerant path extractor
  (`extract_object_path`/`extractObjectPath`) handles both new bare-path writes and legacy public-URL rows,
  so no backfill migration was needed.

## Notes

- **What:** synced, voice-first notes. **v2** (spec `NOTES_ENHANCEMENT_SWARM.md`) adds full-text search,
  auto-titling, structure detection (voice → interactive checklists), note ↔ source-recording linkage,
  raw+formatted dual storage, cost-controlled cleanup, four per-user feature flags, and conflict-pair sync.
- **v3 (2026-08, research-driven pass — competitive study of Voicenotes/AudioPen/Cleft/Superwhisper/
  Apple Notes/Bear/Keep):**
  - **Pinning end-to-end** — `is_pinned` finally has writers: desktop `set_note_pinned` (hover ☆ on list
    cards + ★ toolbar toggle) and mobile `notesStore.setPinned` (star in the editor top bar); PINNED
    section renders first on both platforms. Pinning never bumps `updated_at` (see `04` §notes).
  - **Grouped list (desktop)** — PINNED / Today / This week / Earlier eyebrow groups (mirrors Meetings);
    rows carry a compact mono meta line: relative date · checklist progress `☑ 2/4` (accent; green when
    complete) · recording count. Searching switches to a flat ranked list (no groups).
  - **Sub-second voice capture** — a mic button beside + in the desktop list header (`dictateNewNote()`:
    create + select + start dictating in one click) and a full-screen empty state whose CTA is
    "Dictate a note". Research finding #1: capture latency is the retention variable.
  - **Search upgrades (desktop)** — match highlighting (`hlText`, `<mark class="hl">`), previews centered
    on the first hit (`noteSnippet`), and a "Create ‘query’" action on empty results (query becomes title).
  - **Ask your notes** — Enter (or the Ask link) in the notes search box runs `DashboardApi.ask_notes`:
    token-overlap ranking (title 3×, body 1×) picks top 6 notes → ONE `chat_via_proxy` call → inline
    answer card with sources + dismiss. Mobile: same ranking client-side in `NotesListScreen.runAsk` →
    `lib/groq.askNotes`. Explicit action only, fails closed. (Voicenotes' defining feature.)
  - **Named restyle** — the ✨ button opens a 3-style menu: **Auto-structure** (default prompt) /
    **Flowing prose** (no scaffolding) / **Clean transcript only** (keep every word). Desktop
    `format_note_with_ai(text, style)` → `ai_cleanup.build_notes_system_prompt(style=…)`; mobile
    `reformatNote(id, style, from)` → `formatNoteWithTitle({style})` with mirrored prompts in
    `lib/groq.ts` (edit one, edit both). **Restyles read the ENTIRE visible note** (2026-08-15 user
    feedback: the old raw-transcript-first source silently dropped every typed word — "only formats the
    recent transcription"); the transcript-as-source path lives only behind the Original view's
    "Reformat from transcript" / "Retry formatting" (`from:'raw'` on mobile, `formatNoteStyled(style,
    'raw')` on desktop), plus an automatic fallback when the note body is empty (failed first cleanup).
    Explicit picks only — Hard Rule #12's once-per-dictation cost control is untouched.
    (AudioPen/Cleft/Superwhisper's most-praised feature family.)
  - **Per-card note management (desktop, 2026-08-15 feedback)** — every notes-list card has a
    hover-revealed ⋯ menu (`.ncdots` → body-appended `#ncMenu`, same `.nmenu` family/closer):
    **Rename** (inline — the card title becomes an input; Enter commits, Esc cancels; the open note
    rides the normal editor autosave, a closed note saves via `save_note` with `no_cleanup:true`),
    **Pin/Unpin**, and **Delete** (`delNoteById`, the same confirm + `delete_note` path as the editor's
    ⋯ menu, which also gained a Rename entry that focuses the title field).
  - **Mobile editor parity (2026-08-16):** `NoteEditorScreen` gained the same trio — an app-level
    undo/redo stack over `{title, body}` (snapshot per flushed autosave + around reformat/dictation
    replacements — the cases native input undo can't cover; ↶/↷ in the top bar), an **Aa text-size
    cycle** (S/M/L, AsyncStorage `flume_note_fs`, scales the body editor, raw-transcript editor and
    `MarkdownNote` via its new `fontScale` prop), and **Delete note** in the top bar (native Alert
    confirm → `removeNote`; pending autosaves are dropped first so they can't resurrect the tombstone).
    List-level delete already existed on mobile (long-press → multi-select); rename = the title field.
  - **Editor undo/redo + controls (desktop, 2026-08-15 feedback)** — the note editor owns an
    app-level snapshot undo stack (`NU` in `flume_dashboard_html.py`): native contenteditable undo
    dies whenever anything replaces the editor programmatically (AI reformat, restyle, re-render), so
    snapshots are taken per idle autosave (700 ms), before dictation appends, and around every
    programmatic replacement. ↶/↷ toolbar buttons + Ctrl/Cmd+Z, Ctrl+Y, Ctrl/Cmd+Shift+Z (the
    transcript view keeps native plaintext undo). Toolbar grew Word-ish controls: strikethrough,
    H3 heading, numbered list, and an **Aa text-size menu** (S/M/L, persisted in
    localStorage `flumeNoteFs`, scales body + transcript + title).
  - **Editable original + reformat-from-transcript** (the Cleft pattern) — "Show original" is now an
    editable view on both platforms (desktop `contenteditable` div → debounced `save_note` with the
    **`no_cleanup` control field** so a format-failed note can't fire a surprise LLM call; mobile
    `TextInput` → `updateRawContent`); a "Reformat from transcript" button re-runs the AI over the
    corrected text.
  - **Copy / export** — desktop overflow ⋯ menu: Copy as text / Copy as Markdown / Export .md / Export
    .txt (native save panel via `export_note_text`, ~/Downloads fallback on Windows) / Delete (the old
    red bottom button is gone). `htmlToMd()` walks rich-text content back to markdown so both storage
    forms export identically. Mobile: share-sheet button in the editor top bar. ("Export = trust.")
  - **Editor meta line** — `CREATED AUG 12 · 214 WORDS · 2 RECORDINGS` in mono under the title, word
    count updates live while typing. Checked checklist items render struck-through + dimmed on desktop
    (`li.done`; mobile's `MarkdownNote` already did).
  - Restyle/`formatNoteStyled` saves **markdown** as `content` (not rendered HTML) so mobile renders it;
    `format_note_with_ai`'s stale local-key gate was removed (clients hold no Groq key since IDI-178 —
    the proxy path needs none).
  - Considered and REJECTED for now: folders/tags UI (restraint — pins+search suffice at current scale),
    Keep-style card gallery (hurts text scanning), auto-sorting checked items to the bottom (rewrites
    synced content lines), karaoke word-sync playback (no word timestamps stored).
- **v3.1 desktop layout (2026-08-15, user-picked direction — NotebookLM's panel structure adapted to
  Flume dark):** the Notes screen renders as THREE floating rounded panes (`.nbgrid` replaces
  `.threepane` for notes only; History keeps `.threepane`): **Notes** (pill New/Dictate buttons, pill
  search, grouped list, ask card), **Note** (toolbar lives in the pane header; title + meta + body in
  the pane body; a NotebookLM-style **dictation bar with a terracotta FAB** at the bottom replaces the
  old toolbar Dictate button — `updateDictateBtn` now drives `#dictBar`/`#dictFab`), and **Studio**
  (2×2 pastel action cards reusing the fcard cream/sage/plum language plus a new `slate` pastel:
  Auto-structure / Flowing prose / Clean transcript / Export-menu; "THIS NOTE" rows = the editable
  original-transcript row + per-recording play rows — the editor `segbar` is GONE, recordings render
  here via `studioHtml()`; a light "Add note" pill sits in the pane footer). Distinct from the rejected
  Version B: this third pane is an ACTION pane, not a filter rail. Inside a pane the pane body is the
  ONLY scroller (Hard Rule #23 spirit) — `.edscroll .notebody`/`.noteorig` are `overflow:visible`.
  Studio hides under 1000px; the toolbar ✨ menu keeps restyles reachable there. Mobile keeps its own
  optimized screens (no three-pane on phones). **Selection + chrome behavior (same session):**
  NO note is selected by default — `curNote()` returns the SELN match or null, with **no fallback to the
  newest note** — and the Studio pane is rendered ONLY once a note is selected/created (`.nbgrid.nosel`
  = two columns until then; the editor pane shows a "Pick a note" prompt). The app sidebar collapses
  **only while a note is open** (the same moment Studio appears — merely landing on the Notes screen
  keeps the navigation visible); `.app.navhide` is driven by `applyNavCollapse()` (`ACTIVE==='notes' &&
  curNote() && !NAV_OPEN`), the hamburger (`#navHamb`/`toggleNav()`, rendered only while a note is open)
  brings it back, and any other screen restores it.
  **Auto-grow (same session):** since 2026-08-17 the default window is WIDE — macOS 1280×760
  (clamped to the screen's visible frame in `_build`), Windows 1240×740 — so Studio's 1000px
  breakpoint is met out of the box and the screens get the vertical room they're designed for (user
  feedback: the old 980×680 felt squat). The auto-grow below now mostly matters for users who shrank
  the window: opening a note fires `ensureStudioFits()` → `DashboardApi.ensure_window_width(1220,700)`
  → host `ensure_window_size` (macOS `FlumeWebDashboard`: animated content-size grow on the main thread,
  clamped to the screen's visible frame, top edge anchored; Windows `SharedDashboard`: pywebview
  `window.resize` **scaled by the system DPI** — see `05` Hard Rule #41, the un-scaled version silently
  never grew on scaled displays). Grow-only, fail-closed, and fires at most ONCE per Notes visit so a
  user who deliberately shrinks the window afterwards isn't fought on every note click. Belt-and-braces:
  if 600 ms after the request the page is still under the breakpoint (host can't resize / tiny screen),
  `.nbgrid.force3` force-shows the three panes squeezed, retired automatically once the user widens past
  the breakpoint.
- **v3.2 — Import + full dictation bar (2026-08-15):**
  - **Import from Meetings / Transcriptions.** Desktop: an "Import" pill beside New/Dictate opens a modal
    picker (`openImport()`, appended to `<body>` — `.nbgrid` clips overflow) with Meetings/Transcriptions
    tabs, live search, and one-click rows: one pick = one new note, modal closes, note opens. A meeting
    imports as markdown — summary ¶ + `## Decisions` bullets + `## Action items` as an INTERACTIVE
    task-list (`- [x]` with owner bolded + due inline) + an italic provenance line; the full row is
    fetched via the existing `get_meeting` on click (cloud-hydrated LIST rows lack summary/decisions —
    don't compose from them), falling back to raw transcript text when no summary exists yet. A
    transcription imports as its text + provenance. Composition is 100% client-side through the ordinary
    `save_note` — no new backend. **Windows:** capture is live (`MeetingManager` + WASAPI), and
    `DashboardApi.list_meetings`/`get_meeting` still have a cloud fallback
    (`meetings._fetch_meeting_rows`, module imports are platform-safe) so Mac-captured meetings show
    even when local capture isn't running — the Meetings screen and its import picker (`open_meeting` routes through the fallback too;
    `opened` returns every id so read-only rows never flash NEW). Mobile: `flume-ui/components/ImportNotesModal.tsx` (bottom sheet, same
    tabs/search/composition — exported `meetingToNote`/`historyToNote` mirror the desktop functions; JS
    `<Modal>` is allowed because NotesListScreen is a TAB screen, Hard Rule #14 bans it only inside
    native-stack modals), wired via a download icon in the NotesListScreen header → `createNote` + open.
  - **Dictation bar, full controls.** While recording the editor's bottom bar shows: cancel (discard —
    `note_dictate_cancel`, recorder stopped, audio dropped), a **live waveform** (28 bars driven by the
    REAL mic level — `note_dictate_level` returns `recorder.level`, polled every ~120 ms; bars freeze
    grey while paused), a mono **timer** (pause-aware, client-side), **pause/resume**
    (`note_dictate_pause` → `recorder.toggle_pause`), and the stop-FAB (stop + transcribe, unchanged
    path). `abortDictationIfLive()` DISCARDS a live recording on every context exit (switching/creating/
    deleting notes, leaving the screen) — previously those paths flipped the UI flag and left the mic
    running. Mobile's editor already had all of this (dock cancel/stop/pause + Visualizer + timer).
- **IDI-176 (2026-08), mobile:** notes live in a singleton `notesStore` with a realtime channel
  (`verbal_notes_<uid>`, rejoin/backoff, own-echo suppression — without it your own write's echo minted a
  FALSE conflict pair inside the 60s window) + pull-to-refresh + exported `reload`; editor autosave is
  debounced 500ms (flushed on back/unmount/background) and `updateNote` falls back to the cache when the
  optimistic create hasn't landed (edits can no longer be silently dropped); **conflict pairs finally have
  UI** — badge in the list, "Edited on two devices" banner in the editor with Keep-this-version /
  View-other-copy (promote), via `resolveConflict`; failed/empty dictation into a note shows a message and
  deletes the orphaned audio; `reloadFlags` runs on screen focus; all note writes respect the sync toggle.
- **Raw + formatted (Decision 1):** a dictated note stores **both** the raw transcript (`raw_content`) and
  the AI-formatted `content`; the toolbar's **"show original"** reveals the raw text. Pre-existing/typed
  notes have `raw_content` null → the affordance is hidden.
- **Cost control (Decision 2):** cleanup runs **once**, on the initial dictated save (creates formatted
  content + title). Typed edits never auto-format. Appended dictation cleans **only the new segment** and
  concatenates it. Re-running cleanup is explicit only: toolbar **"Reformat"** (or **"Retry formatting"**
  when the first cleanup failed/timed out — 8 s hard timeout → save raw + set the retry affordance).
- **Auto-title (Decision/Feature 2):** fires only on the first save of a note whose title is still empty;
  **never overwrites a manually-set title**.
- **Structure detection (Feature 3):** enumerable speech becomes markdown task-list items (`- [ ]`);
  checkboxes are interactive (toggle `- [ ]`↔`- [x]` in the underlying content, persisted immediately) and
  carry a real checkbox role/label. Flag-off still formats but keeps prose/plain bullets.
- **Audio linkage (Feature 4):** each dictation persists its recording and appends `{id,url,created_at}` to
  the note's `audio_segments`; a labeled per-segment play control appears (typed notes show none).
- **Feature flags (Decision 4, default on):** `notes_search_enabled`, `notes_autotitle_enabled`,
  `notes_structure_detection_enabled`, `notes_audio_linkage_enabled` — toggled in Settings; desktop reads
  via `feature_flag(cfg,…)` (`config`), mobile via `getNotesFeatureFlags`/`setNotesFeatureFlag`
  (AsyncStorage). First-run does **not** backfill existing notes (Decision 5); only new notes get v2
  behaviors, but search covers everything.
- **Deletion (IDI-158, 2026-08):** cross-device deletes are **tombstones**, never hard DELETEs — see
  `04-data-model.md` §notes for the full contract (`deleted_at` column, tombstone-wins merge, scoped
  back-fill, desktop cloud-first delete with `ok:false` on failure, dashboard `delNote` gated on `r.ok`).
- **Desktop:** `DashboardApi.fetch_notes/save_note/delete_note/set_note_pinned/ask_notes/
  export_note_text` (the orphaned `toggle_note_pin`/`pin_text` bridge methods were deleted in IDI-179;
  v3 added the real pin writer) — local-first
  (`config['notes']`) merged with Supabase `notes` via `merge_remote_note` (union + conflict-pair, see
  `04-data-model.md`). `note_dictate_start/stop` = in-note dictation (stop persists the recording +
  appends to `audio_segments` when linkage is on); `format_note_with_ai(text)` returns
  `{title, formatted_content}` in one LLM call; `search_notes(query)` = case-insensitive substring,
  title-over-content ranked, recency tiebreak. Dashboard UI (`flume_dashboard_html.py`): search field,
  hand-rolled markdown/checklist renderer (`role="checkbox"`), per-segment playback, show-original/reformat/
  retry affordances, and Notes feature-flag toggles in Settings.
- **Mobile:** `flume-ui/hooks/useNotes.ts` + `lib/notesStorage.ts` (AsyncStorage cache, `mergeRemoteNote`)
  + `notes` table. `useNotes.saveDictation` wires `formatNoteWithTitle` into the save path (first-vs-append,
  8 s timeout → `format_failed`); `reformatNote` = explicit Reformat/Retry. Search via
  `lib/notesSearch.ts::searchNotes` (same ranking). `NoteEditorScreen` renders markdown/checklists through
  the fresh `flume-ui/components/MarkdownNote.tsx` (NOT the legacy `lib/MarkdownText.tsx`), with
  show-original, reformat/retry chips, and per-segment playback (`expo-audio` via `lib/recordings.ts`).
- **Backend:** `notes` table — base cols `id,user_id,title,content,folder,is_pinned,device_name,created_at,
  updated_at` **plus v2** `raw_content text` (nullable) and `audio_segments jsonb '[]'` (see
  `supabase_notes_v2.sql`; details + conflict-pair/union/unknown-field sync in `04-data-model.md`).
- **Multi-select delete (mobile):** long-press a note card in `NotesListScreen` enters selection mode
  (checkmark affordances, count in the header); tap toggles, the header trash icon deletes the selection
  after a `confirm()` dialog. Backed by `useNotes.removeNotes(ids)` (one `.in('id',…)` cloud delete +
  per-id cache eviction). Opening a note is suppressed while selecting.
- **Sync identity (fixed 2026-07):** notes sync was broken by two bugs — (1) mobile inserted **without** an
  id so its local `note_<ts>` never matched the server-minted uuid (edits lost, rows duplicated), and (2) no
  back-fill of notes created before the `notes` table existed. Fixed by the **text `id`** column
  (`04-data-model.md`), mobile upsert-with-id (gated on sync), and a load-time back-fill. Notes have **no
  realtime subscription** on either platform (only `transcriptions` do) — they reconcile on notes-tab open
  (desktop `fetch_notes`) / screen mount (mobile `useNotes.load`), not live.
- **Known limit:** still no `is_voice` column — `isVoice` is inferred from `raw_content`/non-empty
  `audio_segments` (survives reloads for dictated notes).

## Canvas — shared clipboard

- **What:** a staging board to send text/links/images between your devices (one shared row per user).
- **M1/D1 redesign (2026-08-17)** — the UI is now honest about the one-slot model on both platforms:
  a **"Live on Canvas" hero** (payload clamped, origin device + relative time + word count, actions
  Copy / Clear — desktop adds **Save as note** via the ordinary `save_note` path) + a **device-local
  activity log** (bounded 20; mobile AsyncStorage `verbal_canvas_log`, wiped by `clearAccountData`;
  desktop localStorage `flumeCanvasLog`) + a **draft composer** (composing no longer edits the shared
  row in place — "Send to devices" is the one write; the desktop draft persists in localStorage
  `flumeCanvasDraft`). Mobile (`CanvasScreen`, M1 "Slot & feed"): chat-style composer (text/paste,
  photo button, **mic dictation → transcript lands in the field for review, send stays manual** via
  `useRecorder`), an "Earlier" feed of 2-line-clamped rows, and long content opens an **in-tree expand
  overlay** (never an RN `<Modal>` — the screen lives in the native-stack Menu modal, Hard Rule #14),
  which killed the "a long text looks like an open file" bug. The `useCanvas` hook contract changed to
  `{live, feed, sendText, sendPhoto, copyLive, clearLive, copyFeedEntry, refresh, toast, dismissToast}`
  (mock updated in the same change); all IDI-173 sync machinery (selective-column writes, explicit
  clears, device_id own-echo filtering, live toggle gating, rejoin/backoff, reset/catchUp) is unchanged.
  Desktop `fetch_canvas` now also returns `device_name`/`updated_at`/`own` for the hero card; desktop
  image sends carry the current LIVE text (never the draft). Backend/schema untouched.
- **Desktop:** `DashboardApi.fetch_canvas/save_canvas` + image support (`save_canvas_image_data`, native
  `NSOpenPanel`/`NSPasteboard` pickers → `canvas-images` bucket). `FlumeWebDashboard._canvas_listen_loop`
  = a `websocket` subscription to `postgres_changes` on `canvas`, emits `canvasRemote` to JS (ignores own
  writes). On receive it copies **text OR the image URL** to the clipboard and fires a macOS banner
  (`_notify_native` → `osascript`, fail-closed) — **regardless of the active tab**; the `canvasRemote` JS
  handler now updates the (always-present, hidden) canvas DOM without gating on `active==="canvas"`, so a
  photo received in the background is there when you open Canvas. (The legacy native `canvas_window.py` was DELETED in IDI-179.)
- **Mobile:** `flume-ui/hooks/useCanvas.ts` — `canvas` table (upsert `on_conflict=user_id`) + `canvas-images`
  bucket + `expo-clipboard` + `expo-image-picker`; realtime channel `canvas_${userId}`. On receive it copies
  text/image-URL to the clipboard and shows a transient **"Received from X — copied to clipboard"** toast
  (`toast`/`dismissToast`, rendered by `CanvasScreen`); a failed image upload now shows an explicit toast
  instead of silently no-op'ing. Skips own writes, haptics on receive.
- **IDI-173 (2026-08):** origin filtering is by stable `device_id` (name compare only for old-client rows —
  two same-named devices used to drop each other's updates); writes OMIT columns they aren't changing (a
  text edit can't null the image); **clears propagate** — an explicit `{content:'', image_url:null}` write
  applied by every receiver incl. the legacy native window (falsy-drops fixed); mobile fetches on open and
  applies the row (empty board included), with stable card ids so redelivered events don't duplicate;
  mobile `discard` on a synced card writes the clear; subscribe lifecycle is account-epoch aware with
  rejoin/backoff; the macOS writer's "Windows" default name is gone.
- **Backend:** `canvas` table (one row/user: `content`, `image_url`, `device_name`, `device_id`,
  `updated_at`); `canvas-images` bucket policy in `supabase_canvas_images_policy.sql`.

## Cross-device sync

- **What:** history/notes/canvas kept in sync across your signed-in devices; all keyed by `user_id`.
  **The sync toggle is LIVE and uniform (IDI-171):** one store per platform (`lib/syncStore.ts` mobile —
  feeding Menu/Settings/Devices switches — and `sync_enabled` desktop), gating
  history/notes/canvas/dictionary; ON triggers an immediate catch-up + channel join, OFF closes channels
  without touching local data; mobile runs a foreground (AppState) catch-up and every store rejoins
  dropped channels with backoff. Meetings edits + recording uploads gate on being signed in only.
- **Receive-path rules (review 2026-08-30):** only `postgres_changes` **INSERT**s are content — UPDATEs
  (retry rewriting text, `audio_url` patches, backend bulk touches) matter only as tombstones, because
  the 200-id dedupe is empty after every restart and an UPDATE replayed as fresh dictation overwrote the
  clipboard / pasted. **Backfilled rows are history-only**: `_deliver(record, live=False)` stamps
  `record["_backfill"]=True` and both `_on_sync_receive`s skip clipboard, paste and toast for them (a Mac
  whose socket was dead for days used to type every missed targeted dictation into the foreground app on
  reconnect). Backfill fetches newest-first (`created_at.desc`, delivered reversed) so a long gap never
  spends the 50-row budget on soon-stale rows. A rejected channel join (`phx_reply` status≠ok,
  `phx_error`, `system` error) closes the socket so `_run` reconnects with a fresh token instead of
  sitting open with zero subscriptions. `_remember` is locked (socket thread vs backfill thread).
  `SharedDashboard` restores `sync_target_device_id` from config, treats an empty device fetch as
  "unknown" (never flips an explicit target to broadcast on a timeout), and excludes this install by
  real device id. Fixtures `idi170_171` / `idi172_174` now use relative timestamps (the 3-day stale filter
  had silently broken their fixed Aug-6 dates).
- **Desktop:** `sync.py::SyncClient` — Phoenix WebSocket to Supabase Realtime, subscribes to
  `transcriptions` `*` events filtered by `user_id`, skips own inserts, honors `target_device_id`; ONE
  reconnect loop with a bounded backfill on (re)connect (content since last-seen + separate tombstone
  sweep — IDI-171/172); `push()` inserts via REST incl. `audio_url`/`status`. **On receive (IDI-172),
  `main._on_sync_receive` appends to LOCAL HISTORY + clipboard and auto-pastes ONLY when the row targets
  this device** — broadcasts no longer paste into whatever window is focused. History deletes are
  tombstones (cross-device); Settings has "Clear history" with an optional clear-everywhere sweep. Push
  targeting from `dashboard._target_device_id` (`__all__`/`__none__`/specific).
- **Devices LIST vs sync-target (fixed Jul 2026):** the dashboard "Paired devices" list is built from
  `sync.fetch_account_devices(user_id)` — **every** device on the account, each with an `online` flag
  (`last_seen` within 5 min) — NOT `fetch_devices` (which returns only the last-5-min set and is now kept
  only for the sign-in "is another device online right now?" detection). Both desktop hosts
  (`flume_web_dashboard._load_devices`, `shared_dashboard._load_devices`) list devices whenever **signed
  in** — no longer gated on the live `SyncClient` (`self.app._sync`), which previously forced the list
  EMPTY whenever content-sync wasn't actively running (so a signed-in-but-sync-off Mac showed no devices
  and, because it never heartbeat, was invisible to the phone). Those loops now also call
  `sync.register_device_presence(...)` every 30 s so a device shows **online** to others while its
  dashboard is open, independent of the content-sync toggle. Mobile's `DevicesScreen` already used the
  account-wide `fetchAccountDevices` (shows offline devices + a per-device sync switch), so this brings
  desktop to parity. Root cause of "phone and Mac can't see each other": the list was a live-only,
  sync-loop-gated view, not a persistent account-devices view.
- **Mobile:** `flume-ui/hooks/historyStore.ts` — local AsyncStorage cache is source of truth; realtime
  channel `verbal_history_${userId}` merges remote INSERTs (skips own, respects `target_device_id`,
  drops+prunes tombstones); real durations persisted (`duration_ms` — local cache AND the cloud column
  since 2026-08-16, see `04` §transcriptions). `useDevices` is a
  singleton store (IDI-177): ONE 60 s poll/heartbeat, shared target selection (picking a send-to device on
  Home reaches the navigator's routing immediately), `reset()` on sign-out stops all `devices` queries;
  per-device sync switch is SELF-only; other devices' rows get an honest "Remove from list" (user-scoped).
  **Send-target v2 (2026-08-16):** `useDevices` carries an explicit tri-state `SendMode` —
  `'device'` (targeted) / `'all'` (broadcast, Home's "All" pill = `setTarget(null)`) / `'none'`
  (**This phone only**: `addTranscription(..., pushToCloud=false)` skips the cloud insert entirely) —
  persisted in `flume_target_device` as a device id or the desktop-matching `'__all__'`/`'__none__'`
  sentinels, plus a `ready` flag (first load landed). The most-recent-device auto-fallback applies ONLY
  in `'device'` mode — an explicit All/none choice is never silently overridden by the poll.
  **RecordingScreen's chip is now a live tappable picker** (This phone only / All devices / each online
  device, `refresh()` on open) showing "Finding devices…" until `ready` — and the WYSIWYG rule: the
  choice displayed at Stop is FROZEN into a `SendChoice` passed through `onComplete`; the router routes
  from that, never re-reading the store (which used to adopt a target mid-recording — the "chip said No
  device, sent to my laptop anyway" race). Home shows matching This-phone/All/device pills keyed off
  `mode` (previously "All" also lit up in the none state). Resend paths target only in `'device'` mode.
  Desktop receive conditions audited the same day: `sync.py` drops rows targeted at another device
  BEFORE the callback, `_on_sync_receive` pastes only when targeted, broadcast = history+clipboard only.
- **Backend:** `transcriptions`, `devices` tables + realtime — both platforms push the full shape
  (`audio_url`/`status`/`target_device_id`) since IDI-172; see `04-data-model.md` §Sync model.

## Device pairing

- **Devices screen (desktop, reworked 2026-08).** PAIRED and ONLINE are presented as different things,
  because they are: paired = has a row on the account, online = heartbeat within
  `sync.PRESENCE_ONLINE_SEC` (120 s). `renderDevices()` splits the list into **"Online now"** and
  **"Paired, offline"** groups, each with a count; offline rows are dimmed (`.dcard.off`) so the live
  device is what the eye lands on, and every row states its platform plus a relative `last_seen`
  ("seen 3 weeks ago") instead of the raw type string. Header reads "N paired · M online now". The
  "SEND MY TRANSCRIPTIONS TO" pills carry a green dot on live targets. The header is `position:sticky`
  inside `.main` (`.dhead`) — the scroller is still `.main` per Hard Rule #23; do **not** nest a second
  scroller here. **"Remove all offline"** (`remove_offline_devices`) bulk-clears the offline group behind
  a confirm; it is a list removal, not a revocation, so any of those devices reappears on its next
  heartbeat. Nothing auto-prunes — see `04-data-model` §`devices` for why, and for the reinstall-identity
  fix that stops the list filling up in the first place.
- **Sync-target popover (desktop, 2026-08).** The full-screen Devices selector isn't the only way to
  change where dictation lands any more: clicking a device row in the sidebar (`#sideDevices`, now
  clickable) or the small **"Sync: <target>"** pill at the top of Home (`.homeSyncPill`, in `renderHome()`'s
  `.mhead`) opens `#syncPop`, a floating panel anchored under the click with the identical target pills
  (`syncSelectorHTML()` — one implementation shared by the Devices screen and the popover, so there's
  only one place that builds the option list). Picking a pill calls the same `set_target_device` bridge
  method the Devices screen uses; `setTarget()` then refreshes the sidebar, Home pill and popover together.
  The current target's sidebar row carries a small "SYNC" tag. Closes on outside click, Escape, or picking
  a target. Fixed the pre-existing gap where `SharedDashboard._device_refresh_loop`'s periodic `'devices'`
  push (every 30s) had no `VerbalNative` handler and was silently dropped — the sidebar/Home pill only ever
  reflected the device list from page load; `'devices'` now updates `STATE.devices`/`target_device_id` and
  re-renders. This is still the same GLOBAL, per-installation target (`dashboard._target_device_id` /
  local config `sync_target_device_id`) described above — no new schema, no per-device-pair matrix.
- **Already-paired scan (2026-08-30):** `claimPairing` returns `alreadyLinked` when the phone's stored
  user id already equals the host's; the PairDevice handler then shows "Already paired — this device is
  already linked to <host>'s account, nothing changed" instead of "Paired" and skips the store reset. The
  single-use code is consumed either way (the host's QR expires/refreshes as usual).
- **Row `device_name` is the SOURCE device (2026-08-30):** mobile `historyStore.addTranscription` now writes
  `getDeviceName()` to `transcriptions.device_name`; the `deviceTag` argument is only the LOCAL history
  label (callers pass the *target's* name in "send to <device>" mode, which used to leak into the row — the
  Mac showed its own name on phone dictations).
- QR-based, single-use token. Host (signed in) inserts a `pairings` row (`token`=`token_urlsafe(6)`,
  `expires_at`≈now+120 s), shows QR `flume://pair?t=<token>`. New device claims via the **`claim_pairing`
  RPC** (IDI-157: atomic guarded claim, server-side expiry — direct table reads/updates are gone) → adopt
  host `user_id` → enable sync. Host polls the `pairing_status` RPC; Cancel (and TTL expiry) revokes the
  token server-side via `cancel_pairing`, and the dashboard's "Pair a device" button is latched against
  double-clicks and shows an error when starting fails. Desktop `pairing.py` (`create_pairing`/
  `check_pairing`/`cancel_pairing`, `qr_svg` — hosting only; its dead claim fn was removed, IDI-156; all
  calls go through `auth_header`); mobile `lib/pairing.ts` (`extractToken`/`claimPairing`),
  `PairDeviceScreen` (expo-camera), claim handler in `RootNavigator`'s `PairDevice` screen.
- **Adoption mechanics (IDI-156, 2026-08):** the claim writes a **paired-account override**
  (`verbal_paired_user_id`) that `storage.getUserId()` checks BEFORE the Supabase session id — previously
  the session write-back reverted the adoption within milliseconds, making pairing a silent no-op for any
  signed-in user. The claim also runs the same account-switch teardown as `afterSignIn` (`clearAccountData`
  when the id changes, then the caller resets+reloads `historyStore`), registers the device under the host
  account, and the Settings "Account ID" field goes through the identical path. The override is cleared on
  real sign-in, sign-out, and account deletion. INTERIM: replaced by real session minting when `auth.uid()`
  RLS (IDI-29) lands — an id override cannot survive JWT-scoped policies.

## Google auth

- **Sign-in is REQUIRED on all platforms (IDI-166, 2026-08; ENFORCED on macOS in IDI-183):** the desktop
  first-run "Later" path and all anonymous-mode remnants are gone; the dashboard's sign-in wall is the only
  entry. Since IDI-183 that is enforced rather than merely un-advertised on macOS: **dictation itself
  refuses while signed out.** `VerbalApp._on_record_start` is the single choke point every start path
  reaches (menu row, toggle key, hold key), and it returns early after surfacing the sign-in wall —
  throttled to one window every 4 s, because a held hotkey re-fires. The menubar menu greys out every
  account row in the same state (see the menubar entry below). Both gates **fail closed**: an auth error
  reads as signed out. Failure UX is state-driven: `get_state` carries
  `auth_error` (+ new `DashboardApi.cancel_sign_in` frees the loopback port), so a canceled/timed-out
  OAuth attempt re-enables the button with an error instead of latching forever. A **dead session**
  (revoked/expired refresh token) is persisted (`config['auth']['session_dead']`), surfaced as a
  "Session expired — sign in again" banner, and makes `delete_account` return actionable guidance.
- **Desktop:** `auth.py` — Supabase Auth **PKCE loopback**: browser → `/auth/v1/authorize?provider=google
  &redirect_to=http://localhost:8765/callback`; loopback-only listeners on **port 8765** (`::1` +
  `127.0.0.1`, IDI-265 — see `05-conventions.md` #82) capture the code, exchange at `/token?grant_type=pkce`. Stores `config['auth']`
  (`user_id,email,name,avatar_url,access_token,refresh_token`) + sets `sync_user_id=user.id`. No Google
  secret in-app (Supabase holds it).
- **Mobile:** `lib/supabase.ts` + `flume-ui/hooks/useAuth.ts` — `signInWithOAuth({provider:'google',
  redirectTo:'verbal://auth-callback'})` + `WebBrowser.openAuthSessionAsync`; return URL parsed by
  `createSessionFromUrl` (PKCE `?code=` → `exchangeCodeForSession`, dedup via `_handledCodes`; implicit
  `#access_token` fallback); `Linking` listener for Android reopen. Only Google is real; Apple/email are
  stubs. Needs an EAS dev build (not Expo Go). **Session lifecycle (IDI-166):** `AppState` drives
  `startAutoRefresh`/`stopAutoRefresh` (RN requirement — backgrounded >1h no longer resumes expired);
  an involuntary sign-out (session died without the user tapping Sign out) sets `sessionExpired` on
  `useAuth`, rendered as "Your session expired — please sign in again" on Welcome; the Google button
  shows an in-flight state; `completeOnboarding` only clears genuinely stale sessions (a real signed-in
  user re-seeing onboarding is never silently signed out).
- **Setup facts:** `GOOGLE_AUTH_SETUP.md` (Web OAuth client, redirect
  `https://ovpcthjingugwvpxlsna.supabase.co/auth/v1/callback`; Supabase Redirect URLs include the loopback
  and the `verbal://` deep link). Details in `04-data-model.md`.

## Account deletion (MER-32, 2026-07)

In-app "Delete account" — App Store Guideline 5.1.1(v) requires apps with account creation to let users
initiate deletion in-app. **Server-side:** `supabase/functions/delete-account/index.ts`, `verify_jwt` on,
identity derived from the caller's JWT locally (never a body-supplied id — the function can only ever
delete the signed-in caller's own account). Order: purge DB rows across every `user_id`-keyed table
(`transcriptions`, `notes`, `dictionary`, `canvas`, `devices`, `meetings`, `push_tokens`, `groq_usage`) +
storage objects (`recordings/<user_id>/`, `meeting-audio/<user_id>/`, and a list+filter over `canvas-images`
since that bucket's namespace is flat, `canvas/<user_id>_<ts>.<ext>`, not folder-per-user) **first**, then
the Supabase auth user itself **last** — a partial failure leaves a recoverable signed-in state instead of
an orphaned auth user. Idempotent (retrying after a partial failure is safe: every delete is either
by-`user_id` or by-listed-path, and a repeat admin-delete-user call 404s harmlessly, treated as success).
Sign-in-with-Apple token revocation is an intentional deferred TODO (`revokeAppleToken()` stub — needs the
Apple Developer account, not available yet); Google-only deletion (the only live sign-in method) works
fully without it.

**Clients:** both call the same edge function with the real session JWT (not the anon key — the function
401s without one) via `app.auth.delete_account_remote(cfg)` (desktop, `whisperflow/app/auth.py`) /
`useAuth().deleteAccount()` (mobile, `flume-ui/hooks/useAuth.ts`), then wipe every local trace on success:
desktop `app.auth.wipe_local_account_data()` (clears `config['auth']`/history/pinned/notes/meetings/
dictionary, deletes the local `recordings/`+`meetings/` directories — a strict superset of `sign_out()`,
which deliberately preserves local caches for a same-user re-sign-in); mobile reuses `clearAccountData()` +
`historyStore.reset()` (the same sign-out teardown, Hard Rule #13). Two-step destructive confirm on both
platforms: desktop uses two sequential JS `confirm()` dialogs in the Settings "Account" card
(`flume_dashboard_html.py`); mobile uses two sequential native `Alert.alert` calls in `SettingsScreen.tsx`
(Hard Rule #14 — this screen is a native-stack modal, so the custom `ConfirmDialog` wouldn't reliably
receive touches here, same reasoning as the existing sign-out confirm).

Live-verified end-to-end (2026-07) with a disposable test auth user: seeded one row in every table + one
object in every bucket, called the function with a real JWT, confirmed all rows/objects/the auth user were
gone, confirmed a repeat call with the same token still returned success (idempotency), and confirmed a
request bearing only the anon key (no user JWT) was rejected with 401. The desktop Python client wrapper
(`delete_account_remote`) was also exercised directly against the live function, not just the edge function
itself via curl. `wipe_local_account_data()` was verified by code review only, not live execution — it
deletes real files under `~/.verbal/` and this development machine has a real, in-use installation.

## Meetings — capture, live transcript, hybrid summary

- **Two-speaker model — the Granola approach (2026-08-28, current).** Meetings show exactly two speakers:
  **the signed-in user's name** (`self`, mic) and **"Them"** (`s1`, ALL system audio — everyone else on the
  call). Rationale: without a bot inside the meeting (Otter/Fireflies/Fathom), nobody gets reliable
  per-person names from a mixed system-audio stream; Granola — the closest comparable Mac-native product —
  labels Me/Them and puts the value in the notes. Our diarization → "Speaker N" pipeline (below) split one
  person in two more often than it separated two people, and a wrong split shown with confidence cost trust.
  What changed: `_speaker_for()` always returns `s1` (`THEM_LABEL`), the 90 s-gap heuristic is gone;
  `_diarize()` is gated by `meetings_diarize_enabled` now **default OFF** and the voiceprint step
  (`voiceprint.process_meeting`) no longer runs at meeting end (both kept for fixtures / legacy meetings);
  the summary prompt no longer asks for `speaker_names` and instead says "s1 is everyone else — use a
  name from the transcript only when unambiguous, else 'the other participant(s)'"; the SPEAKERS
  VERIFIED/ESTIMATED tag is removed from the desktop Summary header and mobile `MeetingDetailScreen`
  (`speakers_source` is still written as `estimated`; the column stays). Renaming `s1` ("Them" → "Alice"
  in a 1:1) still works via `rename_speaker` on desktop. Meetings recorded before 2026-08-28 keep their
  stored `s1..sN` / "Speaker N" labels untouched.
- **Speaker diarization (2026-08-16 → retired 2026-08-28; history).** `meetings_diarize_enabled`, was default ON. The live 90s-gap
  heuristic (`SPEAKER_GAP_S`) stays for the in-meeting view, but it cannot split two people in
  conversation — everything remote lands on one "Speaker 1". At meeting end, AFTER the WAV upload and
  BEFORE voiceprint and the summary, `MeetingSession._diarize()` re-partitions the system-audio speaker
  ids from real who-spoke-when:
  - The audio never moves: `groq-proxy` (v11) signs a 1-hour URL for the already-uploaded
    `meeting-audio/<user>/<id>.wav` with the service role and submits it to AssemblyAI
    (`speaker_labels: true`, universal-2). Submit and poll are separate proxy actions
    (`{"diarize":{"object"|"poll"}}`) so no isolate ever sits in a poll loop; the desktop polls every 4s,
    ≤120s, on the end-flow worker thread where the meeting is already in its 'working' state.
  - Only speaker labels + times come back (ms→s converted server-side); the transcript TEXT stays Groq's.
  - `map_diarized_speakers()` (module-level, pure, pinned by `diarize_fixtures.py` — 14 cases) applies
    them: "self" is mic ground truth and never relabelled; the diarized cluster that lands mostly on
    self utterances IS the user heard in the mixdown and is excluded (else the user appears twice); a
    system utterance is only relabelled at ≥30% overlap (wrongly merging two people is worse than the
    status quo); new ids are s1,s2,… by first appearance; a name typed mid-meeting follows the id that
    received the majority of that speaker's utterances.
  - Ordering matters: diarize → voiceprint (now gets clean per-speaker windows) → summary (attributes
    action items to the right people).
  - Fails closed at every step (flag off, no upload/signed-out, key unset → proxy 503s, timeout, any
    exception): the meeting keeps the gap-heuristic labels exactly as today. Requires keep-audio + being
    signed in, since AssemblyAI fetches the WAV from the bucket.
- **Speaker accuracy pass (2026-08-27; superseded by the two-speaker model above — history)** — why "3 people showed as 2" and what changed:
  - **Turn-level labelling, not chunk-level.** System-audio chunks are now transcribed with Groq
    `verbose_json` + `timestamp_granularities[]=word` (`transcribe_with_status(..., words=True)` →
    `sidecar["words"]`); each utterance carries transient `words: [[w, t0, t1]]` (absolute s) during the
    session — **never persisted or synced** (`_public_transcript()` strips them; the live `utterance`
    event too). At diarize time `split_utterances_by_turns()` (pure, fixture-pinned) cuts a chunk where
    the diarized speaker changes, THEN `map_diarized_speakers()` labels the pieces. Before, one 8–22 s
    chunk got one label, so a person who only interjected inside someone else's chunk was erased.
    Utterances without words (local Whisper, ElevenLabs/AssemblyAI ASR, `self`) pass through unchanged.
  - **Self-cluster exclusion needs a clear majority** (`SELF_CLUSTER_SHARE = 0.7`): a diarized cluster is
    "the user" only when ≥70 % of its overlap lands on self utterances. The old bare plurality dropped a
    remote participant who talked over the user as a phantom.
  - **Language:** `diarize_submit(..., language=)` sends the meeting's pinned language; the proxy pins
    `language_code` when given, else `language_detection: true` (was hard-coded `"en"`). Deployed live
    as `groq-proxy` **v16** (2026-08-27); older clients that omit `language` get auto-detect.
  - **Provenance is visible on both platforms:** `speakers_source` = `diarized` | `estimated` — a cloud
    column (migration `meetings_speakers_source`, applied 2026-08-27; `null` on older meetings = treat as
    estimated) written by `row()`, mirrored in local meta, and merged by `get_meeting()`. Desktop Summary
    header shows **SPEAKERS VERIFIED / SPEAKERS ESTIMATED** with a tooltip explaining the fallback;
    mobile `MeetingDetailScreen` shows the same tag next to the speaker chips (`speakersSource` in
    `lib/meetings.ts`). A gap-heuristic guess is never shown with false confidence.
  - **Automatic names from the transcript:** the summary JSON now includes `speaker_names`
    (`{sid: name}`) — only for placeholder-labelled speakers whose name is unambiguous in the transcript
    (self-introduction or being addressed by name). Hard-validated in `_parse_summary_json` (real
    `s<N>` id, 1–2 alphabetic words, not "Speaker…", unique). `apply_speaker_names()` renames only
    "Speaker N" labels (never a user/voiceprint name), rewrites "Speaker N" mentions in the produced
    prose, and each rename feeds `voiceprint.learn_speaker` so the person is auto-named next meeting.
    Applied in `run_summary()` and the retry path (`rerun_row`, which now PATCHes `speakers`).
  - Not done (deliberate): no `speakers_expected` hint (participant count unknown), no reading of the
    meeting app's active-speaker label, no calendar attendees.
- **"You" → the user's real name (2026-08-28).** The mic speaker (`self`) is labelled with the signed-in
  account's name, not "You", everywhere it appears. Desktop `meetings.self_speaker_label(config)` reads
  `config['auth']['name']` (Google `full_name`; an e-mail-only value counts as no name → "You");
  `MeetingSession` persists it in `speakers.self` (so the cloud row, the summary prompt's speaker key, and
  mobile all see the name), `_diarize()` keeps it, and `with_self_name()` substitutes it at READ time in
  `list_meetings`/`get_meeting` (`DashboardApi._named`) for pre-2026-08-28 rows that stored "You" — a
  user-typed rename of `self` is never overridden. The meeting window fetches
  `get_self_speaker_label` (shared_dashboard) for the pre-meeting "Microphone" card (`#preMicSub`) and the
  live `speakerName()` fallback. Mobile: `lib/meetings.ts` `withSelfName()` runs inside `toMeeting()`
  (name from `ensureSelfName()` ← persisted Supabase session `user_metadata.name|full_name`, refreshed by
  `useAuth` via `setSelfSpeakerName`, cleared on sign-out); `meetingsStore.load()` awaits it before the
  first fetch, and `MeetingLiveScreen` uses `selfSpeakerName()` for its fallback. Signed-out → "You".


> **UI v4 — Notes-language panes (2026-08-16, user-approved proposal).** The desktop Meetings screen now
> renders as the same THREE floating panes as Notes (`.nbgrid`, shared behavior contracts: nothing
> selected on entry, sidebar collapse + window auto-grow keyed off the shared `paneOpen()` when a meeting
> is open, hamburger `toggleNav()`):
> **① Meetings list** — accent "New meeting" pill, live-REC bar (`.mlivebar`, Return/Stop), pill search
> whose **Enter runs ask_meetings** into a notes-style inline answer card (`MEET_ASK`; the old big Ask
> card/thread is GONE), and a COMPACT grouped list: one parent card per PINNED/date group (`.mgrp`) with
> faint dividers, rows (`.mgrow`) = overlapping speaker-avatar stack (`spColor`) + title/one-line summary
> + right-aligned mono time/duration/★✓ meta, unread dot, accent edge stripe on the open row.
> **② Meeting document** — pane header holds the Yours/Merged/AI hybrid tabs (restyled as pills,
> `.npaneHead .hnTab`; `hnView` now selects `.hnTab` unscoped), pin toggle (`meetPinToggle`), copy, and a
> ⋯ menu (Regenerate / Delete via `deleteMeeting`'s confirm — the old two-click `sumDelete` is retired).
> Body = title input + meta + summary → Decisions → Action items → Notes → marks/transcript expanders,
> all populated by the UNCHANGED `fillMeetDetail()` (the v4 shell `meetDocHtml()` keeps every element id;
> the `#mtgDetail` wrapper survives inside the pane so all its scoped widget CSS still applies —
> `.npane #mtgDetail` neutralizes only the page chrome). Bottom: the **playback bar** (`meetPlaybarHtml`),
> the dictation bar's twin — play FAB, click-to-seek progress wave, `mm:ss / total`, speed chip
> (1×/1.5×/2×), transcript playhead-follow via `timeupdate` (`pbTick`); disabled+captioned when
> `audio_expired`. The full-AI-notes sub-page renders in this pane too (`meetNotesPaneHtml`).
> **③ Studio** — pastel cards **AI Notes / Regenerate / Ask this meeting** (sets `MEET_ASK_SCOPE` →
> `ask_meetings(question, meeting_id)`, a new backend param that feeds ONE meeting's row as context) **/
> Export** (menu: copy summary, .md, .txt, **Send to Notes** — `meetingNoteMarkdown()`, the import
> composition factored out and shared with the Notes import picker); a **SPEAKERS section** (avatar +
> name + talk-time share bar from transcript t0/t1 via `speakerStats`) where **tap = filter the
> transcript to that speaker** (`MSPK`/`spkFilter` — their lines lit with a speaker-colored edge, others
> dimmed, a SHOWING <NAME> ✕ chip in the transcript box; `markPlaying` switched to classList so the
> playing highlight can't wipe filter classes), double-click = rename (`sumRename`, which now refreshes
> the Studio + list too); "This meeting" rows (Marked moments → expand box, Send to Notes); footer =
> light "Add note"-style New-meeting pill. Also fixed latent: teaser SVGs had NO size rule (rendered
> 300×150 in the old layout too).
> **v4.1 — the AI notes are EDITABLE on desktop (2026-08-16),** matching mobile's raw-markdown editor:
> a pencil toggle on the AI Notes pane flips `ntBody` into a mono `textarea` (`MNT_EDIT`/`mntChanged`,
> debounced 800 ms → the NEW `DashboardApi.set_meeting_notes(meeting_id, notes_md)` — PATCHes
> `meetings.notes_md` + bumps `updated_at` exactly like mobile's `updateNotesRemote`; returns ok:false
> on cloud failure so the editor shows "Not saved"). Regenerate now **confirms first** when notes exist
> (it replaces hand edits); every route away (`notesBack`/`openMeetingDetail`/`navTo`) flushes a pending
> debounce via `mntAbandon()`. Works on Windows too (cloud PATCH, no manager needed).
>
> **UI: widget kit v2 — COMPLETE** (`MEETINGS_WIDGETS_HANDOFF.md`, Jul 2026). Dot+label speaker chips,
> single-parent-card rows with faint dividers, glyph icon buttons (1.4 stroke), ↳ hybrid-note AI additions
> with Yours/Merged/AI tabs, v2 meeting list on the dashboard AND mobile (compact rows in one parent card,
> `MeetingListScreen.tsx`). Summary fully editable: transcript hover copy/inline-edit (`edited` flag),
> action items inline edit/delete/done + **due labels** (extracted by the summary LLM, `due` key), marked
> moments get **user notes** (`set_mark_note`), jump-to-transcript + delete. Per-row **AI regenerate** on
> hybrid notes (`regenerate_hybrid` → one focused LLM call). Meeting list: **pinned** (cloud `pinned`
> column, PINNED group first) and **NEW/unread** (local `meetings_opened`, cleared by `open_meeting`).
> **Voice fingerprinting** (`app/voiceprint.py`; **no longer run at meeting end since 2026-08-28** — one "Them"
> bucket has nothing to fingerprint; module kept, `learn_speaker` still fires on a manual rename): each non-self speaker gets a numpy log-mel
> mean+std embedding from the meeting WAV; named speakers update rolling prints in `config['voice_prints']`
> (LOCAL-ONLY, never synced); unnamed speakers auto-name on a decisive cosine match (≥0.92 + 0.02 margin)
> BEFORE the summary runs; hits land in the `recognized` jsonb column and render the fingerprint banner +
> avatar corner dot. Speakers are renameable from the SUMMARY too (double-click the header avatar chip
> or a transcript chip → `set_speaker_name`), which also feeds the fingerprint learner from the local WAV
> ("⚡ Voice print saved" toast). Scratchpad is a contenteditable with markdown-lite (⌘B/⌘I native, `- `→em-dash bullets
> with Enter continuation, numbered continuation, `# `→heading) — stored as plain text (`innerText`), and
> freshly-dictated text flashes accent. All list writes go load-then-patch (never write a list you didn't load).
- **What:** record a live meeting ON the Mac (system audio + mic — no bot joins the call), see a live
  transcript beside a personal scratchpad, and get a post-meeting hybrid summary: AI summary + decisions +
  action items + the user's own notes enhanced with transcript context. Spec: `MEETINGS_DESIGN_HANDOFF.md`
  (screens 31a–31h); availability: macOS full, iOS read-only (+ scratchpad edit), Windows capture via
  WASAPI loopback (`win_system_audio.py` — keeps a silence player running and reconnects up to 3× on
  device loss/switch, then surfaces `sysErr` in the `elapsed` tick; Rule #76) hosted in `WinMeetingWindow` (same `meeting_html()`; the
  pre-meeting language control is a custom listbox, not a native `<select>` — WebView2's OS combo
  popup ignores CSS overflow and covers Start recording; `05-conventions.md` Rule #66). No call
  auto-detect on Windows yet. **Two Windows fixes from the 2026-08-26 report:** (1) `WinMeetingWindow`
  is built once and re-used like the Mac panel, so it now intercepts pywebview's `closing` — X /
  Alt+F4 **hides** it (or collapses to the bar while recording/processing, `windowShouldClose_` parity)
  instead of letting winforms destroy the form — and drops its references on `closed`; before that,
  the first close left a dead handle and every later "Start meeting" was a silent no-op (Rule #67;
  Windows shutdown/log-off and Task Manager are still let through). (2) The default meeting title
  (`MeetingSession.__init__`, `"Meeting — Aug 26, 14:05"`) is built from `tm_mday` instead of the
  glibc-only `%-d`, which the Windows CRT rejected with "Invalid format string" — so every meeting
  started without a typed title failed on Windows (Rule #68). **And two from the 2026-08-28 report:**
  (3) collapsed **bar** mode is now real on Windows — it used to render as a full 700×480 titled
  window with the tiny pill floating inside, because `create_window`'s `min_size` became WinForms
  `MinimumSize` and clamped the shrink, and the logical/physical px mix drifted even the expanded
  geometry on scaled displays (Rule #71). `_apply_chrome` now mutates the form on the WinForms
  UI thread and `win_geometry` does one DPI-aware `SetWindowPos` (+ `SetWindowRgn` pill region): bar =
  borderless top-most pill top-center of the primary work area with host-eased hover-reveal, expanded =
  Sizable centered 880×620 with the minimum restored — and **minimizing during a live meeting
  collapses to the bar** instead of the taskbar (`_on_native_resize`, macOS focus-loss parity — a
  live recording must never run invisibly; idle minimize stays a plain minimize; Rule #67h).
  (4) The live screen's shortcut hints render **"Ctrl+."/"Ctrl+P"/"Ctrl+Enter"** on Windows instead
  of ⌘ chords (the keydown handlers fire on `metaKey||ctrlKey` and the Win key is OS-reserved) —
  part of the platform-string seam (Rule #80) that also replaced the dashboard/popover's hardcoded
  "This Mac" with `THIS_DEVICE` ("This PC" on Windows) in the sidebar, canvas, settings, meeting-list
  "this Mac only" tag and onboarding wizard. Both 2026-08-28 fixes are pinned by
  `scripts/win_smoke_isolated.py` (bar/expanded chrome via the native form, minimize-to-bar
  driven with a stubbed live session, rendered platform strings).
- **Desktop:** `meetings.py` (`MeetingManager`/`MeetingSession` state machine: idle→preparing→recording⇄
  paused→stopping→processing→ready|failed) + `system_audio.py` (SCK audio capture) + `meeting_window.py`/
  `meeting_html.py` (ONE morphing WKWebView panel: an ambient glassy **bar** top-center — that fluidly grows
  into the full window via native frame animation; content modes `permissions` 31h / `premeeting` 31b /
  `live` 31c; while recording, losing focus or closing collapses back to the bar; the separate
  `meeting_hud.py` was dead code, DELETED in IDI-179). **Short by default:** at rest the bar carries only
  the live dot + elapsed timer, same Capsule recipe as the recording overlay (IDI-184) — title, waveform and
  cancel/star/pause/stop live in `.barOpt`, revealed on hover only — pausing does NOT force it open (it
  used to; dropped per `05-conventions.md` Rule #58, since a paused meeting can sit paused indefinitely
  and the pill was staying maximally wide the whole time instead of shrinking to dot+timer). A paused
  meeting is signaled by the dot alone (greyed, no pulse); the same four actions also sit in the full live
  screen's header (`.mact`). **Cancel is destructive and distinct from Stop**: Stop finalizes (drains
  transcription, uploads audio, generates the summary, keeps a history row); Cancel throws the whole
  meeting away — no transcript, no summary, no history row, and it deletes the cloud row/audio + local WAV
  that already exist from the moment recording started. Gated behind a JS `confirm()` on both surfaces
  (`05-conventions.md` Rule #57). Hover is driven
  from Python (`MeetingWindow._start_hover_monitor`/`_on_global_mouse`, active only
  while `layout==='bar'`) since a background, non-activating panel gets no real CSS `:hover` on macOS — see
  `05-conventions.md` Rule #40.
  The panel is **live-meeting-only** (MER-46): reading a meeting happens in the dashboard, and when a
  meeting stops the panel collapses to a **handoff pill** ("Finishing notes…" → "Notes ready →", ✕ to
  dismiss) whose click calls `open_meeting` — `MeetingWindow.set_handoff(state, row)` on both platforms,
  driven from `MeetingSession._stop_impl`. See the retired-modes note in `05-conventions.md`.
  Dashboard (31a/31f/31g): Home `MeetingLauncherCard`/`ActiveMeetingCard`, a **dedicated "Meetings"
  sidebar destination** (`scr-meetings`: count header, New-meeting button, active-recording bar, search,
  Today/This-week/Earlier groups, delete, empty state — user preference; it originally shipped as a folder
  inside Notes), and a Settings group; the Windows popover gets a "Start meeting" row; the macOS menubar
  menu gets
  "Start Meeting"/"Return to Meeting". (Mobile keeps its Meetings entry inside the Notes tab — there is no
  sidebar on mobile.) `scr-meetings` is a **two-level route** (`MVIEW` = `list` | `detail`, plus the
  `MSUBNOTES` full-notes sub-page): the detail view IS the ported PostMeetingSummary — see
  **Meeting detail** below. Bridge methods on `DashboardApi`: `start/stop/pause/cancel_meeting`,
  `mark_moment`, `save_meeting_scratchpad`, `set_meeting_title` (live session) /
  `set_meeting_title_by_id` (any meeting — what the detail view's title field calls), `rename_speaker`,
  `list_meetings`, `get_meeting`, `open_meeting(_launcher)`, `delete_meeting`, `retry_meeting_summary`,
  `get_meeting_audio`, `get_meeting_permissions`, `test_meeting_capture`, `get/set_meeting_setting(s)`,
  `dashboard_page_ready`. Scratchpad dictation
  reuses the standard dictation path (paste lands in the focused scratchpad).
- **Meeting detail (31e, in the dashboard — MER-46, 2026-08):** the summary + full-notes views live in
  `flume_dashboard_html.py` under `#mtgDetail` / `#mtgNotes`, rendered into `meetingsMain`:
  `renderMeetDetail()` builds the shell once and `fillMeetDetail()` fills the cards (so an edit never
  rebuilds the DOM under an expanded transcript or a focused input), `renderMeetNotes()` + `openNotes()`
  own the markdown notes sub-page. Everything the panel's summary had is here — speaker avatars +
  fingerprint banner, hybrid notes with Yours/Merged/AI, decisions, action items, marked moments, full
  transcript with inline edit, TXT/MD export, two-step delete, regenerate, audio playback. All CSS is
  **scoped to `#mtgDetail`** because the panel's design vocabulary (`.card`/`.eyebrow`/`.legend`/`.mono`)
  overlaps the dashboard's own; the wider Flume palette tokens it needs were added to the dashboard
  `:root`. It replaced the panel's `summary` mode because one panel can only hold one mode: a past meeting
  fought the live screen, could not be read while another meeting recorded, and was yanked back to the bar
  whenever the panel lost focus mid-meeting.
- **Summary generation:** `meetings.generate_meeting_summary` — strict-JSON contract
  `{summary, decisions[], action_items[{owner,task,done}], hybrid_notes[{user_line, ai_addition}]}` via
  `chat_via_proxy` (2 attempts, 45 s, 24k-char transcript budget head+tail). Failure → status `failed`
  with explicit Retry (31e); silent meeting → `ready` with empty summary. Runs ONCE per meeting;
  regenerate is explicit (Notes cleanup cost-control philosophy).
- **Mobile:** read-only by design (empty states, not errors): `lib/meetings.ts` (fetch/map/realtime/
  scratchpad update) + `flume-ui/hooks/useMeetings.ts` (+`.mock.ts` contract) + `MeetingListScreen` /
  `MeetingDetailScreen` / `MeetingPlaybackScreen` (expo-audio playback with transcript highlight + tap-to-
  seek), reached from a "Meetings" folder row in `NotesListScreen` (routes on the Notes stack). The ONE
  mobile write: scratchpad edits (optimistic + debounced, last-write-wins).
- **Export:** the summary header has `TXT`/`MD` buttons → `DashboardApi.export_meeting(id, fmt)` → pure
  builders `meetings.export_transcript_txt/_md` (txt: header + `[m:ss] Name: text`; md: summary, decisions,
  checkbox action items, marks, notes, transcript) → native `NSSavePanel` (main thread), fallback
  `~/Downloads`. **Mark feedback:** pressing ★ pops the button, shows a "★ Marked m:ss" toast (expanded) or
  flashes the bar title (collapsed) — the marks footer alone was invisible feedback ("star isn't working").
- **Ask your meetings (chat Q&A):** the dashboard Meetings page has a chat panel → `DashboardApi.ask_meetings`
  → `meetings.ask_meetings`: fetches the ~25 latest cloud rows, keyword-ranks them against the question
  (title×4 / summary×2 / transcript×0.5), builds context from the top 3 (summary+decisions+actions + the
  question-relevant transcript lines ±1 neighbor, ~3.2k chars each), answers via `chat_via_proxy` with a
  grounded-only system prompt, and cites source meeting titles. Client keeps a 6-turn thread (Q bubbles /
  A cards / typing dots). Desktop-only for now.
- **Open/delete:** clicking a row (or the handoff pill) calls `open_meeting`, which fetches the row, marks
  it read, shows the dashboard and emits `openMeeting` into it → `openMeetingDetail(row)`. Both dashboards
  now **buffer** emits until the page's `dashboard_page_ready` handshake and flush on it (the same contract
  `meeting_page_ready` gives the panel) — without it an `openMeeting` pushed into a window built by that
  very click would evaporate. `open_meeting` also hides a consumed handoff pill, but never while a meeting
  is capturing/finishing. A meeting that finishes (or is retried) while its detail is open refreshes in
  place via `meetingsUpdated` → `refreshOpenMeeting`; a `deleted` payload (or a `not found` re-fetch) drops
  back to the list. Delete: ✕ on each row, plus a two-step confirm trash button in the
  detail header; deletes emit `meetingsUpdated` so the dashboard list refreshes everywhere.
- **Backend:** `meetings` table + `meeting-audio` bucket (`supabase_meetings.sql`, realtime on, RLS
  `TO public`). Bucket is **private** (MER-27, 2026-07 — was public); `meetings.audio_url` stores a bare
  object path, and both `shared_dashboard.py::get_meeting_audio` (desktop) and
  `MeetingPlaybackScreen.tsx` (mobile) generate a signed URL (~3600s TTL — long enough for a full
  playback+scrub session) before playing. See `04-data-model.md`.
- **Status/limitations:** system audio requires macOS 13+ and the Screen & System Audio Recording
  permission (31h checklist + 3 s capture self-test). Speaker identity is source-based v2 — user's name / "Them" (no diarization);
  meeting text NEVER goes to analytics; `meetings_max_minutes` (capture-length cap) is still stored but not
  enforced — a separate, not-yet-built concern from the reaper below.
- **Meeting-audio retention reaper (MER-31, 2026-07):** audio-only deletion, **off by default**. A daily
  `pg_cron` job (`reap-meeting-audio-daily`, 03:00 UTC) POSTs to the `reap-meeting-audio` Edge Function,
  which deletes the `meeting-audio/<user_id>/<meeting_id>.wav` object for meetings where `pinned = false`,
  `audio_expired = false`, `retention_days > 0`, and `now() - started_at > retention_days` — **never**
  touching `transcript`/`summary`/`decisions`/`action_items`/`hybrid_notes`/`notes_md`; the readable record
  survives, only the heavy audio goes. Fail-closed ordering: storage delete happens first, `audio_expired`
  (+ clearing `audio_url`) is only set if that actually succeeded, and rows still `status = 'processing'`
  are never touched (avoids the zombie-row race). `retention_days` is stamped **per meeting at capture
  time** from the desktop setting `meetings_keep_audio_days` (default **0 = never expire** — changing the
  setting only affects meetings captured afterward, not retroactively; a future billing tier would write
  this same column instead of it being user-editable — the seam is already there, no schema change needed).
  Clients: desktop's meeting detail view shows "Audio expired — notes and transcript kept" and clicks on
  the transcript no-op instead of erroring (`flume_dashboard_html.py`, `#mtgDetail` — was `meeting_html.py`
  before MER-46); mobile's `MeetingPlaybackScreen`/
  `MeetingDetailScreen` already degraded gracefully on a missing `audioUrl` (hide the player bar / show
  "View transcript" instead of "Play with transcript") — that same path now also covers the expired case,
  plus a small "Audio expired — transcript kept" line where the player bar would be.

## Insights — words, speed, streaks & rhythm (all platforms, Aug 2026)

Wispr-Flow-style statistics page. Desktop: a dashboard sidebar destination (`scr-insights` in
`flume_dashboard_html.py::renderInsights`, shared by macOS + Windows; the Home "Words today" card links to
it). Mobile: `InsightsScreen` (a bottom TAB since the V2 nav redesign 2026-08-16, plus a plum strip card on
Home).

**What it shows** (design: hero WPM gauge → pastel stat band → activity heatmap → breakdowns):
- **Speaking speed** — semicircular gauge (0–200 wpm, average-typist marker at 52) + a **"Top X% of
  typists"** badge (piecewise mapping vs global *typing* speeds: 52→50%, 100→top 4%, 150→top 0.5%,
  clamped 0.1–99; identical in `app/insights.py::_percentile` and `lib/insights.ts::percentile`).
- **Words dictated** (all time, + today, ▲/▼ % vs the prior 30 days, "≈ N novels" at ≥40k words).
- **Time saved** vs typing at 40 wpm (desktop: measured from real speech seconds; mobile: estimated from
  the WPM — needs ≥60 s of measured speech, tile shows "—" until then). **Mobile WPM is account-wide
  since 2026-08-16**: `transcriptions.duration_ms` syncs from every device (see `04` §transcriptions),
  so the phone clocks your speed from desktop dictations too — not just its own recordings.
- **Streak** (current — may end today or yesterday — and best ever) + a GitHub-style **activity heatmap**
  (last ~53 weeks desktop / width-fitted weeks mobile, terracotta sequential ramp
  `#1f2225→#4a2d24→#7a4030→#a84b33→#C85A3E→#E88D6A`, the live streak's cells glow, hover tooltips on desktop).
- **Where you dictate** — desktop: full per-app usage stats with a **30 days / All time** segmented
  toggle on the card — per app: words, share %, dictation count and average words per take
  (rank-colored bars, top 6 + Other). Mobile: per-device (JS has no frontmost-app API, so mobile rows
  carry no app signal — same limitation as context grounding's app hint).
- **Your rhythm** — 24-hour histogram, peak hour highlighted, morning share.
- **Polished for you** (desktop only) — words changed between raw transcript and pasted result
  (`insights.polish_delta`, word-level SequenceMatcher) + dictionary-rule counts.
- **Copy recap** (desktop, via `copy_text`) / **Share** (mobile, native share sheet) — a text summary.

**Data model — no new Supabase columns.** Desktop (`app/insights.py`, fail-closed everywhere):
- `config['stats_daily']` per-day ledger `{w,n,s,fx,apps,hh}` (`apps` values are `[words, dictations]`;
  the first build wrote bare word ints — readers accept both, writers upgrade in place) written by
  `record_dictation` from both
  `main._process_audio` and `win_main._process_audio` AFTER the paste; bounded to 800 days;
  `config['stats_total']` lifetime counters survive pruning; `config['stats_since']` = ledger birth date.
- `config['stats_cloud']` — incremental aggregate of the account's `transcriptions` rows
  (`refresh_cloud`, paginated REST via `auth.auth_header`, high-water-marked on `created_at`).
  **Merge rule (no double counting):** a cloud row from a day *before* `stats_since` counts regardless of
  device; on/after it, only rows from OTHER devices count (this device's are in the ledger). Tombstoned
  rows (empty text) count zero.
- Bridge: `DashboardApi.get_insights` (instant, cached) + `refresh_insights` (network fold-in; the page
  calls it once per dashboard session after first paint).
Mobile (`lib/insights.ts`): cloud-only aggregate cached in AsyncStorage `verbal_insights_cache`
(uid-stamped, wiped by `clearAccountData` and ignored across account switches), incremental fetch; WPM
from local history `duration_ms` PLUS synced rows' `duration_ms` (own-device rows excluded from the
cloud accumulator — no double counting); hook `useInsights` (+ `.mock.ts` contract). If sync is off the
screen shows a "this phone isn't being counted" hint.

Fixtures: `whisperflow/insights_fixtures.py` (accumulation, streaks, merge rule, percentile, polish
delta, fail-closed paths). Both spec files declare `app.insights` in `hiddenimports` (lazy import).

## Settings screen — grouped rail (desktop, Aug 2026)

- **Was:** twelve headed sections stacked in one scrolling column (every setting the app has, flat, with
  nothing ranked above anything else), fifteen prose subtitles, two rival Save buttons and 39 inline
  `style="…"` attributes. Two separate scroll-clamping bugs came out of that height.
- **Now:** `#settingsMain` carries `.setshell` and becomes a two-column grid — a **rail** of eight groups
  (Account, Dictation, Dictionary, Transform, Notes, Meetings, Shortcuts, Data & sync) plus a `#setPane`
  that renders **one group at a time** via `settingsPane(id)`. The pane, not `#settingsMain`, is the
  scroller, so each group keeps its own position and no group is tall enough to need one.
- `SETTINGS_GROUP` is module-scope because the ~30s state heartbeat rebuilds this screen — a local would
  throw the user back to the first group every rebuild. `setSettingsGroup()` re-renders and resets
  `scrollTop`. The `__HK_WAIT` freeze during hotkey capture is preserved.
- **Rail badges** (`settingsBadge`) show only state held **locally** — dictionary counts, notes flags,
  sync on/off. Anything fed by a late fetch would read as fact while still being a guess.
- Meetings and Transform still render themselves into `#meetSettings`/`#tfSettings`; both already guard on
  their container, so they simply no-op when their group isn't mounted — which also means their
  `Loading…` stubs can no longer shift the page under the cursor. Their own `<h3>` is hidden by CSS
  (`.setpane #meetSettings>h3:first-child`) since the pane already titles the group.
- **Two latent bugs this surfaced and fixed:** `saveSettings()` read `#model`/`#syncToggle`/`#userId`/
  `#devName` unconditionally and now throws when only one group is mounted → reads via `fieldVal`/`togOn`
  with the current state as fallback. And `.scard` was never a flex container, so every
  `style="flex-direction:row"` on one was **inert** and those cards (account, delete, clear history,
  dictionary) had always stacked — replaced by a real `.scard.row` class.

## Recording overlay / popover / hotkey / onboarding / updater / permissions / sounds (desktop)

- **Overlay** (`overlay.py`/`overlay_html.py`): non-activating pill (Recording → Transcribing → Done),
  bottom-center, `NSScreenSaverWindowLevel`, all-spaces; buttons via the bridge (`overlay_stop`/`_cancel`/
  `_pause`/`_copy`/`_dismiss`). iOS analog = the `Recording` modal screen.
- **Capsule sizing (IDI-184, 2026-08):** the pill was ~306×42 on macOS and a FIXED 470×44 on Windows —
  a third of the screen width on a 1366px laptop. It now rests at **123×36 (macOS) / 150×40 (Windows)**
  carrying only what is live (waveform + elapsed clock) and **grows on hover** to the full control bar
  (217 / 250). Nothing was dropped: pause/cancel/stop are revealed, and `esc` still cancels regardless.
  What went away is genuinely redundant — the uppercase RECORDING caption above the pill (the terracotta
  border plus a moving waveform already said it), the left "mute" disc (**decorative: no code ever set a
  mute state**), the recording-state device tag and the transcribing SRC→DST route (the Done pill names
  the destination, which is when it is news). A **paused** recording force-reveals the cluster and dims
  the bars, because with no caption the resume button is the only thing that says "paused". Waveform is
  11 bars on both platforms now (was 13 Mac / 10 Windows). Other states scale the same way: transcribing
  148/180 (Mac), done 202/313. The macOS panel shrank from 720×150 to **440×96** — it is transparent but
  still takes mouse events, so every pixel was a dead zone over whatever was underneath (−61% area).
  On Windows the *window* stays at its widest (340) and the pill is drawn content-sized and centred
  inside it, so hover never resizes the window (a resize would make Enter/Leave flap as the frame moved
  out from under the cursor); the surplus is chroma-keyed, hence invisible and click-through. Clicking a
  collapsed Windows capsule reveals the controls rather than hitting an invisible button — also the only
  way in on a touchscreen. **Hover is driven from Python on both platforms, not by CSS `:hover` or tk
  `<Motion>`** — see `05-conventions.md` Rule #40 for why neither fires for a background app's
  colour-keyed, never-focused panel. The **transcribing ring is rotated from Python** as well
  (`_start_spin_pump` → `window.VerbalSpin(deg)` at 20 Hz): written as a CSS `animation` it did not move
  at all on macOS, because that panel throttles animation timelines and JS timers alike — Rule #41.
  Windows needed no change; its arc already rides the 33 ms repaint loop's phase counter.
- **Live waveform (2026-08):** the recording pill's bars track the **real mic level**, not a loop.
  `Recorder` meters each audio block (`recorder.level`, 0..1, 0 while paused/idle); `overlay.py` pumps it
  into the page 15×/s and the page scrolls a 13-slot history at 30 fps (newest at the right). Windows
  (`win_overlay._sample_level`) scrolls the same number into its 10 PIL-drawn bars from the tk animation
  loop. Both fall back to the old ambient animation if the level ever stops arriving — see
  `05-conventions.md` Rule #35 for the curve and the fail-open contract. **Mobile is still decorative:**
  `flume-ui/components/Visualizer.tsx` takes hardcoded `heights` from `RecordingScreen.tsx`.
- **IDI-178 polish (2026-08):** Transform pill — Replace is single-fire (latch + synchronous rewrite
  consume), errors render on whichever pill is visible, the LLM worker can't strand `_busy` (run-token +
  try/except), busy state has a visible Cancel. Meeting window — `preStart` flips to live only on a real
  `{ok:true}` (errors render on the pre-start modal), bridge methods use the lazy `_meeting_win()`
  accessor, and a new `MeetingManager.processing` state keeps the red-X collapsing to the bar while the
  summary generates ("Still finishing your meeting notes…" + a done/failed notice if hidden). Auto-learn —
  Add/close are double-click latched and a pre-empted card still records its offer (anti-nag, Rule #9).
  Menubar — "Reset Onboarding (dev)" only exists under `VERBAL_DEV`; model checkmark default is the real
  `"base"`; new "Check for Updates…" item with an explicit "you're up to date" alert.
- **Menubar menu** (`menubar_menu.py`, macOS, IDI-183): a real `NSMenu`, left-click. Header row (custom
  `NSView`: mark, status, hotkey hint / waveform + elapsed / meeting timer, words-today) → Start
  Recording · Start Meeting → Recent ▸ (last 10, click copies; Open History…) · Canvas (N) ▸ · Notes →
  Recording Mode: <value> ▸ · Offline Model: <value> ▸ · ✓ Auto-detect Meetings · ✓ Sync to My Devices
  (disabled while signed out) → Open Flume ⌘O · Settings… ⌘, · sign in/out → Check for Updates… · About
  Flume · Quit ⌘Q. `Reset Onboarding (dev)` still only exists under `VERBAL_DEV`.
  **Signed out, the menu is locked:** every account row (record, meeting, Recent, Canvas, Notes, mode,
  model, auto-detect, sync, Settings…) is disabled, the Recent/Canvas submenus are emptied so the previous
  account's local history isn't on display, the words-today count is suppressed, and the header reads
  "Sign in to get started". Only **Sign in with Google**, **Open Flume** (which renders the sign-in wall),
  Check for Updates…, About and Quit stay live — otherwise there is no way back in. A dead session
  (identity kept, refresh token rejected) keeps the rows usable but the header says "Session expired". Rebuilds itself on open
  via `MenuController.menuNeedsUpdate:`; the ⌘-equivalents are menu-local (the global dictation hotkey
  stays in `hotkey.py` and is advertised in the header subtitle instead of faked as a key equivalent).
- **Popover** (`flume_popover_html.py`): **Windows only** now — the tray-click pywebview mini-dashboard
  (`win_popover.py`). The macOS `NSPopover` host (`flume_popover.py`) was deleted in IDI-183. Built once
  and re-used: Alt+F4 hides it (pywebview `closing` cancelled) and `closed` drops the handle so the next
  tray click rebuilds — the same dead-handle recipe as `WinMeetingWindow` (`05-conventions.md` #67,
  2026-08-26). Its `quit_app` goes through `win_main._hard_exit` (#59b).
- **Hotkey** (`hotkey.py`): `NSEvent` global monitor; default key **54 (Right Cmd)**, ESC cancels. Hold
  mode (down=start/up=stop) vs Toggle mode (debounced tap). Windows uses `pynput` (default `alt_r`).
  **Tap-to-latch (Aug 2026):** in HOLD mode the key now does both jobs — a press longer than
  `TAP_LATCH_MAX_SECONDS` (0.8s) is push-to-talk as before, while a shorter press is a TAP that leaves the
  recording running hands-free until the next tap. Previously a tap started and stopped a recording inside
  ~0.3s, which `_on_record_stop` discarded as "too short", so tapping looked like the app ignoring you.
  Two guards keep it honest: a press with any **other key struck during it** is a chord (Right ⌘ + C), never
  a latch; and the latch is dropped by ESC, `set_mode` and `_reset_to_ready` (`clear_latch()`) so it can
  never survive the recording it refers to. Mirrored in `win_hotkey.py`; pinned by `tap_latch_fixtures.py`
  (15 checks driving the real `_handle_event` with fake events). TOGGLE mode is unchanged.
- **Onboarding:** dashboard JS flow; `DashboardApi.complete_onboarding` sets `config['onboarded']`. Mobile:
  `OnboardingScreen` (3 slides) + AsyncStorage `flume_onboarded`.
- **Updater** (`updater.py`): polls Supabase `app_versions_latest` per platform, downloads to temp with
  sha256 verify — **fail closed**: a row without a `file_hash` is refused, never installed (IDI-260,
  see `05-conventions.md` #81) — installs (`.dmg`/silent `.exe`) then exits. Binaries are GitHub Release
  assets, not Supabase Storage (IDI-224, 2026-08 — see `05-conventions.md` #50).
  **Persistent "update available" UI (2026-08-23):** a one-shot alert used to be the only signal, so
  dismissing it lost the update until the next periodic check happened to re-alert. Now a small
  terracotta badge dot composites onto the menu-bar icon (mac, `main.py::_badged_icon_path` — rendered
  as a non-template image since NSStatusItem template images are flattened to one solid tint and can't
  show a distinct badge color) / tray icon (Windows, `win_main.py::_create_icon_image(badge=True)`) the
  moment a newer version is found, plus a persistent "Update available (vX.Y.Z)" menu row — both survive
  a "Later" dismissal for the rest of the session (gated by a per-version seen-dialog flag, not a
  blanket suppression) and only clear once a still-newer version supersedes them or the app relaunches
  post-update. (Windows' `auto_update=True` mode used to skip the badge/menu entirely; since
  2026-08-26 the badge, tray row and dashboard banner show in that mode too, because the silent
  install now waits for the app to be idle — see below.)
  **In-dashboard update flow + one-surface rule (2026-08-25):** the dashboard now carries its own update
  banner (Update available → downloading % → "Restart to update", user-clicked, never auto-install) plus
  a Settings > Updates group (current version + Check for Updates), backed by
  `DashboardApi.get_update_status/check_for_updates/start_update_download/install_ready_update` and
  `main.py`'s `_update_phase` state machine. With that in place, AUTOMATIC checks (startup + 4h timer)
  no longer pop the native OS dialog on macOS — badge + menu row + banner only; the native
  dialog fires solely for the explicit "Check for Updates…" menu item or the "Update available" row
  ("two popups per version reads as nagging" — live feedback). **Windows is the exception (2026-08-28):**
  an automatic find shows the tk dialog **once per version** (`update_dialog_seen_version`, topmost,
  "Download and install now?" + a note that "No" lets `auto_update` install it silently when idle) —
  badge-only was reported as "Windows is not picking up updates, no popup", because the 4 px tray badge
  and a `/VERYSILENT` background install are invisible. "Yes" claims `_update_phase='downloading'`
  synchronously so the auto_update branch that runs next does not start a second download. `install_update()` exits via `os._exit`,
  not `sys.exit` — every caller is on a worker thread (see `05-conventions.md` #64).
  **Windows parity + "it never actually checked" fix (2026-08-26, Flume 1.0.33 never saw 1.0.34):**
  the Windows app fired its ONLY check of the session at t=0 — inside `updater`'s 30 s post-launch
  gate — then a once-per-session flag made every later call a no-op, so Windows never asked Supabase
  at all; and the dashboard's update bridge read `_update_available` etc. straight off the app object,
  which `VerbalWinApp` didn't have, so every 30 s poll raised `AttributeError` and Settings › Updates
  was dead on Windows. Now (`05-conventions.md` #69): `VerbalWinApp` owns the same
  `_update_available/_phase/_progress/_ready_path` state machine as macOS (`_pending_update` is an
  alias); `_update_check_loop` checks 35 s after launch and every 4 h; the tray gets a **"Check for
  updates..."** row (Mac-parity — the only Windows caller of `announce_current=True`, so the "You're
  up to date" dialog is reachable); every explicit click on either platform passes
  `check_for_update(force=True)` to skip the gate; and `DashboardApi.check_for_updates` is
  synchronous (≤ 8 s) and returns `available`/`version` so the button's toast can't contradict the
  banner. **Windows `auto_update=True` (the default) is unattended but no longer abrupt:**
  `_download_and_install(update, silent=True)` downloads with progress, parks the installer as phase
  `ready` (banner: "ready to install" / "Restart to update" — clickable any time) and only runs the
  `/VERYSILENT` install + `os._exit` once `_app_busy()` — recording, transcribing/injecting, or a
  meeting capturing/post-processing — has been False for two consecutive 1 s polls; it abandons the
  parked installer if a newer version supersedes it mid-wait (and chains straight into that one), or
  if the user already clicked "Restart to update". The tray dialog's "Yes" (an explicit click,
  `silent=False`) installs immediately. Every download/install is single-flight
  (`_update_download_lock`), a periodic re-check landing mid-download keeps the in-flight state instead
  of yanking it on a transient `None`, and any raise lands on phase `failed` (banner offers Retry) on
  both platforms — `main.py::_start_update_download` gained the same try/except. `updater.py`'s
  `time` import moved to module level: `download_update`'s retry backoff raised `NameError` on the
  first transient error, so its 3-attempt retry had never run.
- **Permissions** (`permissions.py`): accessibility / microphone / system-audio / notifications status +
  request, surfaced via `DashboardApi.get_permissions/request_permission`. On Windows the module's
  bottom-of-file shim overrides `check_accessibility()` to `"granted"` — correct, because Windows has no
  paste permission; its paste blocker is UIPI, detected after the fact by `paste_guard.py` instead.
  Accessibility is also read on the dictation path now, not just by the onboarding wizard — see
  **Blocked-paste detection** above.
  **Mic permission is now actually requested on the path a real user takes (2026-08-23).** Previously
  `request_microphone()` (mac) / the Windows Settings deep-link were only reachable from a
  Settings/Permissions screen nobody visits on first install — the hotkey record-start path just opened
  the mic directly and failed silently if TCC hadn't granted access yet, which is why Flume never showed
  a permission pop-up the way apps like Zoom do. Mac's `_on_record_start` now calls
  `_ensure_mic_permission()` first (checks/requests, caches a `'granted'` result forever so the hot path
  stays fast, and shows a one-time `rumps.alert` with a Settings deep-link if denied). Windows has no
  programmatic request API at all (access is gated entirely by Settings > Privacy > Microphone with no
  OS prompt ever appearing for a blocked desktop app), so its fix is detection instead: a failed mic open
  now shows a one-time native toast (winotify, with a `ms-settings:privacy-microphone` action) via
  `win_main.py::_notify_mic_permission_blocked`, gated by `config['mic_permission_notified']` (same
  anti-nag shape as `autolearn_declined`, Rule #9) and cleared automatically the next time the mic opens
  successfully so a later regression is reported again.
- **Sounds** (`sounds.py`): `afplay` system AIFFs — `play_start`(Tink), `play_stop`(Pop), `play_done`(Glass),
  `play_added`(Hero, the auto-learn confirm chime).

---

For data shapes, tables, auth internals, and sync push-shape differences → `04-data-model.md`.
For conventions, gotchas, the design system, and dead/legacy modules → `05-conventions.md`.


## Notes — Granola-style note-maker (Jul 2026 upgrade)

The notes LLM prompt (`ai_cleanup.NOTES_FORMATTER_SYSTEM_PROMPT`, mirrored VERBATIM in mobile
`lib/groq.ts::NOTES_FORMATTER_PROMPT`) is a **world-class note-maker** engineered against six
explicit criteria and tuned over four live eval iterations (v1 formatter → v4):
(1) completeness floor — compression removes WORDS never INFORMATION (every fact/number/name/
commitment/reason/open-question survives; reasons stay ATTACHED to their bullet); (2)
proportionality — tiny thought = 1–2 clean lines with zero scaffolding, dense debrief = full note;
(3) 3-second scannability — decisions/dates/owners bolded, consequential line first; (4) scenario
shapes — debrief (Decisions/Next steps/Open questions/Notes), tasks (owner+due inline), idea dumps
(rationale on the same bullet, speaker's own ranking kept), journal (prose in the speaker's voice,
NO bullets/headings), technical (steps+backticks); (5) truth discipline — self-corrections resolve
to final, "maybe" never upgrades, zero invention; (6) writer-not-stenographer — polished
capitalization/punctuation, spoken meta-preambles ("remind me…") stripped. Known failure modes each
rule guards: v1 over-summarized (bare noun-phrase bullets, rationales lost), v3 went verbatim-
lowercase. Checklist syntax ("- [ ]") stays exclusively in the flag-gated structure-detection
appendix. Eval harness: scratchpad `notes_eval.py` pattern (4 scenario transcripts); fixtures
`notes_fixtures.py` 66/66.

## Live meeting on mobile + meeting-start push (Jul 2026)

Follow a meeting LIVE from the phone while the Mac captures it. Desktop
(`meetings.py`): `row()` carries a `live` bool (true while preparing/recording/paused);
`_cloud_push_live` PATCHes ONLY transcript/speakers/duration/live every ≥4s during the
meeting (never scratchpad — mobile owns that live), so the phone streams the transcript
in via the existing realtime UPDATE subscription. On stop the final write flips `live`
false. Mobile `MeetingLiveScreen.tsx`: REC pill + locally-ticking elapsed, auto-scrolling
live transcript with speaker dots, and a sliding segmented control to a synced Notes pad
(debounced `updateScratchpadRemote`). `lib/meetings.isLiveNow` guards a 90s staleness
window (desktop crash → stale `live` never traps the UI). The list shows a LIVE banner
that routes to the live screen; when the meeting ends the live screen `replace()`s to the
finished detail. New column `meetings.live`.

**IDI-175 (2026-08), mobile meetings hardening:** one singleton `meetingsStore` (the four screens shared
a channel TOPIC but not a channel — one unmount killed another's subscription; `lib/meetings.ts` now
multiplexes ONE channel to N listeners with rejoin/backoff) with own-echo suppression so a notes-edit echo
can't clobber in-flight text; fetch errors keep the previous list + show a retry banner (a blip used to
blank it); scratchpad/notes writes go through a pending-retry queue (latest wins, flushed on
catchUp/reconnect, "Couldn't save — will retry" rendered) and are **CAS on `updated_at` +
user_id-scoped** — a desktop regeneration mid-edit freezes the field and offers Reload instead of being
overwritten; `generateMeetingNotes` has a 30s abort; playback URL resolution has an error state + retry.

**Meeting-start push:** desktop `_notify_start` fires the `notify-meeting-start` edge
function on meeting start → reads `push_tokens` (new table) → Expo Push API. Mobile
`lib/notifications.ts` registers an Expo push token on launch and is DEFENSIVE — every
expo-notifications call is a lazy `require` in try/catch, so a dev client built before the
native module was added never crashes (remote push lights up on the next native build; the
`expo-notifications` config plugin is in app.json). Local-notification + foreground handler
paths also present. Simulators can't receive real push (needs a device + APNs).

## Meeting Notes page (Jul 2026)

Full AI notes of a meeting — a dedicated PAGE inside the meeting window (MODE `notes`), not a new
window. Generated by `meetings.generate_meeting_notes` (`MEETING_NOTES_SYSTEM`: **analyst-grade**
notes matching a top human write-up — `## TL;DR` (3–6 bullets, skipped for a trivial note), `##
<Topic>` sections with nested sub-bullets and **bold** load-bearing facts, **Markdown TABLES**
(mandatory whenever 3+ items share fields — cost breakdowns, option comparisons, pros/cons,
schedules; derived values computed, never invented), `## Decisions` with reasons, `## Action items`
as checkboxes with owner/due and a `### Phase N` PHASED ROADMAP for multi-step plans, `## Open
questions`; proportional — rich when the call is rich, two lines when it's thin; written in the
deterministically computed OUTPUT LANGUAGE). ONE LLM call per meeting (`max_tokens=4000`,
`timeout=60s`), LAZY: generated on first open of the page, cached in the new `meetings.notes_md`
column (cloud-persisted), Regenerate button re-runs it. Rendered by a self-contained markdown
renderer in `meeting_html.js::mdRender` (##/###, - and 1. lists, - [ ] checklists, **bold**,
`code`, **GitHub-style tables** → `.ntTable`; first paragraph styled as an accent-bordered context
callout). Entry points: "Open notes ↗"
in the hybrid-notes card header; when the user took no scratchpad notes the card body previews the
first lines of the AI notes (or offers "Generate meeting notes"). Copy button exports the raw
markdown to the clipboard.

**Mobile parity (iOS, Jul 2026):** `MeetingNotesScreen.tsx` renders the same `notes_md` with a
self-contained RN markdown view (context callout, ## sections, bullets, 1. lists, - [ ] tasks,
**bold**, `code`, **tables** via flex-column `MdView` rows); when `notes_md` is absent the phone
generates it on-device via `lib/groq.ts::generateMeetingNotes` (same `MEETING_NOTES_SYSTEM` prompt,
`max_tokens=4000`, + deterministic output language) and persists via `updateNotesRemote` so every
device gets it. `MeetingDetailScreen` gained
a Notes entry row, tappable action-item checkboxes (`updateActionItemsRemote`, full-list write),
due-date labels, and marked-moment user notes. New cloud column `notes_md`; mobile Meeting type +
`toMeeting` carry `notesMd`/`pinned`/`recognized`.

**Notes are now editable on mobile (Jul 2026):** a pencil toggle in the header swaps the rendered
`MdView` for a raw-markdown `TextInput` (edits are plain markdown source, not WYSIWYG); a checkmark
returns to the rendered view. Wiring mirrors the scratchpad's optimistic-update + 600ms-debounced-write
shape (`useMeetings.ts::updateNotes`, both the real hook and `useMeetings.mock.ts` — the two must stay
contract-identical) → `lib/meetings.ts::updateNotesRemote` (pre-existing, previously only called after
AI regeneration). The screen also hides the bottom tab bar (`RootNavigator.tsx`'s
`getFocusedRouteNameFromRoute` check, same mechanism `NoteEditor` already used) and now has its own
"Play with transcript" button (previously only on `MeetingDetailScreen`) linking to
`MeetingPlaybackScreen` — see the tap-to-seek/highlight sync described just above.

## Meeting auto-detection (Granola-style, desktop, Jul 2026)

Flume notices a call in progress and pops a floating **"Meeting detected · <source>"** pill with a
one-click **Take notes** button — no more manually hitting Start Meeting. macOS-only, meetings-only,
fails closed.

- **Detection** (`app/meeting_detect.py`): a `rumps.Timer` (5 s) runs `detect()` **on a background
  thread** (the scan can block ~1 s) and applies the result on the main thread. It enumerates windows
  via **`SCShareableContent`** (ScreenCaptureKit) — the reliable title source: with the Screen-Recording
  permission Flume already holds it returns EVERY on-screen window's title, including background windows.
  `CGWindowListCopyWindowInfo` is only a **fallback** (on macOS 14/15 `kCGWindowName` is empty for all but
  the frontmost window, so it alone misses a Meet call you've tabbed away from — this was the "not
  detecting" bug). It looks for an *in-call* window, not just an open app: a **Zoom Meeting** window, a
  **Google Meet** call in any browser (code `xxx-yyyy-zzz` / `meet.google.com` / `Meet - ` prefix),
  **Zoom web**, **Teams**/**Webex** meeting windows, FaceTime. Returns `{source,key,app}`; the friendly
  `source` (e.g. "Chrome", "Zoom") shows in the pill. `_BROWSERS`/provider matchers are easily extended.
  Conservative on purpose (an idle Zoom / a doc titled "Meet…" must not trigger) — pinned by
  `meeting_detect_fixtures.py`.
- **False-positive hardening (2026-08-19).** Because `detect()` tests EVERY on-screen title, a loose
  pattern fires on whatever is open. Three fixes: (a) `_MEET_CODE` is now boundary-anchored
  (`(?<![a-z0-9-])…(?![a-z0-9-])`) — unanchored, it matched any 3-4-3 letter run *inside* a longer
  hyphenated slug, and a Chrome tab containing "…axo-data-and…" was reported as a live Meet call
  (`gmeet:axo-data-and`, 7 prompts in one evening); (b) a code alone is no longer sufficient — it needs
  `\bmeet\b` in the title too, since three short hyphenated words are ordinary in article titles;
  (c) Webex dropped its `or "webex" in low` clause, which made every Webex window a "call" even though the
  owner check already proves the app. A `_MEET_SITE` signal was **added** (`… - Google Meet` as the
  trailing site name, end-anchored so "How to use Google Meet - YouTube" is excluded) — that catches a
  *named* call, which the old rules missed entirely.
- **Prompt** (`app/meeting_prompt.py`): a non-activating NSPanel + WKWebView pill (same recipe as
  `autolearn_widget.py` — never steals focus from the call), near-black Flume design with a sage accent.
  Buttons post `md_take`/`md_dismiss` through the shared `_Bridge`.
- **Wiring** (`main.py`): `_detect_meeting_tick` asks **once per call** (`_md_handled` keyed by call),
  skips when a meeting is already recording, and resets after ~2 empty polls so the *next* call re-prompts
  (also hides a stale pill). A **dismissal is durable for the session** (`_md_dismissed`, 2026-08-19):
  that reset used to erase the refusal too, so a detection that merely flickered off-screen for 10 s
  came back and asked again — same key, seven times. `_md_dismissed` is deliberately NOT cleared by the
  empty-poll reset (anti-nag, like `autolearn_declined`). `_meeting_detect_result(True)` → `meetings.start(use_mic,use_system,lang)` +
  open the live window; if capture isn't ready (permissions) it falls back to `_toggle_meeting` (the
  permission/pre-meeting flow). Menubar **"Auto-detect meetings"** checkbox toggles `meeting_autodetect`
  (config, default **on**).

## Mobile audit pass (Jul 2026): onboarding, buttons, per-device sync, keyboard

- **Onboarding** trimmed to 2 slides (`OnboardingScreen.tsx`) — the "Connect a computer /
  pair a device" slide was removed (pairing happens post-sign-in, not in onboarding).
- **Dead buttons fixed**: Home feature cards → Devices / Notes (`useNavigation`), Home +
  Notes "See all" wired/removed, Home notifications bell removed; History search field +
  overflow menu (Copy/Delete via `remove`) wired, misleading Edit==Copy button dropped;
  Pairing "Enter code instead" now a real code field (reuses `pairing.extractToken`).
- **Per-device sync** (replaces the single global yes/no popup): new cloud column
  `devices.sync_enabled`; shared helper `lib/deviceSync.ts` (`fetchAccountDevices`,
  `setDeviceSync`, `isDeviceOnline`); a root-mounted `DevicesSyncHost` sheet
  (`showDevicesSheet()`, mounted beside `ConfirmHost`) shown from `useAuth.afterSignIn`
  when other devices exist; each device has its own Switch; toggling THIS device mirrors to
  local `verbal_sync_enabled` (drives `lib/useSync`); on sign-in this device reconciles its
  flag from its own cloud row. Ongoing management via the rebuilt `DevicesScreen` (native
  Switches — avoids the JS-modal-in-modal touch issue).
- **Keyboard fast-typing (dropped letters) fixed** on BOTH platforms
  (`plugins/keyboard/FlumeInputMethodService.kt`, `targets/keyboard/KeyboardViewController.swift`):
  (1) config cached by file-mtime (was disk-read+JSON-parse per keystroke); (2) suggestions
  DEBOUNCED ~70ms off the commit path (was a 25k-word scan + IPC per keystroke); (3) shift/
  auto-cap now update key labels IN PLACE (`refreshLetterCaps`) instead of a full
  `showKeyboard()` rebuild — the rebuild was the primary cause, racing the next rapid tap
  (esp. the letter after a space); (4) on-device learning writes moved off the main thread.
  Verified via the EAS Android APK (native can't hot-reload).

## Multilingual transcription (Jul 2026)

Whisper was hard-pinned to `language="en"` in four places — the model itself is multilingual (~99
languages). Now: `config['spoken_language']` (ISO-639-1 or `auto`; default `en` preserves old
behavior) applies to dictation AND meetings; a per-meeting **Language** picker in the pre-meeting
modal overrides it (`start_meeting(..., language)` → `MeetingSession.language` → every chunk).
Resolution + routing live in `transcriber.resolve_language` / `transcribe_with_status(language=…)`:
`auto` → omit the param (Whisper detects); non-English pins route Groq to full **whisper-large-v3**
(turbo is weaker on low-resource languages); the English dictionary-glossary bias prompt is attached
ONLY when the language is English (a Whisper prompt also hints the language). The dictation formatter
carries a "same language, never translate" rule. Options list: `shared_dashboard.SPOKEN_LANGUAGES`.
Mobile: `lib/groq.ts` honors `flume_spoken_language` (default `en`; no picker UI yet). Known limit:
code-switched meetings resolve per 8–22s chunk in auto mode.

**Meeting notes/summary output language is a separate setting from transcription language**
(`config['meetings_notes_language']`, Settings → Meetings): default `"en"` always writes the
summary/decisions/action items/notes in English, regardless of what language (or script) the
meeting was recorded in — e.g. a meeting transcribed in Roman-script Urdu still gets English notes.
Set it to `"auto"` to fall back to the old behavior: per-meeting `MeetingSession.language` pin >
global `spoken_language` pin > script detection over the transcript > English. Resolution lives in
`meetings._summary_output_language`, used by both `generate_meeting_summary` and
`generate_meeting_notes`.

## Custom keyboard — core features (mobile, iOS + Android)

Verbal ships a real system-level keyboard on both platforms (iOS extension
`targets/keyboard/KeyboardViewController.swift`, Android IME `plugins/keyboard/
FlumeInputMethodService.kt`) — a from-scratch QWERTY/numbers/symbols keyboard, not a wrapper around the
system one. The "Flume bar" above the keys has icon buttons that toggle in-keyboard overlays (tap-to-insert
rows), a pattern every subsequent keyboard feature (clipboard history, Transform) has reused rather than
inventing new UI:

- **Snippets** — spoken/typed trigger phrases expand to full text, browsable and tap-to-insert directly
  from the keyboard (not just via dictation).
- **Canvas** — the cross-device shared-clipboard feature, reachable from the keyboard too.
- **History** — recent dictations, tap to re-insert.
- **Vocabulary** — the user's custom dictionary words, with phonetics shown if present.
- **On-device word suggestions**: prefix completions AND next-word prediction from a personal
  word/bigram model (`learnWord`/`learnBigram`, bundled `flume_words.txt`/`flume_bigrams.txt` seed data),
  persisted per-keyboard (see `05-conventions.md` Hard Rule #16 for the exact storage/caps). Suggestions
  can also surface an emoji for an exact word match.
- **Emoji picker**: a full bundled library (~1900 emoji, 9 groups + Recents) with keyword search
  (`flume_emoji_kw.txt`) mapping typed words to relevant emoji.
- **Dictation via mic**: records and transcribes through the same `groq-proxy` pipeline as the in-app
  recorder. **Both** keyboards do the full sequence natively in-extension/IME (vocab-bias prompt, last
  ≤80 terms/≤600 chars → transcribe → **prompt-echo scrub** → replacements → single-pass snippet
  expansion; an echo-only transcript shows "No speech detected") — iOS gained the missing
  three stages in IDI-161 (there was never a real main-app handoff), Android's snippet cascade was fixed
  to the single-pass contract in IDI-162. Both send `x-flume-device`, read `spokenLanguage` from the
  shared config ('auto' → omit), surface every failure visibly (mic/full-access/HTTP/timeout — iOS's
  `flashMic` was an empty stub), and carry an async **field-identity guard** (IDI-163): a transcript is
  dropped with a message unless the input session still matches record-start, a FRESH secure-field check
  passes at insert time, and the result is <90s old — a dictation can never land in a password field or
  a different field than it was spoken into.

All of the above predates and is extended by the clipboard-history and Transform features below, which
reuse the identical bar-icon → overlay → tap-to-insert (or bar-icon → live-action) shape. Deep
implementation gotchas (fonts, sounds, typing feel, theming, the app→keyboard config bridge) live in
`05-conventions.md` Hard Rule #16 — this section is deliberately the "what," not the "how."

## Keyboard clipboard history (mobile, Jul 2026)

A 5th Flume-bar icon (clipboard glyph) on both custom keyboards opens a clipboard-history
overlay (same bar-icon → overlay → tap-to-insert pattern as dictation history), plus an ephemeral
"quick paste" chip near the bar that appears once per new copy with an 8-char preview — tap either
to insert the full text.

**Entirely self-contained in each keyboard target — not part of the `flume_kbd_config.json`
app→keyboard bridge.** Neither the main app nor JS ever sees clipboard content; only the extension
observes and persists it, to a NEW file `flume_kbd_clipboard.json` (iOS: same App Group container as
the config bridge; Android: the IME's own `filesDir`), capped at 15 entries (mirrors the existing
dictation-history wire cap). One preference IS threaded through the existing bridge:
`clipboardHistoryEnabled` (`lib/storage.ts::getClipboardHistoryEnabled`/`setClipboardHistoryEnabled`,
default ON, Settings → Keyboard) — gates the feature without carrying any clipboard content itself.

- **iOS** (`KeyboardViewController.swift`): clipboard access needs the keyboard's "Full Access"
  permission. The quick-paste chip simply doesn't render without it (ambient, not naggy); the
  clipboard overlay always shows the icon, but tapping it without Full Access shows an explicit
  "tap to open Settings" row (`extensionContext?.open(...)`) instead of the list — informative,
  never silently broken. Detection happens in `viewWillAppear` (the only reliable moment an
  extension can notice a clipboard change — extensions don't run in the background) by comparing
  `UIPasteboard.general.changeCount` against a persisted value.
- **Android** (`FlumeInputMethodService.kt`): no permission gate needed. A
  `ClipboardManager.OnPrimaryClipChangedListener` registered in `onCreate()` can catch a clipboard
  change made in another app before the keyboard reopens (Android IMEs stay resident more readily
  than iOS extensions); `onStartInputView` re-checks once as a fallback.
- **Privacy — respected on both platforms, not optional:** content flagged by the password-manager
  "don't capture this" convention is skipped for both the chip and history — Android's
  `ClipDescription.EXTRA_IS_SENSITIVE` (API 33+) and iOS's de facto `org.nspasteboard.ConcealedType`
  UTI (set by 1Password/Bitwarden etc). Clipboard content is never synced to Supabase or any cloud
  store — device-local only, always.

## Transform — voice/prompt-driven text reshaping (TRANSFORM_SWARM.md, Jul 2026)

**What:** reshape text with an instruction instead of just dictating it. Master switch
`transform_enabled` (default OFF) + per-mode flags, in Settings → Transform.

Both modes share `transform._chat`, which is resilient like `process_text`: primary = Groq
`openai/gpt-oss-120b` (was llama-3.3-70b, retired by Groq 2026-08-18) via the shared proxy; on any failure (including Groq's **daily-token 429**)
it retries the SAME `groq-proxy` against **Ollama Cloud** (`gpt-oss:120b`, `provider="ollama"`, model
const `transform.OLLAMA_FALLBACK_MODEL`) — a separate quota with a server-held key (the same path
meeting-notes uses, reversed order). So Transform keeps working when the shared Groq key is exhausted.
Fully fail-closed — both down → `None` → "Couldn't transform, try again" (Mode B) / untouched text
(Mode A).

- **Mode A — inline (Capture):** end a dictation with *“…so Flume, make this formal”*. A free
  tail-gate (`transform.detect_trailing_instruction` — trigger homophones `transform_trigger_words`,
  ≥3-word body, instruction must START with an editing verb from `INSTRUCTION_VERBS`) splits body from
  instruction; `apply_instruction` (TRANSFORM_SYSTEM_PROMPT via groq-proxy) rewrites the body; the
  overlay shows *“✦ Transformed · <instruction>”* so a wrong split is catchable. ANY failure falls
  back to the untouched `process_text` path (Rule #1). Hook lives in `main`'s transcribe worker,
  BEFORE `process_text`.
- **Mode B — selection (Agentic):** select text anywhere → **⌘⇧T** → `_on_transform_hotkey` calls
  `injector.save_focused_app()` **first** (captures the target app's pid *while it's still frontmost*),
  then `transform.capture_selection` (save clipboard → synth ⌘C → read → ALWAYS restore) →
  `transform_widget.TransformWidget` cream pill (non-activating, bottom-center): **Improvise**
  (IMPROVISE_SYSTEM_PROMPT clarity pass), typed instruction, or SPOKEN instruction (reuses
  Recorder+transcriber; blocked while a meeting holds the mic). While recording the **mic pulses (accent
  ring) + a live waveform** shows (`.mic.on` micPulse + `#micWave`, same idiom as the overlay pill) so
  it's unmistakable the mic is live. A spoken instruction is **transcribed then shown in the editable
  field for review/edit — it does NOT auto-transform**; the user presses Go / Enter to run the
  (possibly edited) instruction (`heard` state populates `#pin` and `makeKeyWindow`s the panel so it's
  editable at once — nonactivating, so the target selection survives). Result is a **preview** — Replace
  pastes over the still-highlighted selection via `injector.inject_text`, then a 6-s **Undo** (target-app
  ⌘Z). **The `save_focused_app()` call is load-bearing:** Mode B never enters the dictation core, so
  without it `injector._previous_app_pid` was stale/None and `inject_text`→`restore_focused_app()`
  re-activated the wrong app (or nothing) — Replace silently pasted nowhere. Cancel/no-selection/too-long
  (>12k chars) are all no-ops.
- **Mobile — Mode B on the keyboard (Jul 2026):** a dedicated Transform button (iOS SF Symbol
  `wand.and.stars`, Android Ionicons `sparkles-outline`) on both custom keyboards
  (`targets/keyboard/KeyboardViewController.swift`, `plugins/keyboard/FlumeInputMethodService.kt`),
  gated by `transformEnabled` (default OFF, bridged like `clipboardHistoryEnabled` — Settings →
  Keyboard). No Accessibility-style universal selection API exists on mobile, so selection is read
  through the focused field's own proxy instead: iOS `textDocumentProxy.selectedText`, Android
  `currentInputConnection.getSelectedText(0)` (the same call already used for the existing
  delete-over-selection backspace logic). Empty/unreadable selection shows an inline "Select some
  text first" message rather than silently doing nothing. **Typing the instruction reuses the
  physical keyboard itself**: both files already funnel every keystroke through one centralized
  `commit()`/`onSpace()`/`onBackspace()` — a compose-mode flag redirects these to a local instruction
  buffer instead of the host app, so the letters layer stays fully usable while the original
  selection is left untouched (critical: nothing touches the host proxy until the final Replace,
  which is what keeps the selection alive through the whole flow). The existing mic button is
  repurposed (same button, mode-dependent meaning) to speak the instruction via the already-built
  recording→transcribe pipeline; a horizontally-scrollable preset row (Improvise + Formal/Casual/
  Shorten/Fix grammar) covers the one-tap case. Same verbatim `TRANSFORM_SYSTEM_PROMPT`/
  `IMPROVISE_SYSTEM_PROMPT` and de-wrapping logic as desktop, called directly from the extension via
  a new JSON chat-completions call (`chatViaProxy`/`proxyChat`) — a sibling of the multipart
  transcription call each file already makes, same `groq-proxy` endpoint (it already routes JSON→chat
  vs multipart→transcription), no backend changes needed. Selections over 8000 chars are **refused with a
  visible message** on both keyboards (IDI-164 — previously silently truncated, which made Replace destroy
  the untransformed tail; desktop still caps at 12000 with its own handling). **Replace re-validates the
  selection** (IDI-164): the host's current selection is re-read and must still equal the captured
  original, else "Selection changed" and no insert — a collapsed selection can no longer end up with
  original+rewrite both in the document. A failed transform now fully rebuilds the keyboard UI on both
  platforms (it used to strand a spinner), and iOS carries a `transformSeq` request token + task
  cancellation like Android. **No OS-level undo exists on mobile** (no "send ⌘Z to the host app"
  equivalent) — Undo is a soft implementation: delete exactly as many UTF-16 code units as the rewrite
  inserted, then re-insert the original captured text; shown as a ~6s bar chip (shared with the clipboard
  quick-paste chip — whichever ephemeral affordance is most recent wins; the two never show at once).
  Since IDI-164 `pendingUndo` is cleared on any input-session/field change and on host-mutating typing,
  so Undo can never delete characters in a different field.
  Mode A (trailing "…so Flume, …" trigger) is not implemented on mobile.
- **Fixtures:** `whisperflow/transform_fixtures.py` (16 gate cases + output unwrapping, offline).

### Dashboard first paint + Windows launch speed (2026-08-28)
- `flume_dashboard_html.py::load()` renders from `get_state` (local config only) **before** any network:
  it used to `await fetch_notes` first, so a slow/dropped connection left the window dark until the
  Supabase call timed out ("very slow start, feels like it crashed" — Windows). Notes/canvas/team load
  afterwards and re-render on arrival. Never put a network `await` ahead of `renderActive()`.
- Windows `webview.start(private_mode=False, storage_path=~/.verbal/webview)`: pywebview's default made
  a fresh Chromium profile under `%TEMP%` per launch (slow cold start, `tmpXXXX\EBWebView` litter).
  Sign-in is PKCE in the system browser, so nothing needs a private profile.
- Startup timing is logged at INFO: `webview loop starting`, `dashboard: window created in …`,
  `dashboard: get_state (… after launch)` — read `app.log` before guessing where a slow launch goes.
- Device wording in the shared page is platform-aware: `THIS_DEVICE` ("This PC"/"This Mac") and
  `DEVICE_NOUN` are JS constants injected next to `IS_WINDOWS`; the sign-in headline and the wizard's
  "menu bar"/"system tray" follow `_is_win_early`/`IS_WINDOWS`. Onboarding no longer says "This Mac" on
  Windows regardless of who signs in.

### Team invite deep links (2026-08-29)
- The invite e-mail (`supabase/functions/invite-member`) links to the **`invite` Edge Function**
  (`/functions/v1/invite?t=<token>`, public, `verify_jwt=false`) — a stable address that only
  **redirects**: to the static landing page `INVITE_LANDING_URL` (desktop) when that env is set, else to
  `idiaz.io/flume/download.html?t=<token>`. **The `*.supabase.co` functions gateway serves every response
  as `text/plain` + `nosniff` (verified 2026-08-29 with text/html AND application/xhtml+xml), so the
  landing page cannot be an Edge Function** — it is the static file `site/flume/invite.html` (source of
  truth in this repo; a copy sits in `/Users/mshabbar/IDIAZ/flume-site/` for upload to
  `https://idiaz.io/flume/invite.html`). That page tries **`flume://invite?t=<token>`**; if the document
  is still visible ~1.6 s later it redirects to the download page, token preserved; phones go straight
  there. **Live since 2026-08-29**: the function's default `INVITE_LANDING_URL` is that page. Publishing the
  Flume site = `~/.agents/skills/here-now/scripts/publish.sh /Users/mshabbar/IDIAZ/flume-site --slug
  hollow-tulip-8v5s` (idiaz.io/flume is that here.now publish; the `idiaz-io/websites` repo pipeline
  covers only the root site).
- **macOS handles the scheme** (`CFBundleURLTypes` in `whisperflow.spec`; `main.py::_install_url_handler`
  registers a `kAEGetURL` Apple Event handler → `app/deep_link.py::handle`). Launch Services routes the
  URL to the running app or launches it; the handler is installed in `__init__` so a cold-start URL is
  not lost. **Windows: not wired yet** (needs the `[Registry]` scheme in `verbal-setup.iss` + argv /
  second-launch hand-off; `deep_link.py` is shared).
- In the app: the token is parked in config (`pending_invite_token`), the dashboard opens on **Team** and
  gets an `inviteLink` event; the page calls `DashboardApi.get_invite_link` (preview via
  `org_invite_preview`) and shows the **"Join <team>"** modal; Join reuses `claimTeamInvite(token)`
  (IDI-223 confirm round-trip included) and `clear_invite_link` drops the parked token. Signed-out users
  hit the sign-in wall first — `checkInviteLink()` re-runs when `signed_in` flips true. Invalid/expired
  tokens are cleared on preview; network failures keep the token for a later retry.
- Fixtures: `whisperflow/deep_link_fixtures.py` (parser + handler); the Apple Event path was exercised
  with a real `NSAppleEventDescriptor` (class/id `GURL`, keyDirectObject `----`).
