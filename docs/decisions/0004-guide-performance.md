# ADR-0004: Track remaining inventory against captured guide baselines

- Status: approved for implementation by the user on 9 November 2026.
- Provenance: the implementation-handover pickup request, followed by explicit
  approval of three additive tables, FIFO reductions and first-valid baselines.
- Scope: guide movement, not purchase profit or realised sale returns.

Physical inventory is the only collection Performance population. Goal-only
ownership has no physical allocation identity and is excluded; inventory linked to
multiple goals is counted once. A quantity increase creates a new lot. An absolute
quantity decrease consumes the oldest remaining lots first (FIFO). Repeated imports
and already-reflected disposals do not create or consume quantities again.

Each remaining lot receives its baseline once, at its first valid captured guide
observation. Old inventory begins tracking now; neither Card.created_at nor legacy
scraper prices reconstruct earlier history. Missing price/FX/source evidence leaves
the baseline unknown until a valid observation. Capture retains exact printing and
finish, original EUR text, GBP pennies, bulk timestamp, FX rate and reference/fetch
dates. No new FX or provider fallback is introduced. Etched remains unpriced.

The headline sums `(current GBP guide - baseline GBP guide) * remaining quantity`
over comparable lots. Its percentage divides by their combined baseline value;
zero baseline has no percentage. Missing baseline/current values are excluded from
both sides and coverage is disclosed. Mover filters change only the list.

The chart records portfolio observations, including quantity, coverage and FX
changes. It is separately labelled from since-baseline movement. No synthetic
daily series, historical ownership backfill or unattended scheduling is added.
Explicit guide refresh and quantity writes capture observations; identical latest
evidence/holdings are repeat-safe. Page reads never create history.

Storage adds QuantityLot, GuideObservation and GuideObservationValue only. Existing
tables/columns, collection rows, goal notes/links and legacy snapshots are retained.
Lot updates and captures join the import/reconciliation transaction; helpers do not
commit. Existing startup creates missing tables. Back up the configured SQLite
database before using the new version; recovery restores the backup with the app
stopped. No production database was opened or migrated during implementation.

The implementation and verification owners are [Performance](../components/performance.md)
and the [verification runbook](../runbooks/verification.md). This decision expands
the earlier startup constraint only to these approved additive tables; it does not
authorise column migrations, data deletion or legacy retirement.
