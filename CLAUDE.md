# Verbal — Claude Code project instructions

Verbal is a Wispr-Flow-style voice-dictation product: a **macOS/Windows desktop app** (`whisperflow/`,
Python) and an **iOS + Android app** (`verbal-mobile/`, Expo/React Native — ONE codebase for both mobile OSes,
with native voice keyboards in Swift and Kotlin), sharing one **Supabase** backend.

## Read `context/` first

`context/*.md` is the curated, up-to-date knowledge base (product, architecture, features, data model,
conventions). Read the relevant file before working in an area — it's faster and more accurate than
re-deriving from the tree, and it lists the dead/legacy code to ignore.

## KEEP `context/` IN SYNC (required)

The `context/` docs are synced into a Claude project via GitHub and must always reflect reality.
**Whenever you make a change that contradicts or extends anything in `context/`, update the relevant
`context/` file(s) in the SAME change** — this is part of "done", not optional:

- New feature → `context/03-features.md` + the matrix in `context/01-product.md` (+ `04`/`05` if it touches
  data/schema or establishes a rule).
- Changed behavior/architecture → `context/02-architecture.md` and the affected `03`/`04` section.
- New gotcha / fixed bug / design token → `context/05-conventions.md`.
- Retired code → the dead/legacy list in `context/05-conventions.md`.
- New live-DB-only Supabase column → `context/04-data-model.md` §Schema gaps.

If a change would make any statement in `context/` false, it is not finished until the doc is corrected.
On request **"refresh context"**, re-derive all five docs from the current codebase.

## Verification (before calling a change done)

- Desktop: `cd whisperflow && .venv/bin/python -m py_compile app/<file>.py && .venv/bin/python -c "import app.main"`.
  For dashboard/widget JS changes, `node --check` each rendered `<script>` block (the JS lives in Python
  strings — see `context/05-conventions.md` for the single-vs-double backslash rule). Run
  `autolearn_fixtures.py` / `qa_filetags_fixtures.py` if those areas are touched.
- Mobile: `cd verbal-mobile && npx tsc --noEmit`.
  Native config is **generated, never hand-edited**: `ios/` and `android/` are gitignored and produced by
  `expo prebuild` from `app.json` + `plugins/withFlumeKeyboard.js` (Android IME) + `targets/keyboard/`
  (iOS extension). If you touch any of those inputs, run `npx expo prebuild -p android --clean --no-install`
  (and `-p ios` on a Mac) and confirm the plugin output landed — see `context/02-architecture.md` §Mobile stack.
- Peripheral features must **fail closed** and never break the recording→transcribe→inject path.

## Conventions

See `context/05-conventions.md` for the full list (atomic config writes, main-thread WKWebView discipline,
AX/Electron accessibility, Groq 896-char prompt cap, non-activating panels, the Flume design system:
Geist for UI / JetBrains Mono for numerics-and-meta, near-black base + cream/sage/plum pastels).
