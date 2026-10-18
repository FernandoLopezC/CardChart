# Repository guidance

## Start with the change

Use [docs/README.md](docs/README.md) to choose the owning guide. Read that guide,
its relevant decisions, and the source and tests it cites. Use
[README.md](README.md) for setup and [the system map](docs/ARCHITECTURE.md) for
changes spanning components; do not load every document for every task.

| Change | Start here |
| --- | --- |
| Membership, authoring, ownership, progress, Wants List export | [Goals](docs/components/goals.md) |
| CSV ingestion, inventory identity, Scryfall cache | [Inventory and ingestion](docs/components/inventory.md) |
| Guide values, FX, legacy price snapshots | [Pricing](docs/components/pricing.md) |
| Startup, schema, configuration, cross-component work | [Architecture](docs/ARCHITECTURE.md) |
| Checks and documentation-only work | [Verification](docs/runbooks/verification.md) |

## Workflow and constraints

1. Inspect the real implementation and callers before scoping a change. Maintained
   [product direction](docs/product-direction.md) owns intent; source and tests
   establish implementation. Report contradictions instead of silently choosing.
2. Scope the smallest complete change. Never add database migration code or new
   fallback behavior unless explicitly requested. Preserve legacy pricing until
   its removal is approved. Keep source in place unless restructuring is requested.
3. Implement, then run the relevant [checks](docs/runbooks/verification.md).
   Prefer observable behavior through real code; preserve meaningful boundary and
   failure coverage. Do not replace tests with copied implementations or fixture-only
   assertions. Verify upstream contracts before weakening malformed-response tests.
4. Update the owning component guide when contracts, routes, data, setup, or checks
   change. Update product intent only when intent changes. Record consequential
   boundary decisions with provenance in [decisions](docs/decisions/README.md).
5. Use [remaining tasks](docs/remaining-tasks.md) as the only work queue: remove
   completed work and leave concrete continuation steps for incomplete material work.
   Preserve historical handoffs; supersede decisions explicitly.

Keep instructions and documentation concise. A completion handoff must state what
and why, affected components, checks actually performed, decisions/assumptions,
remaining work, risks/blockers, upstream dependencies, and downstream effects.
These are contributor instructions; automatic enforcement is not established.
