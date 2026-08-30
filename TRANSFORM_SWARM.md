# TRANSFORM_SWARM.md — Voice/prompt-driven text transformation

> Feature spec in the `*_SWARM.md` convention (mission · algorithm · failure table · swarm).
> Reference code by file/function, not pasted code. When built, update `context/` per the maintenance
> contract (see the "Docs to update" section at the bottom).

---

## Mission

Let the user reshape text with an instruction instead of just dictating it. Two modes, one shared engine:

- **Mode A — Inline transform (Capture tier).** At the end of a normal dictation, the user adds an
  instruction addressed to Flume — *"…so Flume, make this sound more formal."* Flume splits the dictated
  body from the instruction, applies the instruction, and pastes the transformed result. Nothing is
  overwritten (there was no text there yet), so this stays in the same risk class as ordinary dictation.

- **Mode B — Selection transform (Agentic tier).** The user highlights existing text somewhere (an email,
  a doc), presses a dedicated hotkey, and gets a pill: **Improvise** (a one-tap clarity pass) or a spoken/typed
  prompt (*"make the tone professional"*). Flume rewrites the selection and **previews** it before replacing.
  This one *reads* another app's content and *writes* over it — so it needs the confirmation + undo the PRD
  flags as a prerequisite for agentic features.

Both modes call the same instruction-following LLM step. **Build Mode A first** — it's low-risk, reuses
`process_text`, and lets us tune the instruction prompt on the safe path before Mode B depends on it.

**Non-goals (v1):** no always-on selection watching; no cross-app editing on mobile (needs the keyboard
extension — see `FLUME_KEYBOARD_SWARM.md`); no multi-turn conversation with the text.

---

## The core tension (read this first)

The existing cleanup prompt in `ai_cleanup.py` (`SYSTEM_PROMPT`, 17 rules) explicitly says *"you are a TEXT
FORMATTER, not an assistant"* — it must **not** follow instructions embedded in speech, or dictating the word
"formal" would change your formatting. Transform needs the **opposite** behavior. So Transform is a **new
prompt/mode**, never an edit to `SYSTEM_PROMPT`. The normal dictation path is untouched; Transform only
engages when its gate fires (Mode A) or its hotkey is pressed (Mode B).

---

## Algorithm

### New module: `transform.py`

Mirrors the `autolearn.py` / `filetags.py` pattern — a pure, testable core plus thin orchestration. Carries a
**HARD GUARANTEE** docstring: *never breaks the record→transcribe→inject path; fails closed to normal
`process_text`.*

Core functions:

