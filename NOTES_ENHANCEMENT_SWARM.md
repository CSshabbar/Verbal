# Notes Enhancement — Feature Spec & Swarm Plan (v2)

> Status: **Proposed — not yet built.** Full implementation plan for both platforms, complete
> end-to-end checklist, multi-agent loop plan, and — added in v2 — the design decisions that a first
> pass didn't fully answer: raw-vs-cleaned handling, sync conflict behavior, feature flags, cost
> control, empty-state/first-run behavior, accessibility, forward-compat, performance guardrails, and a
> real post-ship validation step. Once built, update `03-features.md`, `01-product.md`, and
> `04-data-model.md` per the project's maintenance contract.

## Mission

Notes today is functional but thin: dictate into a note, organize into folders, pin favorites, desktop
gets AI-cleaned formatting, mobile doesn't, and there's no way to search across notes at all. This spec
closes the basic gaps and adds voice-native differentiators that make Notes feel distinctly Flume,
rather than a generic notes app with a mic bolted on.

**Unlike the Keyboard feature, this is almost entirely buildable and verifiable in a normal Claude Code
environment** — Python and TypeScript, no native toolchain. Scope this as a real build-test-iterate
loop.

## Scope for v1

1. **Full-text search** across all notes, both platforms
2. **Auto-titling** — a dictated note names itself
3. **Structure detection** — rambling speech that's actually a list gets formatted as a real,
   interactive checklist, not prose
4. **Note ↔ source-recording linkage** — play back the original audio behind any voice-dictated note

