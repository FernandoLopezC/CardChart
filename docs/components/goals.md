# Goals and ownership

**Scope:** current working tree, 2026-10-18; parser, registry, synchronization,
authoring/CLI, ownership, routes, relevant models/tests and sampled UI inspected.
Human owner: **unknown**. [Baseline](../README.md#inspection-baseline-and-existing-documentation).

## Purpose and boundary

This component owns curated desired membership and its projection into a persistent
checklist, plus owned-printing records and progress. Imported inventory remains a
separate record system; guide-price conversion belongs to [pricing](pricing.md).
[Product direction](../product-direction.md) owns intent, and
[goal manifest authoring](../goal-manifests.md) remains the schema and authoring
workflow reference. Do not duplicate the schema or checklist data here.

## Entry points and canonical owners

| Concern | Source authority / callers |
| --- | --- |
| Membership, versions, purchase defaults | [Reviewed manifests](../../cardchart/goals/); [parser and typed definitions](../../cardchart/goal_definitions.py#L22-L350) validate shape and identities |
| Loading and runtime lookup | [load_goal_manifests](../../cardchart/goal_definitions.py#L81-L97), [registry access](../../cardchart/goal_definitions.py#L396-L438) |
| Preview, draft, review, activation | [goal_authoring.py](../../cardchart/goal_authoring.py#L57-L229); [UI routes](../../cardchart/routes.py#L197-L413), [CLI](../../cardchart/goal_cli.py#L24-L184) |
| Checklist upsert / existing inventory reconciliation | [synchronize_goals](../../cardchart/goal_definitions.py#L441-L477) calls [reconcile_goal_collection](../../cardchart/ownership.py#L18-L67) |
| New CSV ownership matches | [importer.match_goal_printings / goal_card_accepts_printing](../../cardchart/importer.py#L107-L150); coordinate changes with [inventory](inventory.md) |
| Ownership identity and progress | [models.py](../../cardchart/models.py#L51-L136): goal slug, per-goal stable key, printing UUID/finish/language, positive quantity |
| Checklist, edits and export | [goal routes](../../cardchart/routes.py#L416-L731); [goal_detail.html](../../cardchart/templates/goal_detail.html), [edit_goal_card.html](../../cardchart/templates/edit_goal_card.html) |
| Authoring browser interactions | [goal_authoring.js](../../cardchart/static/goal_authoring.js), [new_goal.html](../../cardchart/templates/new_goal.html), [review_goal.html](../../cardchart/templates/review_goal.html) |

## Data, invariants and failure behavior

Implemented: startup parses all maintained manifests before synchronization. Stable
keys drive upserts; removed manifest entries are not deleted from the DB. Ownership
links already present are preserved by synchronization. Membership is not inferred
from names or all cards of a set ([ADR-0001](../decisions/0001-reviewed-membership.md)).

Authoring uses local bulk metadata, groups candidate printings by Oracle ID, and
preserves submitted selected entry keys. Preview writes no draft. Activation checks
bulk metadata and slug/file conflicts, exclusively creates a manifest, updates the
process registry, then synchronizes one goal. On caught exceptions it rolls back the
session and attempts registry/file cleanup. These are separate persistence steps,
not crash-atomic or cross-process coordination. Drafts/candidates under `instance/`
are inactive; activation needs write access to the maintained manifest directory.
CLI review before moving a candidate is a human procedure; startup cannot prove that
review occurred and checks structure rather than bulk metadata.

Reconciliation indexes the first positive-quantity inventory row per canonical UUID
and finish, including finish-suffixed IDs. It does not aggregate duplicate rows;
inventory has no language field, so the new ownership link takes manifest language.
Import matching additionally compares enriched language for versioned entries.
One inventory row may satisfy several goals; ownership is not reserved or deducted.

Quick update restricts choices to reviewed versions, zeroes other printing quantities
when selecting owned, and deletes all ownership links when selecting missing.
**Difference from intent:** the detailed editor accepts free-form identities and
does not validate them against the manifest; `is_owned` checks positive quantity,
not acceptance. Accepted-printing restrictions therefore do not cover every write
path. See [ownership continuation](../remaining-tasks.md#align-ownership-write-paths).

The Wants List route exports all missing entries, independent of filters/pages,
using reviewed version/expansion mappings; it returns 404 when a mapping is absent.
It makes no marketplace API call. Goal detail shows 20 entries per page while
progress and price summary use the full checklist; aggregates are owned by models
and route helpers respectively, not templates.

## Verification and context updates

Run `python -m unittest discover -s tests -p 'test_goal*.py'` from the repo root
([environment and full checks](../runbooks/verification.md)). Existing tests exercise
the real parser, synchronization, importer, test client and CLI: manifest rejection,
bulk metadata validation, preview, reviewed activation, idempotence, preserved
ownership, rejected finishes, cross-goal matching, pagination and exact export.
Sources: [test_goal_manifests.py](../../tests/test_goal_manifests.py),
[test_goals.py](../../tests/test_goals.py). They do not establish browser event
behavior or crash/concurrent activation recovery.

When changing contracts, update this guide and the existing manifest guide; update
product direction for intent changes, relevant ADRs for consequential boundaries,
and the backlog for unresolved work. Open questions: human ownership, detailed-editor
validation policy, and activation recovery expectations. Do not silently enforce a
new policy as part of documentation work.
