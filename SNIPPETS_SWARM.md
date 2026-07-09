# Snippets — Feature Spec

> Status: **Proposed — not yet built.** This is the implementation plan. Once built, fold a summary into
> `03-features.md` (new "Snippets" section) and add a row to the `01-product.md` feature matrix, per the
> project's maintenance contract. If a schema change is made, record it in `04-data-model.md`.

## Mission

Let a user define a short spoken phrase ("trigger") that expands into a longer saved block of text
("expansion") — a LinkedIn URL, a GitHub profile, an email signature, a scheduling link, a standard
disclaimer paragraph. You say the trigger naturally inside normal speech (not a fixed command syntax),
and it expands in place while the rest of the sentence is left untouched. This closes a feature-parity
gap against Wispr Flow, which ships an equivalent ("snippets") today.

## Concept

Snippets are a generalization of the existing custom-dictionary replacement-rule mechanism
(`{from, to}` in `dictionary.py`), stretched two ways: the "to" side becomes an arbitrary block of text
instead of a single word, and matching happens on a **phrase** rather than requiring an exact single-
token hit. This is deliberately *not* a new subsystem — it should reuse the dictionary's storage shape,
sync path, and UI surface wherever possible, to avoid inventing parallel infrastructure for something
that's conceptually a sibling of the dictionary, not a new category of feature.

## Data model

**Decision: extend the existing `dictionary` table rather than create a new table.** One row per user
already exists there (`vocabulary`, `replacements`); add a third array:

```
dictionary.snippets  jsonb, default '[]'
```

Shape: `[{id, trigger, expansion, label?, created_at, updated_at}]`

- `id` — client-generated short id (same pattern as replacement-rule handling)
- `trigger` — string, the phrase that gets spoken. Cap at 60 characters (matches the real-world cap
  competitors use). Case-insensitive match.
- `expansion` — string, the text inserted. Cap generously (proposed: 1,000 characters) — needs to fit a
  full paragraph, not just a URL.
- `label` — optional short display name shown in the list UI; falls back to `trigger` if unset.
- Dedupe by `trigger` (case-insensitive), same instinct as `add_replacement`'s de-dupe by `from`.

**Why not a separate table:** fewer moving parts, and it inherits the sync path already trusted for the
dictionary (`fetch_remote`/`_push_remote`, one row per user, last-write-wins on `updated_at`). Revisit
this decision only if snippet lists grow large enough to need independent pagination/RLS from the rest
of the dictionary — not expected for v1.

## Desktop implementation (`whisperflow/app/`)

Extend `dictionary.py`:
- `add_snippet(trigger, expansion, label=None)` — dedupe by trigger, generate id, append to
  `config['dictionary']['snippets']`, push to Supabase. Mirrors `add_replacement`.
- `update_snippet(id, **fields)`, `remove_snippet(id)`.
- `apply_snippets(text, snippets)` — **new function.** Phrase-boundary regex match, case-insensitive,
  multi-word aware (unlike `apply_replacements`, which only matches single tokens). Match **longest
  trigger first** to resolve cases where one trigger is a substring of another (e.g. "my email" vs.
  "my email address"). Single pass only — never re-scan an inserted expansion for further triggers
  (no recursive/nested expansion; avoids surprise cascades or infinite loops).

**Pipeline placement:** run `apply_snippets` **after** AI cleanup (`ai_cleanup.process_text`),
immediately before injection (`injector.inject_text`). Cleanup must not be allowed to paraphrase away a
trigger phrase or mangle a URL sitting in the final text. This mirrors where `filetags.py`'s `@`-tag
rewriting already sits in the finalize sequence — post-cleanup, pre-inject.

**Optional (v1.1, not required to ship):** fold trigger phrases into the Whisper bias prompt
(`dictionary.build_prompt`) so unusual short triggers are heard correctly. Budget-check against the
existing **896-character Groq prompt cap** (`05-conventions.md` §6) — vocabulary, open-file tags, and
snippet triggers would all compete for the same prompt budget; decide trim order before shipping this
part (current rule is glossary-first).

**New WKWebView surface:** a **Snippets tab**, alongside the existing Dictionary tab in the dashboard.
Reuses the existing JS↔Python bridge (`DashboardApi`) — add `fetch_snippets`, `add_snippet`,
`update_snippet`, `delete_snippet`, same pattern as `fetch_notes`/`save_note`/`delete_note`.

## Mobile implementation (`verbal-mobile/`)

- Extend `lib/dictionary.ts` — mirror the desktop functions (`addSnippet`, `updateSnippet`,
  `removeSnippet`, `applySnippets`), same AsyncStorage (`flume_dictionary`) + Supabase upsert pattern
  already used for replacements/vocabulary.
- Apply snippets client-side after `formatText` (AI cleanup), before the result is inserted/appended —
  same ordering as desktop.
- New screen: `SnippetsScreen.tsx` in `flume-ui/screens/`, reachable from Settings next to the existing
  Dictionary entry point (same sub-stack pattern as Settings → Devices → PairDevice).
- New hook: `useSnippets.ts` + sibling `useSnippets.mock.ts` — required by the project's existing
  `.mock.ts` contract (exact same exported shape, in-memory backing, never imported at runtime).

## Screen content & interactions (shared information architecture, both platforms)

**List screen — "Snippets"**
- Header: "Snippets" + one-line subhead explaining the feature ("Say a phrase, get the full text.")
- Primary action: **"+ New snippet"**, opens the add/edit form
- Each row shows: label (or trigger if no label), the trigger phrase as secondary text
  ("Trigger: my LinkedIn"), a truncated preview of the expansion (~40 characters + "…"), and edit/delete
  affordances (swipe-to-delete on mobile, hover actions on desktop — matches the existing Dictionary row
  pattern)
- Empty state: friendly copy — "No snippets yet — save a link or phrase you say often." + a prominent
  "+ New snippet" CTA
- Search/filter field — nice to have once the list grows; not required for v1

**Add/Edit form** (modal on desktop, sheet or full screen on mobile)
- **Label** (optional, short — display name, e.g. "LinkedIn")
- **Trigger phrase** (required — helper text: "Say this phrase naturally and Flume will expand it
  automatically")
- **Expansion text** (required, multi-line — the full content to insert)
- Character counters on both fields, enforcing the caps above
- Validation: trigger must be unique (case-insensitive) against other snippet triggers *and* against
  existing dictionary replacement `from` values — block save with an inline error on collision, rather
  than allowing ambiguous runtime behavior
- Save / Cancel; Delete only in edit mode, with a confirmation step before deleting (matches the app's
  general care around destructive actions)

## Edge cases & failure handling

Per Hard Rule #1 in `05-conventions.md` ("never break the dictation path"): snippet matching must never
crash or block the pipeline. Wrap in try/except, log and skip silently on any error — same fail-closed
posture as autolearn and file-tagging.

- Overlapping triggers → resolve by matching the longest trigger first.
- Trigger collides with an existing dictionary replacement `from` → block at save time with a clear
  validation error.
- Very long expansions → capped (proposed 1,000 chars) to avoid paste/inject issues.
- No recursive expansion, ever — a saved expansion is never re-scanned for further triggers.

## Explicitly out of scope for v1

- Team/shared snippets — depends on the org/workspace layer, which doesn't exist yet (see
  `06-roadmap.md` § Team & Organization Layer).
- Per-snippet usage analytics — later add-on, ties to the broader Personal Usage Analytics future item.
- Voice-triggered creation ("save this as a snippet," said aloud) — v1 is settings-screen creation only.
