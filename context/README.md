# Verbal — Project Context

This folder is the **living source of truth** about the Verbal product for AI-assisted work
(chat research, PRDs, scoping, implementation review). It is synced into a Claude project via GitHub, so
these files must always reflect the real code.

## The documents

| File | Read it for |
|---|---|
| `01-product.md` | What Verbal is, platforms, the feature availability matrix, glossary |
| `02-architecture.md` | How the system fits together — desktop, mobile, backend, the WKWebView bridge, data flow |
| `03-features.md` | Per-feature deep dive (desktop + mobile impl, backend, status, limitations) |
| `04-data-model.md` | Supabase schema, storage, data shapes, auth flows, sync model, security, schema gaps |
| `05-conventions.md` | Hard-won rules & gotchas, the Flume design system, dead/legacy code to ignore |

Level of abstraction: architecture + feature-intent + data contracts (stable), with **file/function
references** for drill-down rather than pasted code (code goes stale; a pointer doesn't).

## MAINTENANCE CONTRACT (must follow)

**These docs are only useful if they stay true. Any change to the codebase that contradicts or extends
what's written here MUST update the relevant `context/` file(s) in the same change.**

Concretely:
- **New feature** → add a section to `03-features.md` and a row to the `01-product.md` matrix; if it adds
  a table/column/bucket or data shape, update `04-data-model.md`; if it establishes a new rule/gotcha or
  design token, update `05-conventions.md`.
- **Changed behavior / architecture** → update `02-architecture.md` and the relevant `03`/`04` section so
  nothing here contradicts the code.
- **New hard-won lesson or fixed bug** → record the rule in `05-conventions.md` so it isn't reintroduced.
- **Retired/dead code** → move it to the "dead/legacy" list in `05-conventions.md`.
- **New schema column that lives only in the live Supabase DB** → record it in `04-data-model.md` §Schema gaps.

If a change would make any statement in `context/` false, the change is **not done** until the doc is
updated. For a broad resync, ask Claude Code to **"refresh context"** — it re-derives all five docs from
the current codebase.

(This contract is also enforced for Claude Code via the repo-root `CLAUDE.md`.)
