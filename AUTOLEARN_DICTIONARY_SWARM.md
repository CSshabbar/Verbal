# Auto-Learn Dictionary — Context / Harness / Loop Engineering Spec

> Single source of truth for building **auto-learn from post-transcription
> corrections** in Verbal (desktop). Read top-to-bottom before spawning any agent.
> Everything an agent needs to act correctly (context), how the agents are wired
> (project-manager swarm), and the iterate-until-proven loop (loop engineering)
> lives here. Mirrors the structure of `FILE_TAGGING_SWARM.md`.

---

## 0. MISSION (the loop's success criterion)

**After Verbal transcribes speech and inserts it, if the user fixes the spelling
of a word, Verbal recognizes the correction, offers to add it to the dictionary
(a small confirmation widget), and — once confirmed — never mis-transcribes that
word again.**

The single hardest requirement, stated by the user:

> "It should be intelligent enough to detect that I'm **correcting** the word,
> not **deleting** the word."

So the feature must **distinguish a genuine correction from every other kind of
edit** (deletion, insertion, rephrase, punctuation/case, OS autocorrect) and only
act on real corrections.

Concretely, DONE when all of the following hold on a real machine:

1. Dictate "meeting with **Shabar**" into any normal text field; change `Shabar`→`Shabbar`.
   → a widget appears: **"Add Shabar → Shabbar to your dictionary?"** → confirm →
   the rule persists and future dictations of that name come out `Shabbar`.
2. Dictate "the the report" and **delete** the extra "the". → **no widget** (deletion, not correction).
3. Dictate "send report" and **insert** "the" → "send the report". → **no widget** (insertion).
4. Rephrase a whole sentence after dictation. → **no widget** (too many changes).
5. Fix only capitalization ("idiaz"→"iDiaz") → offered (proper-noun/caps) but never
   for common words ("teh"→"the" is a typo of a common word → **no widget**).
6. Works without crashing, stalling, or ever corrupting the clipboard/recording path.
7. Never reads secure/password fields; degrades to no-op when it can't read the field.
8. Reuses the shipped custom-dictionary machinery and the config/sync plumbing.
9. Behind a user **toggle** (default decided at ship time; OFF until proven safe).
10. A learned rule is auditable and removable; a wrong learn is one action to undo.

If any of 1–10 fails, the loop is **not** complete.

---

## 1. CONTEXT (ground truth — do not re-derive)

### 1a. What the feature is
Verbal already inserts transcribed text into whatever app the user was typing in.
This feature adds a **read-back + diff + learn** step: after insertion, watch the
target field; when the user edits it, diff the edit against what we inserted,
classify the edit, and if it is a **confident single-word correction**, offer to
persist it as a dictionary **replacement rule** so the model's mistake is fixed
forever.

### 1b. How Wispr Flow does it (the bar; from their docs)
- Ships as **"Auto-add to Dictionary" / "Smart Dictionary (Beta)"** (Settings → Personalization).
- **Watches the external text field** it pasted into and detects edits to transcribed words.
- **Learns silently** (no prompt), flags auto-learned words with a **✨ sparkle** in
  an audit list the user can prune later.
- **Proper nouns / uncommon words only** — common words ("sprint", "deploy") are
  filtered out. *This single decision is the biggest false-positive reducer.*
- Keeps three mechanisms separate: **add-a-word** (bias), **replacement rule**
  (deterministic swap), **auto-learn** (passive capture). Syncs across devices.