**Required prerequisite:** mobile notes are currently never run through AI cleanup at all (`formatNotes`
exists in `lib/groq.ts` but isn't wired into the note editor). Auto-titling and structure detection both
depend on this pipeline running on mobile, so wiring it up is the first task, not a nice-to-have.

## Design decisions this spec commits to (don't re-litigate mid-build)

The first draft of this doc dodged several judgment calls. This section resolves them explicitly so no
agent has to guess.

### 1. Raw transcript vs. AI-formatted output — both are kept

Every voice-dictated note stores **both** the raw transcript and the AI-formatted version. The user sees
the formatted version by default; a small "show original" affordance in the note toolbar reveals the raw
transcript. This costs one extra text field per note and eliminates the "AI mangled what I said and I
can't get it back" failure mode entirely. Do not ship this feature without it.

- **Schema:** add `raw_content text` (nullable) to `notes` alongside the new `audio_segments` column.
- **Backward compat:** for notes created before this change, `raw_content` is null; the "show original"
  affordance is hidden.

### 2. Cost control — don't re-run cleanup on every save

Auto-titling + structure detection = an LLM call per note save. Without a guardrail, editing a note ten
times in an hour is ten LLM calls per note.

- Cleanup runs **once** on the initial save of a dictated note (creates the formatted version + title).
- Subsequent edits do **not** re-run cleanup unless the user explicitly triggers "Reformat" from the
  toolbar.
- Manual typed edits (not dictated) never trigger cleanup automatically.
- Additional dictation appended to an existing note runs cleanup only on the newly-appended segment,
  not the whole note.

### 3. Sync conflict handling — better than "last write wins"

Notes currently sync via newest-`updated_at`-wins. That's tolerable for small text edits, unacceptable
when a losing edit takes an audio segment or a whole formatted-content field with it.

- On sync-merge, if two devices modified the same note within a short window (proposed: 60 seconds),
  keep both versions locally as a **conflict pair** and surface a one-time "resolve" prompt in the note
  editor rather than silently discarding one.
- Fields that are pure-append (`audio_segments` is a list of audio references) should **union** on merge,
  not overwrite — if both devices added a segment, both are kept.
- This is the single most important addition v2 makes. Don't skip it because it feels like scope creep.

### 4. Feature flags — every new feature is toggleable

Every one of the four features must land behind a per-user flag in `config` (desktop) / AsyncStorage
(mobile), on by default but individually disable-able from Settings. If auto-titling misfires, the fix
must be one toggle, not a support ticket. Flags:

- `notes_search_enabled` (default true)
- `notes_autotitle_enabled` (default true)
- `notes_structure_detection_enabled` (default true)
- `notes_audio_linkage_enabled` (default true)

### 5. First-run behavior — never retroactively modify existing notes

- Existing notes at the time of the update: no auto-title backfill, no structure re-detection, no
  retroactive audio linkage. Their `raw_content` and `audio_segments` stay null/empty.
- Only notes created *after* the update participate in the new behaviors.
- Search works over existing notes immediately (it's just a query, not a mutation).

### 6. Empty states and edge conditions
- Search with no notes: friendly empty state ("No notes yet — dictate one to get started").
- Search with no results: "No notes match [query]" + a clear-search action.
- A note with no audio segments (typed, not dictated): no playback control shown at all — not a
  disabled-looking one.
- A dictated note where cleanup failed (network dropped): raw transcript is still saved; formatted
  version is null; UI falls back to showing raw, and a small "Retry formatting" affordance appears in
  the toolbar.

### 7. Forward-compat — the neglected direction

The v1 draft covered "old clients reading new-field-absent notes." It missed the reverse:

- Older clients (e.g. desktop 1.0.10) reading a note that *does* have the new fields must ignore
  fields they don't understand rather than crashing or discarding them on write-back.
- Concretely: when an older client saves a note it doesn't fully understand, it must **preserve unknown
  fields verbatim** rather than replacing the row with only the fields it knows about. This is a real
  behavioral requirement for the sync code, not just tolerant deserialization.

### 8. Accessibility (a11y)
- Interactive checklist items: each rendered as a real checkbox with proper accessibility role/label
  (VoiceOver on iOS, TalkBack on Android, and a proper `role="checkbox"` in the desktop WKWebView).
- The playback control per audio segment has a text label ("Play recording from [time]"), not just an
  icon.
- Search field has an accessible label and announces result count on updates.
- Contrast: any new UI element uses the existing `flume-ui/theme/` tokens; do not introduce new colors
  in this build.

### 9. Performance guardrails
- Full-text search must remain interactive (subjective target: <100 ms feels immediate) up to **at least
  1,000 notes** — the realistic upper end for a heavy Flume user over a couple of years. If a naive
  linear scan gets slow beyond that, build a simple in-memory index once at app start; do not ship
  server-side search in v1.
- LLM formatting calls have a **hard timeout** (proposed: 8 seconds). On timeout, the note is saved with
  raw content only, and the "Retry formatting" affordance appears.

### 10. Groq prompt cap distinction

Adding structure-detection rules extends `NOTES_FORMATTER_SYSTEM_PROMPT`, which is the **LLM system
prompt**, not the **Whisper bias prompt**. Hard Rule #6 in `05-conventions.md` (896-char cap) applies to
the Whisper bias prompt only. Named here so no agent conflates the two constraints.

## Context every agent should read before starting

- `01-product.md` — glossary, feature matrix (Notes row)
- `03-features.md` § Notes and § AI cleanup / formatting
- `04-data-model.md` § `notes` table, § Recordings storage, § Sync model, § Schema gaps
- `05-conventions.md` — Hard Rule #1 (never break the dictation path), Hard Rule #6 (prompt cap
  applies to Whisper, not the LLM system prompt), dead/legacy code list (specifically the note about
  `lib/MarkdownText.tsx` and `lib/theme.ts`), verification checklist
- Source files: `ai_cleanup.py`, `shared_dashboard.py` (`DashboardApi`), `flume_dashboard_html.py`,
  `recordings.py`, `notes_migration.sql`, `lib/notesStorage.ts`, `flume-ui/hooks/useNotes.ts`,
  `lib/groq.ts`, `lib/recordings.ts`, `flume-ui/screens/NoteEditorScreen.tsx`

## Feature 1 — Full-text search

- **Desktop:** new `DashboardApi.search_notes(query)` — case-insensitive substring across title and
  content, title matches ranked above content matches, recency as tiebreaker.
- **Mobile:** matching function in `useNotes.ts` or new `lib/notesSearch.ts`, identical ranking.
- **UI:** search field at top of the notes list, live-filtering as the user types.
- **Explicitly not v1:** semantic/natural-language search — deferred, needs real retrieval infra.
- **Perf guardrail:** stays under ~100 ms up to 1,000 notes; if that's not naturally the case, add a
  simple in-memory index built at app start.

## Feature 2 — Auto-titling

- **Prerequisite (mobile):** wire `formatNotes` into the note-save path in `NoteEditorScreen` /
  `useNotes.ts`.
- **Desktop:** extend `format_note_with_ai` to return `{title, formatted_content}` in one call.
- **Mobile:** matching extension on the mobile side.
- **Apply-only-if-untitled rule:** auto-title only ever fires on the *first* save of a note created with
  an empty title. Never overwrite a title the user has manually set.
- Both raw and formatted content are stored (see Design Decision 1).

## Feature 3 — Structure detection (voice-dictated checklists)

- Extend `NOTES_FORMATTER_SYSTEM_PROMPT` (and mobile equivalent) with rules for detecting enumerable
  speech and outputting markdown task-list syntax (`- [ ] item`) rather than prose.
- **Desktop rendering:** hand-rolled markdown-to-HTML parser scoped to checklists, bullets, and bold —
  no library dependency, matches the project's raw-strings approach.
- **Mobile rendering:** fresh markdown-to-RN-components renderer against `flume-ui/theme/` tokens. Do
  **not** revive the legacy `lib/MarkdownText.tsx` (it depends on stale `lib/theme.ts`).
- **Checklist interactivity:** tapping a checkbox toggles `- [ ]` ↔ `- [x]` in the underlying content
  and persists immediately. Each checkbox has proper accessible role and label.

## Feature 4 — Note ↔ source-recording linkage

- **Schema:** add `audio_segments jsonb default '[]'`, shape `[{id, url, created_at}]`, to notes. A note
  accumulates multiple segments over time — this is a list, not a single URL.
- **Desktop:** `note_dictate_start/stop` persists the underlying recording (mirroring `recordings.py`)
  and appends to the note's `audio_segments`.
- **Mobile:** matching change in the `NoteEditorScreen` dictation flow via `lib/recordings.ts`'s
  `persist`/`uploadCloud`.
- **UI:** small play control per segment at the top of the note. Reuses existing playback infra
  (`DashboardApi.play_recording`/`get_audio` desktop; `expo-audio` mobile).
- **Forward-compat behavior:** older clients that don't understand `audio_segments` must preserve the
  field verbatim on write-back (see Design Decision 7).

## Testing plan

### Automated
- Search ranking logic (title beats content, recency tiebreak) — both platforms
- Auto-title "never overwrite manual title" rule — both platforms
- Fixture tests for structure-detection prompt against a corpus of realistic sample transcripts
  (rambling-implied-list vs. plain prose vs. mixed) — match the `autolearn_fixtures.py` pattern
- `audio_segments` round-trip: append, read back, absent-field tolerance, unknown-field preservation on
  write-back
- Cost-control behavior: same note edited N times triggers exactly one LLM call unless user requests
  "Reformat"
- Feature-flag off state: each of the four flags disables its feature cleanly without breaking the
  editor
- Sync conflict test: two devices edit the same note within the conflict window → both versions kept,
  neither silently discarded

### Manual / integration
- Dictate a new note on each platform → title, structure, audio link all correct
- "Show original" affordance retrieves raw transcript unchanged
- Retry-formatting affordance appears and works after a simulated formatting failure (block the
  network for the LLM call to reproduce)
- Search UX check with a realistic library size (aim for a few hundred notes, not 3)
- Checklist toggle persists after navigating away and back
- Cross-device sync of a note using all new fields
- Accessibility pass: VoiceOver (iOS), TalkBack (Android), keyboard nav + screen reader on desktop
  WKWebView
- Perf sanity check: measure search response time at 100, 500, 1,000 notes

### Regression
- Pre-existing notes (all new fields absent) open and edit normally
- Existing local-first merge/sync behavior unaffected for notes without new-field activity
- Older-client write-back preserves unknown fields verbatim (test with an older build if available)

### Post-ship validation — this is a required step, not a suggestion
- Two-week dogfood window: the builder uses Notes as their real note-taking tool for two weeks with
  telemetry off, keeping a running list of every misfire (bad structure detection, wrong auto-title, UI
  friction).
- At the end of the window, review the list against the fixture set — for any category with more than
  ~2 real misfires, add a fixture and re-tune the prompt before considering the feature "done."
- The feature is not done until this validation happens. "Checklist ticked" is a necessary but not
  sufficient condition.

## Swarm plan — multi-agent build breakdown

| Agent | Owns | Depends on |
|---|---|---|
| **A — Desktop logic** | `ai_cleanup.py` extensions, `note_dictate_start/stop` audio linkage, `search_notes`, feature-flag reads | Schema shape from Agent E |
| **B — Desktop UI** | Dashboard notes: search field, markdown rendering, checklist toggle, playback control, show-original toggle, retry-formatting affordance, settings UI for feature flags | Agent A's method signatures |
| **C — Mobile logic** | Wiring `formatNotes` into save path (prerequisite), title/structure extensions, mobile search, audio linkage via `lib/recordings.ts`, feature-flag reads | Schema shape from Agent E |
| **D — Mobile UI** | `NoteEditorScreen`: search field, fresh markdown renderer, checklist toggle, playback, show-original toggle, retry-formatting, settings for feature flags | Agent C's hook signatures |
| **E — Schema, sync, migration** | New `notes` columns (`audio_segments`, `raw_content`), conflict-pair sync behavior, forward-compat unknown-field preservation, updates `04-data-model.md` | Nothing — start first |
| **F — Test, fixtures, and post-ship validation** | Automated tests, fixture files for structure detection, dogfood-log template | Testable code from A/B/C/D |
| **G — Docs & maintenance** | `03-features.md`, `01-product.md` matrix, `05-conventions.md` if new rules emerge | Everything else landing |

**Sequencing:**
1. **E runs first, alone** — publishes the schema shape, the conflict-pair behavior contract, and the
   forward-compat write-back rule. Nothing else can be finalized until these are published.
2. **A and C start in parallel immediately after**, building against the published contract.
3. **B and D start once A and C publish their function/method signatures** — same "agree the contract,
   then build against it in parallel" pattern used across other Flume feature specs.
4. **F builds fixtures and the dogfood-log template in parallel with A–D**, then runs the automated
   suite once code exists.
5. **G runs last**, once everything else has landed and F's suite is green **and** the two-week
   dogfood validation has completed.

**The orchestration loop:**

```
1. E publishes schema + sync-behavior contract
2. A/C publish function signatures once drafted
3. B/D build against those signatures without waiting for full A/C implementation
4. Integration pass — wire A+B, C+D per platform
5. Run automated tests; if any red, route back to the specific owning agent
6. Manual test + a11y + perf checklist
7. Two-week dogfood window
8. Retune structure-detection prompt based on real misfires
9. Only after that: G ships doc updates and the feature is considered done
```

**Practices to hold the loop to:**
- Every agent reads its context list before writing anything. Guessing at conventions is exactly how
  Hard Rule violations creep in.
- Verify with the project's own tools: `py_compile` + `import app.main` for desktop, `npx tsc --noEmit`
  for mobile.
- Commit in slices matching agent boundaries — makes it clear which piece broke on failure.
- If an agent can't verify something in its environment, it says so plainly rather than guessing.

## End-to-end checklist

**Schema & sync**
- [ ] `notes` migration adds `audio_segments jsonb default '[]'` and `raw_content text`
- [ ] Sync-merge conflict-pair behavior implemented (both platforms)
- [ ] `audio_segments` union-on-merge behavior implemented (both platforms)
- [ ] Older-client unknown-field preservation on write-back verified
- [ ] `04-data-model.md` updated

**Feature flags**
- [ ] All four flags plumbed to config/AsyncStorage
- [ ] Settings UI to toggle each flag (both platforms)
- [ ] Feature-flag-off state cleanly disables without breaking editor

**Desktop**
- [ ] `search_notes` implemented + ranked correctly + perf-tested to 1,000 notes
- [ ] `format_note_with_ai` returns `{title, formatted_content}` in one call
- [ ] Both `raw_content` and formatted content stored on dictated saves
- [ ] Cost control: cleanup runs only on initial save + explicit Reformat, not every save
- [ ] Auto-title never overwrites manually-set titles
- [ ] Structure-detection rules added to `NOTES_FORMATTER_SYSTEM_PROMPT`
- [ ] `note_dictate_start/stop` persists recordings, appends to `audio_segments`
- [ ] Dashboard UI: search field, markdown/checklist rendering, playback per segment,
  show-original toggle, retry-formatting affordance
- [ ] Accessibility: role="checkbox" on list items, labeled play buttons, labeled search field
- [ ] `py_compile` + `import app.main` clean

**Mobile**
- [ ] `formatNotes` wired into note-save path
- [ ] Feature and behavior parity with desktop (all bullets above)
- [ ] Fresh markdown renderer built (not legacy `MarkdownText.tsx`)
- [ ] Accessibility: VoiceOver + TalkBack pass for checklists, playback, search
- [ ] `npx tsc --noEmit` clean

**Testing**
- [ ] All automated tests above passing
- [ ] Manual integration checklist above passing
- [ ] Perf sanity check at 100 / 500 / 1,000 notes documented
- [ ] Accessibility pass complete on all three surfaces (desktop WKWebView, iOS, Android)
- [ ] Two-week dogfood window completed, misfire log reviewed, prompt retuned if needed

**Docs**
- [ ] `03-features.md` Notes section updated
- [ ] `01-product.md` matrix updated
- [ ] `05-conventions.md` updated if new patterns/rules emerged

## Definition of done

Every box above checked, both platforms at parity for these four features, the maintenance-contract doc
updates landed in the same change, **and** the two-week post-ship validation has actually happened. A
green checklist without the validation window is not done.
