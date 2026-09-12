# Comment Policy

Governs the multi-session comment hygiene pass (docs/project_memory.md,
"Comment Hygiene Pass" entries). Applies to `frontend/**` and
`config/**`, excluding `frontend/migrations/**` and vendored/minified
static assets (`*.min.js`, `chart.js`). Comments and docstrings only —
this policy never justifies changing a token of actual code; see
`scripts/comment_guard.py` for the mechanical proof that no code moved.

## DELETE

- Narrative and step-by-step comments ("Step 1", "now we...", anything
  that reads as a tutorial rather than a reason).
- Anything that restates the line(s) below it.
- Development history, phase references (`Phase 8.99c`, `§4a`, etc.)
  and changelog notes ("was `X`, changed to `Y`") **once the underlying
  reason is preserved on its own line**. Phase numbers always go — they
  are never kept for their own sake.
- Stale or dead TODO/FIXME markers (none found in `frontend/` as of this
  pass — if one turns up, delete it here, not as an IOU carried forward).
- Commented-out code, unless it is a documented deliberate fallback —
  ask before deleting one of those (none found in `frontend/` as of this
  pass).
- ASCII banners and section dividers (`# ---- X ----`, `/* ==== */`,
  `{# ---- #}`) in every file, **models.py's per-model dividers
  included** — class/def statements are the structure; a divider on top
  of them is redundant.

## Exception — BUG-xx references survive inside a kept comment

A `BUG-xx` tag is not history for its own sake — `docs/bugsfound.md` is
an append-only audit log, and the cross-reference is the point. Where a
guard, retry, coercion, or edge-case branch exists in the code
*specifically because of* a past bug, keep the `BUG-xx` tag inside the
`# Workaround:` (or `# Edge:`) line that survives. Rule of thumb: if
deleting the tag would make the guard look arbitrary, keep it. Phase
numbers attached to the same sentence still go; the BUG-xx tag does not.

Correct: `# Workaround: retry-on-IntegrityError for auto-generated SKUs only (BUG-87).`
Wrong (phase noise kept): `# Phase 8.99 workaround for BUG-87: retry on IntegrityError.`
Wrong (tag dropped): `# Retry on IntegrityError for auto-generated SKUs.`

## KEEP OR WRITE (only when the reason is not obvious from the code)

- `# Rule:`        — business rule, with the REQ number where one exists.
- `# Assumption:`  — units, currency (BDT ৳), Asia/Dhaka tz, ordering,
  nullability, caller guarantees.
- `# Edge:`        — edge case or failure mode being handled.
- `# Workaround:`  — the quirk being worked around, plus a BUG-xx
  reference if one exists (see exception above).
- `# Perf:`        — deliberate performance decision (pagination,
  query-count, caching).
- `# Security:`    — deliberate security decision (fail-closed,
  authorization boundary).

These six prefixes are the entire vocabulary. No other tags.

### The Celery-absence note — one canonical statement, not seven echoes

This project runs no Celery (or any task queue). That fact is true
everywhere but only *behaviourally load-bearing* in a few places. Write
the full note only where synchronous execution actually constrains
something real — request-cycle duration, no retry-on-failure, no
`.delay()` to fall back on:

`# Assumption: runs synchronously in-request (no Celery/.delay()) — caller blocks for the full duration, no automatic retry.`

Everywhere else the fact is true but not load-bearing for that
particular line, delete the restatement rather than repeat it.

## FORM

- One line preferred, two maximum, ≤ 100 chars per line.
- Placed on the line above the construct; inline trailing comments only
  if ≤ 40 chars.
- Present tense, no hedging, no "we", no restating identifiers.
- Density cap: at most one comment per ~15 lines of code; a file with
  no non-obvious logic ends with zero comments — that is a correct
  outcome, not a gap.
- Public service functions may keep a ONE-LINE docstring stating the
  contract; private helpers get none unless the contract is surprising.
