# Performance

## Contract and ownership

[performance.py](../../cardchart/performance.py) owns quantity-lot synchronization,
observation capture, remaining-lot movement and historical portfolio queries.
[models.py](../../cardchart/models.py) defines the three new tables.
[ADR-0004](../decisions/0004-guide-performance.md) records user-approved semantics.
No goal-only ownership or legacy PriceSnapshot value enters collection Performance.

CSV quantities remain absolute totals. Reviewed reconciliation retains its existing
repeat-safe ledger and disposal basis. Their quantity changes synchronize lots and
capture cached guide evidence in the same transaction. The services never commit.
An explicit guide refresh captures an observation after bulk/FX success; a capture
failure reports that history was not saved rather than claiming full success.
No page read, background schedule or inferred acquisition date creates history.

Each addition has its own baseline. Reductions use FIFO. Baselines are assigned only
with exact-finish GBP and valid source/FX evidence, then remain fixed. Unknown data
is excluded from both sides of comparisons. GBP movement includes FX movement;
historical EUR and applied FX evidence remain attached to the original observation.

Overview and Performance share the observed-portfolio chart. It includes quantity
and coverage changes, with an inspected date/value/coverage readout. Hover/tap and
arrows/Home/End inspect snapshots; no range slider exists. No observations and one
observation have explicit states; unavailable observations break the line. Remaining
holdings movement uses fixed lot baselines and a combined-baseline percentage.
The mover filter does not alter headline scope or the historical chart.

## Backup and recovery

The new version creates only missing tables through existing startup. It does not
alter existing columns or backfill historical prices. Before starting it against a
real collection, stop the app and copy the configured SQLite database to a separate
backup. If another SQLite connection remains active, use SQLite's backup API rather
than copying an active database file. Keep that backup outside Git.

To recover, stop the app and restore the complete backup, preserving the current
database separately for diagnosis. Do not drop history tables or manually change
lot quantities. Startup may create the new empty tables again, while existing
collection records remain. The tests exercise SQLite backup/reopen on isolated
data; no production migration or restore was run.

## Verification and limits

Run `python -m unittest discover -s tests -p test_performance.py`, the import/goal
and reconciliation tests, then the complete [offline suite](../runbooks/verification.md).
Tests use real services and temporary/in-memory SQLite. They cover weighted lot
movement, additions, FIFO reductions, repeated writes, missing evidence, zero
baseline, atomic rollback and persistence of existing records.

Actual chart observations start with this version. They cannot reconstruct earlier
holdings or purchase profit. No lot-selection UI, retrospective disposal correction,
provider replacement, scheduled refresh or live-market pricing is introduced.
