# ADR-0005: Retire scrapers and compare missing-card guides

- Recorded: 9 November 2026.
- Status: implemented; feature acceptance remains unconfirmed.
- Provenance: user requested scraper retirement while retaining Scryfall downloads,
  agreed to ownership/valuation alignment, and requested goal price-drop flags.
  The user selected comparison with the previous successful guide refresh, using
  exact printing/finish and a minimum £0.01 decrease.

Remove scraper code, its refresh route and action, and import-time scraper queries.
Keep PriceSnapshot rows, model columns and read-only card-detail archive. Preserve
Scryfall bulk downloads, existing refresh options, exact purchase links and CSV flows.
This supersedes the earlier requirement to retain active legacy scraper behavior;
it does not authorize deleting archived pricing data.

Maintained goal progress and value count only positive ownership records matching
reviewed UUID, finish and language, using one shared acceptance check. Existing
unaccepted rows remain stored and labelled for review. Detailed editing selects a
reviewed version and validates linked inventory; edits preserve other records.
Explicit quick-save/Missing consequences remain disclosed and unchanged.

Add one GoalPriceObservation table through existing missing-table startup. Store
source timestamp, FX rate/date, captured GBP per UUID/finish and recording time.
Existing Performance observations require physical inventory and cannot represent
missing cards. Reusing them would contaminate portfolio history. No existing table
columns are changed, and no historical prices or holdings are backfilled.

Capture all reviewed goal versions in the guide-refresh database transaction with
collection history. Compare the latest two distinct captures; identical source,
FX and prices do not clear flags. Only currently missing cards with comparable
prices can be flagged. New versions or missing values need their own comparison.
Only show flags when current source/FX evidence and current price match the captured
values. Failed history writes roll back both histories. GBP movement includes FX.

This is an in-app guide comparison, not a sale offer or notification service. No
scheduler, paid provider, fallback conversion or threshold setting is added. CLI
bulk downloads remain downloads; Refresh guides captures the comparison afterwards.
Back up the configured database before startup; recovery uses the existing complete
database backup procedure. No production database was opened during implementation.

Owners: [Goals](../components/goals.md), [Pricing](../components/pricing.md), and
[Verification](../runbooks/verification.md). This extends the additive storage scope
of [ADR-0004](0004-guide-performance.md) only for requested goal price comparisons.
