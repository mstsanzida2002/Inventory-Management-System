# Comment Policy

Governs the multi-session comment hygiene pass (docs/project_memory.md,
"Comment Hygiene Pass" entries). Applies to `frontend/**` and
`config/**`, excluding `frontend/migrations/**` and vendored/minified
static assets (`*.min.js`, `chart.js`). Comments and docstrings only —
this policy never justifies changing a token of actual code; see
`scripts/comment_guard.py` for the mechanical proof that no code moved.

**Revision note (session 2):** the rules below tightened after session
1. Session 1's pilot slice (`frontend/models.py`, `mixins.py`,
`permissions.py`, `decorators.py`, originally committed as `19c151d`)
is retrofitted to the tightened FORM rule in session 2, PHASE 0 —
no `BUG-xx` tag, phase number, or doc-pointer survives in any of the
four files.

## BANNED IN CODE COMMENTS — no exceptions

- `BUG-xx` references — `docs/bugsfound.md` owns these.
- Phase / version / sprint numbers — `docs/project_memory.md` owns these.
- Dates, changelog notes, "was X", "changed from Y", "used to".
- Pointers to `docs/*.md`, ticket IDs, commit hashes, author names.
- ASCII banners and section dividers.
- Narrative, tutorial voice, step numbering.
- Commented-out code, unless it is a documented deliberate fallback —
  ask before deleting one of those.

A code comment states the current reason only. History, cross-
references, and audit trail all live in `docs/bugsfound.md` and
`docs/project_memory.md`, never in the code itself.

## PREFIXES — the entire vocabulary, nothing else

```
# Rule:       business rule the code enforces
# Assumption: units, currency, timezone, ordering, nullability, caller precondition
# Edge:       edge case or failure mode being handled
# Workaround: library quirk or constraint being worked around
# Perf:       deliberate performance decision
# Security:   deliberate security decision
```

JS uses the same six prefixes with `//`. Templates use `{# ... #}`,
single line only.

## FORM — non-negotiable

- ONE line. Never two. Never a paragraph.
- ≤ 80 characters total, including the prefix.
- States the reason only — the code already states the mechanism.
- Present tense. No "we", no hedging, no restating identifiers visible
  on the next line.

## DEDUPLICATION

- One architectural fact is stated ONCE, at the highest scope where it is true (module top or
  class docstring), never repeated at each site that obeys it.
- A site-level comment is justified only where that site DEVIATES from the stated rule.

## NO RESTATEMENT

- A comment must not restate the line or lines below it.
- A comment directly above a conditional must not restate the conditional.
- If deleting the comment loses no information, it was restatement.

## ONE PER CONSTRUCT

- Docstring OR #-comment, never both on the same construct. If both survive, they must state
  different facts. Test: delete one — if nothing is lost, it should not have been there.

## NO SPECULATIVE PLACEMENT

- No comment is written at a site that may not exist after editing. If nothing survives there,
  write nothing.

## SECTION MARKERS — narrow exception

- Applies ONLY to files over 1000 lines. No other file may use these.
- A seventh prefix, `# Section:`, is permitted for this purpose alone.
- One marker per module area, never per function, never per class.
- One line, <= 80 characters. No ASCII rules, no dividers, no blank-line padding beyond one
  blank line either side.
- Names the business area, not the code beneath it: `# Section: Purchase orders` not
  `# Section: PurchaseListCreateView and friends`.
- Where a boundary already carries a `# Rule:` or `# Security:` line that marks it, that line
  stands alone -- do NOT add a marker beside it.
- These are navigation aids. They state no rule and carry no rationale.

## DOCSTRINGS

- Public entry points: one line, ≤ 80 chars, states the contract.
  Nothing more.
- Everything else: none. Delete narrative docstrings outright — do not
  shorten them.

## DENSITY

- At most one comment per ~20 lines of code.
- A file with no non-obvious logic ends with zero comments. That is
  correct, not a gap.
- If the reason will not fit in 80 characters, the comment is not worth
  keeping.

## CELERY-ABSENCE ALLOCATION — decided session 2, binding for sessions 2-5

Seven files carry a Celery-absence note. Criterion: keep one line only
where synchronous execution actually constrains behavior (request-cycle
duration, no retry); delete where the note only explains why something
was never built.

KEEP (one-line `# Assumption:`, applied when that file's own session
comes up):
- `frontend/classification.py` (session 3) — `approve_sale()`/
  `cancel_sale()` block on a live classification run.
- `frontend/forecasting.py` (session 3) — the manual retrain POST blocks.
- `frontend/notifications.py` (session 2, applied this session) —
  `send_mail()` blocks per notification, no retry.
- `frontend/views.py`, `DemandForecastingView.post()` — blocks for a full
  retrain-and-forecast run (views.py itself is out of scope until a
  later session; this note survives the eventual pass on that file).
- `frontend/views.py`, `SlowMovingDeadStockView.post()` — blocks for a
  full classification run.
- `frontend/static/js/async-run-button.js` — the loading spinner reflects
  a real synchronous call, not a simulated one.

DELETE (no behavior constraint — a scope/build decision, not a runtime
fact):
- `frontend/api_views.py`
- `frontend/api_urls.py`

## CALIBRATION — the target compression

  10 lines of phase-numbered prose about DateField and TIME_ZONE
    -> # Workaround: auto_now_add ignores TIME_ZONE; localdate() gives the Dhaka date.
  a paragraph on policy resolution failing closed
    -> # Security: no policy match falls back to ADMIN, never SUPERVISOR or AUTO.
  a paragraph on missing versus zero price in JS
    -> // Edge: missing price leaves the field empty; zero is a different fact.