**Our deviation (per the user's explicit request):** we want an **offer/confirm
widget**, not fully silent learning. Reconcile the two: **prompt only in a narrow
high-confidence band, non-intrusively, with per-word "never ask" memory and batching**,
so it never becomes prompt-spam. (A silent-learn + ✨-audit mode is a valid future
default; build the confirm path first.)

### 1c. Existing code to REUSE (do not reinvent) — verified file:line
- `app/dictionary.py`
  - `add_replacement(config, frm, to, save_config_fn)` — **dictionary.py:78** — the
    persist point. Strips inputs; no-ops if empty or `frm.lower()==to.lower()`;
    **de-dupes by `from` (case-insensitive)**; appends; writes config + pushes remote.
  - `apply_replacements(text, config)` — **dictionary.py:53** — word-boundary,
    case-insensitive `re.sub` per rule. This is what makes a learned rule take effect.
  - `normalize/get` (**:24/:35**), `save` (**:69**), `fetch_remote` (**:93**, writes
    only on change), `_push_remote` (**:119**). Rule shape: `{"from": str, "to": str}`.
- `app/shared_dashboard.py`
  - `_learn_from_edit(self, old_text, new_text, cfg)` — **shared_dashboard.py:372** —
    the CURRENT heuristic to generalize: same word count, exactly one differing
    word, both alnum-stripped ≥2 chars & different → `add_replacement`. (Naive: no
    phonetics, no common-word filter, no insertion/deletion handling.)
  - `edit_text(self, old_text, new_text)` — **shared_dashboard.py:352** — the
    history-view edit path (JS `api("edit_text", ...)`); already calls `_learn_from_edit`.
- `app/main.py` — `_process_audio` at **main.py:562**
  - `result` = final injected text; `self._last_result_text = result` — **main.py:605**.
  - `add_to_history(... status="done")` — **main.py:606-608**; `rec_id`, `audio_path` in scope.
  - **Injection hook:** `inject_text(result, allow_mentions=...)` — **main.py:620**.
    *This is where the read-back watcher must be armed.* Target app available via
    `get_focused_app_name()` / `injector.get_focused_app_pid()` / `get_focused_app_bundle()`.
- `app/injector.py` — `save_focused_app()` (**:26**), `get_focused_app_pid()` (**:45**,
  "the dictation TARGET — use it for AX reads"), `get_focused_app_bundle()` (**:52**),
  `restore_focused_app()` (**:57**), `inject_text()` (**:149**).
- `app/filetags.py` — the AX toolkit to reuse:
  - `_ax_attr(element, attr)` — **filetags.py:147** — guarded `AXUIElementCopyAttributeValue`.
  - `AXUIElementCreateApplication(pid)` (**:218**), `AXUIElementCreateSystemWide()` +
    `AXFocusedUIElement` (**:346-350**), `AXManualAccessibility`/`AXEnhancedUserInterface`
    to wake Electron trees (**:230-232**), `focus_is_terminal()` (**:338**).
  - New attributes this feature needs (standard, read via the same `_ax_attr`):
    `AXValue`, `AXSelectedText`, `AXSelectedTextRange`, `AXRole`, `AXSubrole`.
- UI surfaces for the widget:
  - **rumps.alert** native prompt — pattern at **main.py:762** (`ok=`/`cancel=`, check
    `resp == 1`); must run on main thread via `self._on_main(...)`.
  - **WKWebView** overlay/popover with the `_Bridge` JS↔Python bridge
    (`flume_web_dashboard._Bridge`; overlay `app/overlay.py`, `show_briefly`) for a
    styled, non-modal toast/widget.
- `app/config.py` — `save_config` (**:87**) atomic (`tempfile.mkstemp` + `os.replace`)
  under `_config_lock` (**:12**); `add_to_history` (**:143**, caps 50),
  `update_history_entry(config, entry_id, **fields)` (**:164**), `_entry_text`/`_entry_app`
  tolerate str-or-dict entries.

### 1d. Hard constraints / guardrails (violating any = failure)
- **Never crash, stall, or corrupt the recording/injection path.** All AX reads and
  observers wrapped in try/except with hard timeouts; failure = feature silently no-ops.
- **Privacy first.** Never read `AXSecureTextField` (password) fields. Never persist
  raw field contents — store only the single `(old,new)` token pair for a confirmed rule.
- **Correction ≠ deletion ≠ rephrase.** This is the core intelligence (see §2); a
  deletion or multi-word change must NEVER be offered.
- **No prompt spam.** Per-word "already offered/declined" memory; batch multiple
  learns from one edit; non-modal; respect a global toggle + "never ask this word".
- **Reuse the dictionary + config/sync machinery**; don't fork prompt/replace logic.
- **Desktop only.** (Mobile can mirror later via the history-view path; out of scope here.)
- **Don't touch** overlay visuals beyond adding a toast, sounds, auth, canvas, notes,
  file-tagging, or the transcription result itself.
- Every code change must **compile (`py_compile`) + import + `node --check`** any
  generated dashboard JS before it counts as done.

---

## 2. THE INTELLIGENCE CORE — correction vs. everything else

We know `T` = the exact text we inserted. After the user edits, we read `E` = the
field's new content (bounded to the insertion region). Classify `T→E`:

### 2a. Edit taxonomy → action
| Edit type | Example (T → E) | Offer? | Why |
|---|---|---|---|
| Single-word mis-transcription fix | "with **Shabar**" → "Shabbar" | **YES** (phonetically close) | canonical learn case |
| Proper-noun / capitalization fix | "idiaz" → "iDiaz" | **YES** | high-value, low-risk |
| Delete an extra/hallucinated word | "the the report" → "the report" | **NO** | deletion, no target token |
| Insert a new word | "send report" → "send the report" | **NO** | insertion, no source→target |
| Rephrase clause/sentence | "can you do it" → "would you handle this" | **NO** | too many tokens changed |
| Punctuation / whitespace / case-only | "hello world" → "Hello, world." | **NO** (or low value) | formatting, not vocab |
| Common-word swap / homophone | "teh"→"the", "their"→"there" | **NO** | common word; grammar not vocab |
| OS autocorrect mangling | inserted "Kubectl" auto-changed to "Nutell" | **NO** | not user intent; would poison dict |

### 2b. The algorithm (deterministic pipeline)
1. **Token-level alignment** (NOT char-level). Tokenize `T` and `E`; align with
   **Needleman–Wunsch** (or token Levenshtein) → ordered ops: `match | substitute |
   insert | delete`, each with positions. Token-level is what cleanly separates
   "word replaced" (substitute) from "word added/removed" (insert/delete).
2. **Edit-shape gate.** Proceed only if ops contain **exactly one substitution**
   (optionally a ≤2-token contiguous run for names like "New York"), **zero inserts,
   zero deletes**, with matching neighbors. Also require **changed-token ratio ≤ 0.3**
   (≤ 0.5 for very short texts) — a real correction is a tiny fraction of the text;
   a rephrase is not. *Any insert/delete-dominated diff → reject (this is the
   "deleting, not correcting" case the user called out).*
3. **Phonetic-similarity gate** on the one `(old,new)` pair — is `new` a fix of what
   the model *heard*? Compute **Double Metaphone** for both; accept if primary (or
   secondary) codes match or code-Levenshtein ≤ 1. (Double Metaphone > Soundex/Metaphone
   for names/loanwords.)
4. **Orthographic gate (belt & suspenders).** Accept if **Levenshtein(old,new) ≤ 2**
   (words ≤6 chars) or ≤ ~30% of `max(len)`. Final accept = **(phonetic match) OR
   (low orthographic distance)**; reject if **both** are far apart (word swap/rephrase,
   e.g. "car"→"vehicle").
5. **Case/punct-only filter.** If `old`/`new` differ only by case or trailing
   punctuation → treat as a capitalization rule (low value; optionally learn), not a
   new vocab word.
6. **Common-word / proper-noun filter** (Wispr's key move). Reject if `new` is in a
   bundled top-~30–50k English frequency list. Prefer capitalized-mid-sentence,
   camelCase, ALL-CAPS acronyms, or words absent from the wordlist — the proper-noun signal.
7. **Anti-false-attribution guards** (see §4): require observed user keystrokes/dwell
   before crediting an edit; ignore changes within a few hundred ms of insertion with
   no keystrokes (system/autocorrect); never re-offer a declined word.

**Default thresholds** (tune on real data): changed-ratio ≤ 0.3; substitutions = 1
(≤2 contiguous allowed); Levenshtein ≤ 2 or ≤ 30%; Double Metaphone primary equal or
code-dist ≤ 1; reject `new` in top ~30–50k frequency list.

**Output contract** (the "wire format" other agents consume):
```
Decision = {
  action: "offer" | "silent_learn" | "ignore",
  old: str, new: str,
  confidence: float,          # 0..1
  is_proper_noun: bool,
  reason: str,                # human-readable why (for logs + audit)
}
```

---

## 3. TARGET ARCHITECTURE (what to build)

New module `app/autolearn.py` (pure/testable core + a thin AX watcher):
- `align(t_tokens, e_tokens) -> [Op]` — token alignment (pure, no deps beyond stdlib;
  implement Needleman–Wunsch; small inputs).
- `classify(inserted_text, edited_text, config) -> Decision` — the §2 pipeline (pure,
  fully unit-testable without a mic or AX). Uses a bundled frequency wordlist +
  Double Metaphone + Levenshtein (vendored tiny implementations; no heavy deps).
- `EditWatcher` — arms an AX read-back after injection: snapshot target
  (pid/bundle/element/insertion range/inserted text); observe
  `kAXValueChangedNotification` on the focused element + `kAXFocusedUIElementChanged`
  on the app; **debounce ~600–1000ms**; on quiescence/focus-loss read `AXValue`
  (bounded to the insertion region via `AXSelectedTextRange`), call `classify`, and
  emit a Decision. Skip secure fields, terminals, unreadable/Electron-flaky targets.
- `record_offered(config, word)` / `is_declined(config, word)` — per-word memory.
- Persist: on confirm, `dictionary.add_replacement(config, old, new, save_config)`;
  tag the rule as auto-learned (e.g. `{"from","to","auto":true}` — extend `normalize`
  to preserve the flag) for the ✨ audit list.

Two acquisition paths (tiered):
- **In-place (magical):** `EditWatcher` on the external field. Best-effort; native
  Cocoa fields reliable, Electron/web/terminal skipped or best-effort with a sanity
  check (read must contain our inserted text).
- **History-view (reliable):** generalize `_learn_from_edit` (shared_dashboard.py:372)
  to call the same `classify()` so edits made inside Verbal's own transcript view get
  the full intelligence + prompt. Zero AX, zero cross-app flakiness.

Wiring:
- `main.py:620` after `inject_text(...)`: if `autolearn_enabled` and target is a
  safe text field, `EditWatcher.arm(target, inserted=result)` on a daemon thread.
- Widget: on `action=="offer"`, show a **non-modal** confirm (rumps.alert first cut;
  styled overlay toast as the polished version) with **Add / No / Never**; on Add →
  persist. Batch if several words qualify from one edit.
- Toggle + ✨ audit list (review/remove auto-learned rules) on the **Dictionary screen**.

---

## 4. FAILURE SCENARIOS & MITIGATIONS (build so these can't bite)
| # | Scenario | Risk | Mitigation |
|---|---|---|---|
| F1 | **Deletion mistaken for correction** (the user's core worry) | learns garbage / offers on erase | alignment gate: insert/delete ops present → reject; only 1 substitution offers (§2.2) |
| F2 | Can't read target field (AXValue empty/unavailable) | no `E`, can't diff | fail closed — no offer; optionally fall back to history-view path |
| F3 | **Secure/password field** | privacy breach; capture secrets | detect `AXSecureTextField` role/subrole → skip entirely; never persist raw text |
| F4 | User navigates away mid-edit | read wrong field / partial edit | snapshot element identity at insertion; finalize diff only against the *original* element; if focus left before debounce, use last-good value or abandon |
| F5 | Multiple simultaneous edits | >1 substitution → gate rejects | safe reject; optionally offer each independent single-token sub separately, capped |
| F6 | Word occurs multiple times | ambiguous instance / mis-pair | position anchoring in alignment; if still ambiguous, skip |
| F7 | Homophones ("their"→"there") | phonetic pass but grammar, not vocab | common-word filter (§2.6) rejects — never learn wordlist words |
| F8 | Correction is itself a typo ("Shabbar"→"Shabbr") | poisons future output | require `new` to persist through the debounce; confirm widget shows before→after; optional frequency confirmation (seen ≥2×) before hardening; one-click undo/audit |
| F9 | Duplicate/repeat prompts | nag fatigue → user disables | per-word offered/declined set; never re-offer a declined word; batch multi-word edits into one widget |
| F10 | **OS autocorrect false-attribution** | learns a change the user didn't make | require observed user keystroke activity + dwell before crediting; ignore value changes <~300ms post-insert with no keystrokes; suspicious if a valid term→common autocorrect target |
| F11 | Very long doc, small inserted region | expensive/noisy diff | bound diff to insertion window via `AXSelectedTextRange`/offset; ignore edits outside it |
| F12 | Non-text targets (terminal, canvas, code panes) | AX text semantics absent/misleading | gate on real text-field role with readable `AXValue`; reuse `focus_is_terminal()`; denylist known-bad bundles |
| F13 | Electron/web AX unreliable (Slack, VS Code, Chrome) | stale/chunked/wrong reads | sanity-check the read contains our inserted text before diffing; else skip (prefer under-trigger) |
| F14 | Config write race / churn | corrupt config or save storms | inherit atomic `save_config` + `_config_lock`; write only on confirmed learn (never per keystroke) |
| F15 | Widget steals focus from user's app | disrupts flow, could send keystrokes to wrong place | non-modal, main-thread, auto-dismiss; never grab focus mid-typing; fire only after edit finalized |
| F16 | Feature interacts with file-tagging / replacements | double-processing | only learn from *manual* edits, not from our own dict/tag transforms; skip if the changed token was produced by a replacement/tag |

---

## 5. HARNESS ENGINEERING (how the swarm runs)
- **Topology:** a **Project-Manager / Orchestrator agent (PM)** owns the loop. It
  decomposes the work, spawns specialist sub-agents, passes **structured artifacts**
  between them (the contracts in §2 & §6), gates every stage on verification, and
  decides done-vs-iterate. Sub-agents never talk to the user; they return data to the PM.
- **Connected, not siloed:** each agent's output is another's typed input (wire
  formats below). The PM threads them: Detector→Aligner→Classifier→Guards→(UI, Writer),
  with QA verifying the pure core continuously. No agent guesses another's format.
- **Determinism:** control flow (order, retries, done-checks) is fixed by the PM;
  agents only do their scoped job and return `{status, artifacts, evidence, blockers}`.
- **Isolation:** agents that mutate files run in a **git worktree** so parallel edits
  don't collide; read-only agents never write.
- **Author ≠ verifier:** every produced change is verified by a DIFFERENT agent than
  the one that wrote it. Nothing merges unverified.
- **Budget:** cheap→expensive (recon → pure core+tests → AX watcher → integrate →
  adversarial verify). Stop as soon as acceptance tests pass + human confirms on device.

---

## 6. THE SWARM (project manager + connected specialists)

Each agent: **Role · Inputs · Outputs (wire format) · Done-when · Rules.**

### PM — Project Manager / Orchestrator
- **Role:** run §7 loop; spawn/sequence A1→(A3‖A4‖A5 core)→A2→A6/A7→A8→A9; route
  failures back to the owning agent; gate on evidence; surface a crisp status + the
  one on-device test the human must run.
- **Inputs:** this file.
- **Outputs:** phase log + final DoD status.
- **Rules:** never declare success on unverified work; if A9 red, hand the failing
  fixture to the owning agent; stop only when §0 criteria provably met (fixtures) +
  human confirms on device. Keep sub-agents connected via the exact contracts below.

### A1 — Recon (read-only)
- **Role:** confirm §1c anchors still exist (file:line); flag drift.
- **Outputs:** `{anchors: [{sym,file,line,ok}], drift: [...]}`.
- **Done-when:** every reuse anchor verified. **Rules:** no edits; report staleness, don't adapt silently.

### A3 — Aligner (pure)
- **Role:** build `align(t_tokens, e_tokens)` (Needleman–Wunsch) in `app/autolearn.py`.
- **Inputs:** two token lists. **Outputs:** `[Op{type,old,new,pos}]` + `changed_ratio`.
- **Done-when:** correct ops for match/sub/insert/delete on A9 fixtures (incl. repeated words).
- **Rules:** stdlib only; deterministic; O(n·m) is fine (inputs are short).

### A4 — Classifier / "the brain" (pure)
- **Role:** build `classify(inserted, edited, config) -> Decision` (§2 pipeline):
  edit-shape gate → phonetic (Double Metaphone) → orthographic (Levenshtein) →
  case/punct filter → common-word/proper-noun filter.
- **Inputs:** inserted text, edited text, config (for declined memory + dict).
- **Outputs:** `Decision` (§2c). **Done-when:** all §0 scenarios classify correctly on A9.
- **Rules:** vendor tiny Double Metaphone + Levenshtein + a bundled frequency wordlist
  (no heavy deps); pure & fully testable without mic/AX; every reject carries a `reason`.

### A5 — Anti-False-Attribution & Memory (pure + config)
- **Role:** the F8/F9/F10 guards — keystroke/dwell confirmation signal, per-word
  offered/declined memory (`record_offered`/`is_declined`), optional frequency
  confirmation before hardening.
- **Inputs:** Decision + observation metadata (keystrokes seen, dwell, timing) + config.
- **Outputs:** `Decision` (possibly downgraded to `ignore`) + memory writes.
- **Done-when:** autocorrect/typo/declined-word fixtures all suppressed. **Rules:**
  never re-offer declined; write memory via atomic `save_config`.

### A2 — Edit-Detector (AX watcher)
- **Role:** `EditWatcher` — arm after injection, observe `AXValueChanged` +
  `AXFocusedUIElementChanged`, debounce ~600–1000ms, read `AXValue` bounded to the
  insertion region, hand `(inserted, edited, observation-meta)` to A4/A5.
- **Inputs:** target pid/bundle/element, inserted text, insertion range.
- **Outputs:** an `EditEvent{target_pid, bundle, element_id, inserted, edited,
  range, keystrokes_observed, ts}` or nothing.
- **Done-when:** on a native Cocoa field, a real single-word edit yields a correct
  EditEvent; secure/terminal/Electron-flaky targets yield nothing and never raise.
- **Rules:** reuse `filetags._ax_attr`, `AXUIElementCreateApplication`,
  `focus_is_terminal`; hard timeouts; every AX call guarded; **never touch the
  injection/clipboard path**; run off the recording critical path (daemon thread).

### A6 — UI / Prompt widget
- **Role:** on `action=="offer"`, show a **non-modal** "Add `old` → `new`?"
  widget (rumps.alert first cut; styled overlay toast as polish) with **Add / No /
  Never**; batch multiple; wire **undo**; build the **✨ audit list** on the
  Dictionary screen (review/remove auto-learned rules) + the settings toggle.
- **Inputs:** Decision(s). **Outputs:** user choice → A7 or memory (decline/never).
- **Done-when:** widget shows before→after, never steals focus mid-typing, batches,
  never re-appears for a declined word. **Rules:** main-thread; auto-dismiss; reuse
  rumps/overlay/`_Bridge`; do not alter existing overlay visuals beyond the toast.

### A7 — Dictionary-Writer
- **Role:** persist a confirmed rule via `dictionary.add_replacement(config, old, new,
  save_config)`; mark it auto-learned for the audit list; ensure it then applies via
  `apply_replacements` and syncs remote.
- **Inputs:** confirmed `(old,new)`. **Outputs:** `{added, rule, deduped}`.
- **Done-when:** rule appears in dict, de-dupes, survives restart, syncs, and a
  subsequent transcription of `old` yields `new`. **Rules:** reuse dictionary module;
  extend `normalize` to preserve an `auto` flag without breaking existing rules.

### A8 — Integration (worktree)
- **Role:** wire A2–A7 into `main.py:620` (arm watcher), the history-view path
  (`_learn_from_edit`→`classify`), the toggle + audit UI on the Dictionary screen, and
  add `app.autolearn` to the 3 PyInstaller specs.
- **Done-when:** `py_compile` + `import app.main` + `node --check` dashboard JS pass;
  toggle defaults set; nothing unrelated changed.
- **Rules:** touch only what's necessary; keep dictionary/recording/file-tagging paths intact.

### A9 — Adversarial QA (author ≠ this agent)
- **Role:** write + run mic-free fixtures over `(inserted, edited)` pairs asserting
  `classify()`/`align()` decisions. Cover the full §0 matrix + every §4 failure as a
  negative test (deletion, insertion, rephrase, homophone, common word, typo,
  autocorrect-timing, declined-word, repeated-word alignment, case/punct-only, long-doc
  window). Try to BREAK the classifier; report holes.
- **Done-when:** all fixtures green; adversarial cases suppressed. **Rules:** adversarial
  by default — assume the classifier is wrong until fixtures prove otherwise; one red = not done.

**Wire formats (the connective tissue):** `Op`, `Decision` (§2c), `EditEvent` (A2),
`{added,rule,deduped}` (A7), `{status,artifacts,evidence,blockers}` (every agent → PM).

---

## 7. LOOP ENGINEERING (iterate until proven)
```
recon (A1)
  └─ pure core (parallel, read-mostly):  A3 (align) ‖ A4 (classify) ‖ A5 (guards)
       └─ prove core:  A9 fixtures over the §0 matrix + every §4 failure
            ├─ ANY RED → PM routes the failing fixture to A3/A4/A5 → re-run
            └─ ALL GREEN
                 └─ detector: A2 (AX watcher, off critical path)
                      └─ surface: A6 (widget + audit + toggle)  ‖  A7 (writer)
                           └─ integrate: A8 (wire + specs + compile/lint/import)
                                └─ verify: A9 again (integration-level)
                                     ├─ ALL GREEN → hand human the ONE on-device test (§0.1–2)
                                     │                 └─ human confirms → DONE
                                     └─ ANY RED → PM routes to owner → re-run from there
```
**Termination:** exits only when A9 is fully green **and** the human on-device check
passes. Bad-path (can't read AX / unreliable target) must degrade to "no offer,
nothing learned, transcription unaffected" — a valid stable state, not a retry loop.

**Anti-thrash:** cap build↔verify cycles; if in-place AX proves too unreliable across
apps, ship the **history-view path first** (fully reliable) and mark in-place as
best-effort, logging what was skipped.

---

## 8. GLOBAL RULES (every agent, always)
1. **Do no harm to recording/injection.** In doubt, no-op; let dictation proceed.
2. **Correction ≠ deletion ≠ rephrase** — the one substitution gate is sacred.
3. **Privacy:** never read secure fields; never persist raw field text — only `(old,new)`.
4. **Verify before claiming done** — compile + import + `node --check` + fixtures.
5. **Author ≠ verifier.** Self-certified code doesn't merge.
6. **Reuse the dictionary + config/sync machinery**; don't fork prompt/replace logic.
7. **No prompt spam** — declined memory, batching, non-modal, respect the toggle.
8. **Structured returns only**; evidence (fixture output, file:line) over prose.
9. **Don't touch** overlay visuals (beyond the toast), sounds, auth, canvas, notes, file-tagging.
10. Every AX/file/network op is timeout- and exception-guarded.

---

## 9. DEFINITION OF DONE (acceptance)
- [ ] `app/autolearn.py` exists: `align()`, `classify()`, `EditWatcher`, memory helpers.
- [ ] Single-word mis-transcription ("Shabar"→"Shabbar") → offered → confirmed → learned → applied on next dictation.
- [ ] Deletion, insertion, rephrase, homophone, common-word ("teh"→"the"), case/punct-only → **NOT** offered.
- [ ] OS-autocorrect / typed-typo / declined-word cases suppressed (F8/F9/F10).
- [ ] Secure fields never read; unreadable/terminal/Electron-flaky targets → silent no-op.
- [ ] Learned rules are auditable (✨ list) and one-click removable; toggle present; OFF = zero behavior change.
- [ ] History-view edit path uses the same `classify()` intelligence.
- [ ] Reuses `dictionary.add_replacement` + atomic `save_config`; rule syncs to Supabase; survives restart.
- [ ] All A9 fixtures green; `py_compile` + import + `node --check` clean.
- [ ] Human on-device confirmation recorded here: __________
```
