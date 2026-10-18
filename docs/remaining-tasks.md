# Remaining tasks

Completed implementation is reflected in the product documentation and code rather than retained here as unfinished work.

## Decide the future of legacy pricing

- **Status:** Pending decision
- **Reason:** Pricing is no longer the primary product direction, but its removal has not been approved.
- **Required work:** Decide whether and when to retire price snapshots, scrapers, and refresh routes.
- **Upstream dependencies:** Product-owner approval and a data-retention decision.
- **Downstream effects:** A future decision may simplify inventory and card-detail views.
- **Risks or constraints:** Existing pricing data and behavior must remain intact until approval.

## Align ownership write paths

- **Status:** Discrepancy found; policy decision required before implementation.
- **Evidence:** [Detailed editor](../cardchart/routes.py#L612-L653) accepts free-form printing fields; quick update and versioned import matching use reviewed versions. [Goals guide](components/goals.md) distinguishes these paths from product intent.
- **Required work:** Confirm whether manual ownership outside reviewed versions is intentional. Add a functional POST test for the chosen policy, then align validation or clarify product intent. Preserve notes, quantities, acquisition dates and existing ownership during any approved change.
- **Upstream dependencies:** Product-owner decision; no validation tightening is part of documentation preparation.
- **Downstream effects:** Ownership/progress and owned-value coverage may change; update the goals guide and product direction together.
- **Risks or constraints:** Positive manual quantities currently count as owned even when guide valuation cannot accept the printing. Inventory reconciliation also lacks independent language data; do not claim it validates inventory language.

## Normalize inventory identities for guide pricing

- **Status:** Implementation gap observed; not changed in documentation preparation.
- **Evidence:** [Finish collision handling](../cardchart/importer.py#L153-L173) creates suffixed IDs, while [inventory valuation](../cardchart/routes.py#L125-L138) passes raw IDs into a UUID-keyed price index. [Pricing guide](components/pricing.md).
- **Required work:** Reproduce an import with two finishes for one UUID followed by an inventory read against a priced bulk record. Add a regression through that real path, then reuse the canonical identity owner where appropriate without changing stored IDs.
- **Upstream dependencies:** Coordinate importer identity and price-index contracts; no schema migration is needed or authorized by this task.
- **Downstream effects:** Previously unavailable inventory values and totals may become priced; update inventory/pricing context and user notes.
- **Risks or constraints:** Preserve finish-specific pricing, quantities and goal matching; never interpret synthetic CSV IDs as verified UUIDs.

## Establish activation recovery expectations

- **Status:** Unverified failure boundary; proposal for follow-up, not an adopted design.
- **Evidence:** [Activation](../cardchart/goal_authoring.py#L148-L185) spans file creation, process registry and DB synchronization with exception cleanup; [current tests](../tests/test_goal_manifests.py) cover success and slug conflict, not crash/concurrent activation recovery.
- **Required work:** Assign an operational owner and establish whether multi-process activation is supported. Define reachable failure scenarios and recovery expectations, then add focused fault/concurrency verification and a sourced ADR if a consistency mechanism changes.
- **Upstream dependencies:** Deployment topology and data/manifest recovery policy are unknown.
- **Downstream effects:** May affect activation, registry refresh and operational procedures; keep candidate review and conflict refusal intact.
- **Risks or constraints:** Current cleanup is best effort, not crash-atomic. Do not add recovery automation or new fallback behavior without explicit scope.
