# 0003: Reconcile source observations through explicit review

**Classification:** implementation decision for this change, pending human owner
review. **Recorded:** 2026-10-19. **Implemented:** 2026-10-18–19.
**Accountable human owner:** Unassigned.

## Context

The user requested repeatable reconciliation in the main UI and confirmed that
Collectr and Deckcheck mostly track the same physical cards.
Inventory receives CSV imports that replace quantities, while Collectr, Deckcheck,
marketplace sales, and buylist statements can overlap or describe completed
disposals. Name-based matching or adding overlapping snapshots could silently
misstate stock. The repository has no authenticated user or tenant boundary.

## Implementation choice

The reconciliation blueprint stages bounded UTF-8 CSV data, requires column
mapping, exact printing resolution and row-level review, then atomically records
inventory changes with an idempotency ledger. Snapshots set selected printing
totals and do not delete absent cards. Disposals explicitly declare whether source
counts already reflect them. No name-only automatic match or upload-time network
lookup is performed. The blueprint applies session CSRF validation to its POSTs.

Evidence: `create_batch`, `map_batch`, `prepare_preview`, and `apply_review` in
`cardchart/reconciliation.py`; the `reconciliation` blueprint in
`cardchart/reconciliation_routes.py`; `ReconciliationBatch` and `ReconciliationEntry`
in `cardchart/models.py`; functional boundary coverage in
`tests/test_reconciliation.py` and browser preview coverage in
`tests/reconciliation.test.cjs`. This records the boundary implemented for the
current request; it does not claim earlier architectural history or human approval.

## Consequences and alternatives

Review adds an explicit step before changing inventory, and stable references prevent
unchanged transactions from being deducted twice. Snapshot data remains a dated
observation; different exports cannot reliably reveal staleness or whether sales
were already included. Requiring exact printing identity can leave rows unresolved.
Alternatives such as adding snapshots together, inferring matches from card names,
deleting absent cards, or automatically syncing vendor accounts are not implemented.

## Open questions

The human product/operations owner should review this boundary. Real vendor export
fixtures, raw CSV retention/deletion, pending-batch cleanup and support for refunds,
reversals, lots or non-CSV formats remain open; see the
[reconciliation guide](../components/reconciliation.md) and
[remaining tasks](../remaining-tasks.md#validate-export-formats-and-retention).
