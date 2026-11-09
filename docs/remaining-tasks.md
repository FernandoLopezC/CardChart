# Remaining tasks

Completed implementation is reflected in the product documentation and code rather than retained here as unfinished work.

## Implement the preferred UI and free GBP pricing after planning

- **Status:** The preferred mobile/goal and distinctive chart studies are complete, including hover inspection without a slider. The user requested an implementation handover on 9 November 2026. Production implementation has not started; history and migration decisions remain open.
- **Direction:** [Design guidance](../DESIGN.md) adapts PP Scheduling's reference-based process to the user's Collectr screenshots. Mobile is a priority. Binder means a view within existing goals, not separate named groups.
- **Review material:** [Performance study](../artifacts/design-review-v3/cardchart-performance.html), based on the preferred [mobile and goal study](../artifacts/design-review-v2/cardchart-mobile-binders.html). Values, ownership and starting prices are illustrative; controls do not save collection changes.
- **Continuation:** Pick up from the [implementation handover](implementation-handover.md), which records the current tree, source map, pricing options, acceptance criteria and full-stop command. First prepare the concrete plan and resolve history/lot/FX/disposal and migration gates. Then implement shared UI, current-guide refresh/finish fixes and agreed Performance tracking. Verify provider coverage and permitted reuse before integration.
- **Boundaries:** Preserve exact accepted printings, multi-printing ownership, full-scope totals, export and reconciliation review. Guide refresh currently differs from legacy scraper refresh; EUR legacy values and etched/foil semantics need resolution in the pricing scope.
- **Dependencies and effects:** The next implementation affects the base shell, inventory, goals and pricing presentation. No new binder database model, migration, paid feed or legacy-data retirement is approved.

## Decide the future of legacy pricing

- **Status:** Pending decision
- **Reason:** Pricing is no longer the primary product direction, but its removal has not been approved.
- **Required work:** Decide whether and when to retire price snapshots, scrapers, and refresh routes.
- **Upstream dependencies:** Product-owner approval and a data-retention decision.
- **Downstream effects:** A future decision may simplify inventory and card-detail views.
- **Risks or constraints:** Existing pricing data and behavior must remain intact until approval.

## Align ownership write paths

- **Status:** Discrepancy found; policy decision required before implementation.
- **Evidence:** [Detailed editor](../cardchart/routes.py#L616-L657) accepts free-form printing fields; quick update and versioned import matching use reviewed versions. [Goals guide](components/goals.md) distinguishes these paths from product intent.
- **Required work:** Confirm whether manual ownership outside reviewed versions is intentional. Add a functional POST test for the chosen policy, then align validation or clarify product intent. Preserve notes, quantities, acquisition dates and existing ownership during any approved change.
- **Upstream dependencies:** Product-owner decision; no validation tightening is part of documentation preparation.
- **Downstream effects:** Ownership/progress and owned-value coverage may change; update the goals guide and product direction together.
- **Risks or constraints:** Positive manual quantities currently count as owned even when guide valuation cannot accept the printing. Inventory reconciliation also lacks independent language data; do not claim it validates inventory language.

## Establish activation recovery expectations

- **Status:** Unverified failure boundary; proposal for follow-up, not an adopted design.
- **Evidence:** [Activation](../cardchart/goal_authoring.py#L148-L185) spans file creation, process registry and DB synchronization with exception cleanup; [current tests](../tests/test_goal_manifests.py) cover success and slug conflict, not crash/concurrent activation recovery.
- **Required work:** Assign an operational owner and establish whether multi-process activation is supported. Define reachable failure scenarios and recovery expectations, then add focused fault/concurrency verification and a sourced ADR if a consistency mechanism changes.
- **Upstream dependencies:** Deployment topology and data/manifest recovery policy are unknown.
- **Downstream effects:** May affect activation, registry refresh and operational procedures; keep candidate review and conflict refusal intact.
- **Risks or constraints:** Current cleanup is best effort, not crash-atomic. Do not add recovery automation or new fallback behavior without explicit scope.

## Validate export formats and retention

- **Status:** Follow-up required; generic mapped CSV workflow is implemented.
- **Evidence:** [Reconciliation guide](components/reconciliation.md) describes current UTF-8 comma-CSV input, exact-printing review, idempotent transaction ledger, and temporary raw-row persistence. No real vendor export fixtures or retention policy were available during implementation.
- **Required work:** Obtain representative, non-sensitive Collectr, Deckcheck, marketplace and buylist exports; add regression fixtures for supported headers and malformed rows. Decide how long unapplied raw uploads and stale drafts are retained and whether operators need a deletion action.
- **Upstream dependencies:** Product/operations owner and access to safely anonymized source exports.
- **Downstream effects:** May change mapping suggestions, user instructions and data-retention behavior; update reconciliation docs and tests with any adopted formats or policy.
- **Risks or constraints:** Do not claim vendor-specific format compatibility from generic column mapping. XLSX/PDF, direct account sync, mixed lots, refund/reversal handling, and cross-file snapshot staleness detection are not implemented.
