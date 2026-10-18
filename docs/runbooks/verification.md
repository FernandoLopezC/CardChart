# Verify a change

Run from the repository root with the environment from [setup](../../README.md#setup).
The commands below were exercised on the 2026-10-18 working tree; they are a manual
workflow. No CI enforcement or production readiness is claimed.

## Inspect → scope → implement → verify → update context

Choose the [owning component](../README.md), inspect callers, models and tests,
then scope the observable behavior to preserve/change. Use the actual parser,
service, database or Flask test client rather than reproducing business logic in a
test. Keep meaningful security, payment, tenancy, concurrency or migration coverage
if such paths are introduced; their existence is not implied for this local app.
Test dependency failures only where the real code can reach them, and verify actual
SDK/API response contracts before removing malformed-output coverage (including
truncation, refusals and optional fields when applicable).

## Functional checks

```sh
python -m unittest discover -s tests
python -m compileall -q cardchart
git diff --check
```

Focused suites use `python -m unittest discover -s tests -p test_goals.py`, replacing
the pattern with `test_goal_manifests.py`, `test_scryfall_bulk.py`, `test_pricing.py`
or `test_startup.py` as routed by the component guide. Run the full suite for shared
models, identity, synchronization or startup changes. `compileall` writes ignored
bytecode; it is a syntax check, not behavioral verification.

The tests use in-memory/temporary databases, temporary candidate/manifest files and
mocked external responses. Inspect their setup when modifying them: `db.drop_all()`
is safe only against the isolated test DB. Do not substitute a real collection DB.
The suite does not verify live API contracts, scraper markup or browser JavaScript.

On this Windows sandbox, the default temp directory denied file writes. The same
suite passed using the existing venv and a workspace-local temp directory:

```powershell
New-Item -ItemType Directory -Force .venv/context-check-tmp | Out-Null
$env:TEMP = (Resolve-Path .venv/context-check-tmp).Path
$env:TMP = $env:TEMP
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

Set these only in the check's shell process. A pre-existing SQLAlchemy `Query.get()`
deprecation warning is emitted by route tests. The 45-test suite passed after the
temp-path correction; the initial permission failures were not application failures.

## Documentation checks

Check changed Markdown's relative links, heading fragments, cited source paths and
line ranges against the current working tree. Check `git diff --check` and include
new files in whitespace review: Git diff omits untracked content. Use
`git status --short --untracked-files=all` and `git check-ignore` to confirm new docs
are visible. Visibility does not mean staged or committed; preserve unrelated work.
Rerun the three navigation walkthroughs below when routing changes. No repository
link checker or automatic drift detector is installed by this preparation.

## Three representative change walkthroughs

| Request | Route to owner and constraints | Verification | Durable context to update |
| --- | --- | --- | --- |
| Add a curated subset and its export defaults | AGENTS → [goals](../components/goals.md) → [manifest workflow](../goal-manifests.md) → parser/authoring and reviewed JSON. Preserve explicit UUID/finish/language and stable keys; candidates remain inactive until activation or a file move; CLI review is a human procedure. No implicit set-wide membership. [ADR-0001](../decisions/0001-reviewed-membership.md). | Manifest + goal suites; bulk-backed validation in a deliberately configured local environment after review. | Manifest data and workflow guide if its contract changes; product intent only if changed. |
| Fix imported foil ownership matching | AGENTS → [inventory](../components/inventory.md) → importer identity/matching → [goals](../components/goals.md) reconciliation. Distinguish canonical UUID from finish-suffixed storage ID; preserve existing ownership and cross-goal matches. | Goal suite's import, rejected-printing/finish, suffixed-ID and preservation cases; full suite for identity changes. | Both guides if identity semantics change; resolve the corresponding backlog work only when verified. |
| Change missing-cost calculation or FX failure behavior | AGENTS → [pricing](../components/pricing.md) → route aggregate versus conversion/cache owner. Use full checklist and accepted versions, expose unavailable coverage, keep legacy snapshots separate; new fallback requires explicit request. | Pricing + goal suites: cheapest accepted version, quantities, totals independent of page/filter, failure path through real implementation. | Pricing guide, user pricing notes/intent, and a decision record for a consequential integration/failure-policy change. |

These walkthroughs were checked against the cited source and tests during preparation;
they are navigation checks, not claims that those hypothetical changes were implemented.

## Operational commands have side effects

`flask --app cardchart ...` loads the app and can create tables and synchronize goals
before the requested command executes. `goals refresh-bulk` also downloads/writes the
cache; authoring writes candidates/drafts; activation writes maintained manifests
and DB state. They are not documentation checks. Existing procedures remain in
[goal manifest authoring](../goal-manifests.md); use an intentional local data setup.
No production DB command, live download, activation or recovery drill was run here.

Close work by updating the owning guide, relevant decision provenance and the
[single work queue](../remaining-tasks.md). Include actual checks, assumptions,
dependencies, downstream effects and incomplete continuation steps in the handoff.