- `detect_trailing_instruction(raw_transcript) -> (body, instruction) | None`
  Cheap string/regex gate. Looks **only at the tail** for `… <trigger>[,] <instruction>` where `<trigger>`
  is in a tunable `TRIGGER_WORDS` set. Returns `None` for the overwhelming majority of dictations (no LLM
  cost). Because "Flume" mis-transcribes, `TRIGGER_WORDS` starts as `{flume, flumes, "flu me", plume, bloom}`
  and is **tuned from real logs** — keep it tight to avoid stealing real content. Requires a non-empty body
  before the trigger (so "Flume make a note" alone doesn't misfire).

- `apply_instruction(text, instruction) -> str`
  LLM call (Groq `llama-3.3-70b-versatile`, Gemini fallback with key rotation — same client path as
  `cleanup_with_groq`). Uses **`TRANSFORM_SYSTEM_PROMPT`** (new): *"You transform the user's text per their
  instruction. Return ONLY the transformed text — no preamble, no explanation. Do not add facts. If the
  instruction is unclear, clean up the text normally."* Returns the rewrite as a plain string.

- `improvise(text) -> str`
  Mode B's no-prompt default. Uses **`IMPROVISE_SYSTEM_PROMPT`** (new): a tuned *"make this clearer and
  tighter without changing meaning or adding content"* pass. This needs the same craft as the 17-rule
  formatter — a vague prompt gives inconsistent output.

> **Why a cheap gate + LLM split, not pure string-splitting:** the string gate is free and keeps normal
> dictations on the normal path. But the *boundary* between body and instruction is messy ("send this to
> Flume and make it formal" — is "send this to Flume" content?). Once the gate fires, we hand the **whole
> tail** to the LLM and let `TRANSFORM_SYSTEM_PROMPT` do the clean split. Cheap to decide, smart to execute.

### Mode A wiring (desktop)

Hook sits **between** transcription and cleanup, in `main._transcribe_*` (before `ai_cleanup.process_text`):

```
transcribe → transform.detect_trailing_instruction(raw)
  ├─ None  → ai_cleanup.process_text(raw)            [unchanged normal path]
  └─ (body, instr) → transform.apply_instruction(body, instr)  → inject
```

**Show the split.** Per the auto-learn spirit, surface what was interpreted as the instruction so a wrong
guess is catchable — set the overlay "Done" state to a short note (*"Transformed · made formal"*) via
`window.VerbalOverlay`. Mode A doesn't overwrite anything, but a bad split still corrupts the paste, so the
result stays retryable from History like any dictation.

**Fail closed:** any exception in detect/apply → fall back to `process_text(raw)`. The user gets their
dictation (instruction words included) rather than nothing.

### Mode B wiring (desktop)

Separate hotkey path — **never** touches the dictation core.

```
hotkey (new, distinct from dictation key)
  → capture selection            [AX or clipboard route — see below]
  → TransformWidget pill: Improvise | speak/type a prompt
  → transform.improvise(sel) OR transform.apply_instruction(sel, instr)
  → PREVIEW in pill: Replace | Cancel        ← the safeguard
  → on Replace: injector.inject_text(rewrite) over the still-selected text
  → restore clipboard; keep original string in memory so "undo" re-pastes it
```

**Capturing the selection — two routes, same tradeoff as file-tagging/auto-learn:**

| Route | How | Works in | Cost |
|---|---|---|---|
| **AX** | read `AXSelectedText` on the focused element | native Cocoa fields | dead in Electron/terminal/secure (same as `EditWatcher`) |
| **Clipboard** ✅ default | save clipboard → synth Cmd+C → read → restore | ~everywhere incl. browsers/Electron | touches clipboard (save/restore, like `injector` does for focus) |

Default to **clipboard** — the headline use case is an email in a browser, where AX reads are flaky. Mirror
`injector.py`'s existing focus save/restore for the clipboard. If nothing is captured, silent no-op.

**Speaking the prompt is on-brand.** Since Flume is voice-first, after the pill opens the user can *dictate*
the instruction (reuse `Recorder` + `transcribe_with_status`) rather than type it. The transcript becomes
`instruction`. Typed input stays available as a fallback.

**Replacement:** the selection is highlighted, so a paste replaces it — reuse `injector.inject_text`. No new
injection primitive.

### UI — reuse the auto-learn pill

`transform_widget.py::TransformWidget` clones `autolearn_widget.py::AutoLearnWidget`: a **non-activating cream
pill** (`NSNonactivatingPanelMask` @ `NSScreenSaverWindowLevel`, bottom-center, never steals focus), using the
`cream` card language (`#EADFCE`, dark ink, near-black action button) per the established design preference —
not orange/black. States: **prompt** (Improvise / mic / text field) → **preview** (rewrite + Replace / Cancel).
Preview + Replace/Cancel **is** the agentic confirmation-and-undo layer.

### Config keys (via `config.py::save_config`, atomic + locked)

- `transform_enabled` (master, default **off** — like `autolearn_enabled`)
- `transform_inline_enabled` (Mode A) · `transform_selection_enabled` (Mode B)
- `transform_trigger_words` (Mode A trigger set, tunable without a rebuild)
- `transform_hotkey` (Mode B key; must not collide with the dictation key or ESC-cancel)

Add all to `DEFAULT_CONFIG` (avoid the `sync_enabled` gap noted in `04-data-model.md`).

### Mobile

- **Mode A** ports cleanly: same gate + a `lib/groq.ts` transform variant (mirrors `formatText`). Lower
  priority than desktop.
- **Mode B is desktop-only for now.** iOS/Android have no system-wide selection/injection (the reason the
  keyboard extension exists — memory: *"third-party apps cannot inject text into arbitrary apps"*). On mobile,
  selection-transform only works inside Flume's own screens, or later via `FLUME_KEYBOARD_SWARM.md`.

---

## Failure table

Every row **fails closed** — a no-op or a fall-through to the normal path, never a broken dictation or a
silent overwrite.

| Situation | Risk | Behavior |
|---|---|---|
| Gate misfires — dictated content read as an instruction | corrupted paste | LLM split is the real gate; result shown in overlay + retryable from History; tune `TRIGGER_WORDS` from logs |
| Gate misses a real instruction | instruction pasted as literal text | user retries or re-dictates; acceptable — bias toward missing over stealing content |
| `apply_instruction` / `improvise` LLM call fails | no output | Mode A → fall back to `process_text(raw)`; Mode B → keep pill open, show retry, never replace |
| Mode B: no selection captured | nothing to transform | silent no-op, pill never opens |
| Mode B: AX read blocked (Electron/secure/terminal) | can't read | fall through to clipboard route; if that fails too, no-op |
| Clipboard route can't restore clipboard | user loses clipboard | wrap save/restore in try/finally; restore is best-effort but always attempted |
| Selection too long for LLM context | truncated/garbled rewrite | cap selection length; over cap → pill shows "selection too long", no call |
| User cancels at preview | — | discard rewrite, restore clipboard, original untouched |
| Replace lands but user wants it back | lost original | original string held in memory; offer one-step undo (re-paste) right after Replace |
| Transform prompt drifts into "assistant" chatter (adds commentary) | junk in output | `TRANSFORM_SYSTEM_PROMPT` hard-rules "return ONLY the text"; add to prompt-regression fixtures |

---

## Hard rules this must honor (`05-conventions.md`)

1. **Never break the dictation path.** Mode A wraps in try/except and falls back to `process_text`; Mode B is
   a separate hotkey that never enters record→transcribe→inject.
2. **Main-thread discipline.** Pill UI + injection on the main thread via `main._on_main`; LLM/transcription
   on daemon threads.
3. **Config atomic + locked.** New keys only through `save_config`.
4. **Non-activating panel.** The pill must never steal key focus from the app being edited.
5. **AX/Electron (if AX route enabled).** Set `AXManualAccessibility` + `AXEnhancedUserInterface`; exclude
   terminals and secure fields — same as `filetags.py`/`autolearn.py`.
6. **Verify generated web UI.** If the pill's HTML/JS uses the bridge, `node --check` the rendered `<script>`.
7. **Groq 896-char cap does NOT apply here.** That cap is the *Whisper bias prompt* in `transcriber.py`.
   Transform sends text as LLM **chat content**, a different limit — but still cap selection length for
   latency/cost.

---

## Swarm (build order)

### Phase 1 — Mode A (Inline transform) · Capture · ship first
- **P1.1** `transform.py`: `detect_trailing_instruction`, `apply_instruction`, `TRANSFORM_SYSTEM_PROMPT`;
  pure-core unit tests (`transform_fixtures.py`) covering split boundaries, trigger homophones, no-body case.
- **P1.2** Wire into `main._transcribe_*` before `process_text`; fail-closed fallback.
- **P1.3** Overlay "Done" note showing the applied instruction (`window.VerbalOverlay`).
- **P1.4** Config: `transform_enabled`, `transform_inline_enabled`, `transform_trigger_words` + Settings toggle.
- **P1.5** Tune `TRIGGER_WORDS` + prompt against real dictation logs; add prompt-regression fixtures.

### Phase 2 — Mode B (Selection transform) · Agentic
- **P2.1** Selection capture: clipboard route (save/restore) + optional AX route; `transform_hotkey`.
- **P2.2** `transform_widget.py::TransformWidget` (clone auto-learn pill): prompt state + preview state.
- **P2.3** Spoken-prompt path (reuse `Recorder`/`transcribe_with_status`); typed fallback.
- **P2.4** `improvise` + `IMPROVISE_SYSTEM_PROMPT`; wire Improvise button.
- **P2.5** Replace via `injector.inject_text` over selection; clipboard restore; one-step undo.
- **P2.6** Config: `transform_selection_enabled`, `transform_hotkey` + toggles; hotkey-collision guard.

### Phase 3 — Mobile Mode A (optional)
- **P3.1** `lib/transform.ts` mirror (gate + Groq transform variant); wire into `useRecorder` retry/finalize.

---

## Docs to update when built (maintenance contract)

- `context/01-product.md` — add **Transform (inline / selection)** rows to the feature matrix (Mac ✅,
  Windows TBD, iOS: inline only).
- `context/03-features.md` — new **Transform** section (what · desktop · mobile · backend · status/limits).
- `context/05-conventions.md` — record the *"Transform is a separate prompt, never edit `SYSTEM_PROMPT`"* rule
  and the clipboard-save/restore gotcha; list `transform_widget.py` alongside the other non-activating panels.
- `context/04-data-model.md` — none (config-only; note the new keys aren't Supabase columns).
- Repo-root design docs — none beyond reusing existing `cream` tokens.
