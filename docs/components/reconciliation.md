# Reconciliation

**Scope:** implemented local CSV review and repeat-import ledger, 2026-10-18.
This guide describes current code; the accountable human owner is unassigned.

## Purpose and boundary

Reconciliation records dated inventory snapshots and completed disposals from
Collectr, Deckcheck, eBay, or a buylist. It changes inventory only after a person
reviews exact printing matches and explicitly selects rows. Collectr and Deckcheck
usually report the same cards: snapshots are absolute counts, never sums, and cards
missing from a snapshot are not deleted. The user confirms whether disposal counts
are already reflected in the selected source inventory.

This workflow is separate from the ordinary inventory importer: it does not infer
printing identity from a name, make a network request during upload, or treat an
export as authoritative without review. See [inventory and ingestion](inventory.md)
for ordinary upsert/import behavior and [goals](goals.md) for goal ownership rules.

## Entry points and data owners

| Concern | Authority |
| --- | --- |
| Upload, mapping, review, apply, history, export, local cache refresh | [reconciliation_routes.py](../../cardchart/reconciliation_routes.py); blueprint `reconciliation`, prefix `/reconcile` |
| CSV validation, identity, preview, duplicate safety, atomic apply | [reconciliation.py](../../cardchart/reconciliation.py): `create_batch`, `map_batch`, `prepare_preview`, `apply_review` |
| Persisted batch and transaction ledger | [models.py](../../cardchart/models.py): `ReconciliationBatch`, `ReconciliationEntry` |
| Browser quantity preview | [reconciliation.js](../../cardchart/static/reconciliation.js) |
| Behavior tests | [test_reconciliation.py](../../tests/test_reconciliation.py), [reconciliation.test.cjs](../../tests/reconciliation.test.cjs) |

## Input and identity contract

Uploads are UTF-8 (BOM accepted), comma-separated CSV, at most 2 MiB and 1,000
non-empty data rows. Headers must be unique and non-empty; each row must match the
header width. Save Excel exports as CSV UTF-8. Source, kind, past-or-current observed
date, and disposal basis are validated. Buylist uploads require a vendor/account
label to namespace references. Blank references may be supplied once on the upload
form and used for rows without an order-reference column.

Column mapping requires quantity and supports name, Scryfall ID, set code, collector
number, finish, language, reference, line/item ID and status. Finish must resolve to
nonfoil, foil or etched; language defaults to English. A disposal with a status
column requires a comma-separated list of completed status values. Without one, the
user confirms all rows are completed. Other statuses, refunds and lots are not
inferred or automatically converted into stock corrections.

Automatic resolution requires a unique exact paper printing and finish, via a
canonical Scryfall ID or the local cached set/collector/language/finish data. Names
and listing titles never identify inventory automatically. Existing inventory
printings can be selected manually. An unmatched new printing requires its exact ID
and finish and an explicit **Update printing matches** step against the local cache.
Upload itself does not refresh Scryfall; the page offers an explicit refresh action.

## Performance integration

The approved [Performance service](performance.md) synchronizes FIFO quantity lots
and captures valid cached guide evidence inside the existing apply transaction.
Repeated and already-reflected disposals do not consume lots twice. Snapshot counts
remain absolute; missing cards are not inferred as disposals. No network request or
new commit boundary is introduced by the history hook.

## Apply, repeat safety and persistence

Snapshots set a chosen printing's quantity to the reviewed total. They do not add
counts from overlapping trackers, delete absent cards, or automatically combine
duplicate rows for one printing; the operator must select one row and enter a
combined total. A repeated identical file/date/printing observation is recognized
from its content hash and skipped, so re-uploading a pre-sale snapshot cannot restore
stock after a disposal. Different files do not establish snapshot staleness, and
the app cannot infer whether a snapshot already includes sales.

Disposals either subtract from current quantity (`unreflected`) or record history
without changing count (`already_reflected`). The event ledger is scoped by source
and buylist vendor/account, transaction reference, and line ID or printing identity.
Unchanged repeats are skipped. Reusing a reference with changed contents, changing
whether line IDs are mapped for a prior reference, or submitting duplicate event
IDs is blocked for review. Multiple distinct sales for one printing apply
cumulatively; a disposal cannot reduce stock below zero.
Historical disposals for an absent cached printing share one zero-stock inventory
row, even when several distinct transactions are recorded together.

Applying claims the review token and commits stock changes, ledger entries, saved
results, and linked goal printing quantities in one database transaction. Existing
manual ownership links and their notes/acquisition metadata are retained while
linked quantities are synchronized. Two new modeled tables are created on startup;
existing table columns are not altered. Raw CSV rows remain in the batch while it is
pending and are cleared after successful apply; mapped rows, preview, ledger and
results remain. Mapping persistence excludes the CSRF token.

The reconciliation blueprint checks a session CSRF token on each POST. The app has
no sign-in or tenant isolation, and this check does not protect other blueprints.
CSV export includes positive-quantity inventory in the established importer column
format and prefixes spreadsheet formula-leading text values to reduce formula
execution when opened in spreadsheet software.

## Verification and open work

Run `python -m unittest discover -s tests -p test_reconciliation.py` and
`node --test tests/reconciliation.test.cjs`; use the full commands in the
[verification runbook](../runbooks/verification.md) for broader changes. Tests
cover staging, exact matching, disposal basis, duplicate/repeat handling, snapshot
totals, goal quantity synchronization, CSRF and export behavior. They use temporary
databases and mocked bulk data; live Scryfall behavior is not exercised.

No real vendor exports are included, so format coverage beyond generic mapped CSVs
is unverified. XLSX/PDF, direct account sync, mixed lots, refund/reversal workflows,
raw upload retention/deletion policy and draft deletion are not implemented or
decided. See [remaining tasks](../remaining-tasks.md#validate-export-formats-and-retention).
Boundary provenance is recorded in [ADR-0003](../decisions/0003-reviewed-reconciliation.md).
