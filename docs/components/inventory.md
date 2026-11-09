# Inventory and ingestion

## Collector UI and cache update: 9 November 2026

Collection retains exact-printing quantities, search, sort, 20-row pages and
full-inventory totals. Tile inspectors expose guide details; the card-detail page
separates current guides from archived scraper records. Scrapers are retired;
imports no longer generate scraper queries or guessed marketplace URLs. Existing
columns and saved records are retained. Scryfall downloads, enrichment and exact
purchase links remain available. Import and reconciliation
remain separate workflows. Imports now synchronize [quantity lots](performance.md)
once per affected card, using the first previous quantity and final absolute CSV
quantity. Lot updates and observation capture commit with the original import.

Bulk downloads now validate before atomically publishing a generation through the
metadata file. Readers resolve that file while continuing to support the original
fixed-name cache. Failed refreshes retain the previously referenced valid data.
See [pricing](pricing.md) for the refresh, finish and FX contracts. This supersedes
the direct-write limitation recorded in the historical inspection below.

**Scope:** current working tree, 2026-10-18; importer, bulk reader, upload/inventory
routes, models, startup and relevant tests inspected. Human owner: **unknown**.
[Baseline](../README.md#inspection-baseline-and-existing-documentation).

## Purpose and boundary

This component owns imported physical-card rows, CSV parsing and Scryfall enrichment.
It consumes reviewed [goal versions](goals.md) to attach explicit ownership matches;
it does not discover maintained goal membership. [Pricing](pricing.md) owns monetary
conversion; inventory route helpers own search, sort, pagination and inventory totals.

## Entry points and data owners

| Concern | Authority / callers |
| --- | --- |
| Upload and rollback boundary | [routes.upload](../../cardchart/routes.py#L738-L762), [upload.html](../../cardchart/templates/upload.html) |
| CSV contract, identity, upsert and enrichment | [importer.py](../../cardchart/importer.py#L15-L286); `REQUIRED_HEADERS` is the executable header authority; [README](../../README.md#csv-format) is the user format |
| Persisted inventory and legacy snapshots | [Card / PriceSnapshot](../../cardchart/models.py#L9-L48); `Card.scryfall_id` is unique |
| Scryfall download, format, lookup and set catalog | [scryfall_bulk.py](../../cardchart/scryfall_bulk.py#L17-L181); consumers are importer and goal UI/CLI; pricing has its own streaming projection reader |
| Existing-inventory UUID normalization | [ownership.canonical_inventory_scryfall_id](../../cardchart/ownership.py#L6-L15), consumed by goal reconciliation |
| Search, sort, pagination, guide total | [inventory / inventory_card_view / sort_inventory_views](../../cardchart/routes.py#L76-L192), [index.html](../../cardchart/templates/index.html) |
| Reviewed dated snapshots and disposals | [Reconciliation guide](reconciliation.md), [reconciliation.py](../../cardchart/reconciliation.py), [reconciliation_routes.py](../../cardchart/reconciliation_routes.py); uses a separate ledger and exact-printing review |

## Flow and invariants

`import_cards` decodes UTF-8 with BOM support, requires headers, materializes rows,
loads the bulk lookup, upserts each row, links matching goal printings, then commits.
The upload route rolls back on exceptions. Quantities are replaced by imported
values, not incremented. Metadata failure can still import CSV details with warnings;
goal matching requires a canonical ID returned by enrichment.

Bulk lookup is attempted before live requests, by ID then set/collector. Imports of
at least 100 rows request a refresh; smaller imports read the existing cache only.
Bulk failures warn and fall back to live lookups. Live requests retry bounded network,
HTTP and throttling failures; exhausted/not-found enrichment leaves a warning and
CSV-based data. These are existing fallback behaviors, not permission to add new ones.
See [importer](../../cardchart/importer.py#L45-L105) and
[live fetch](../../cardchart/importer.py#L193-L254).

Inventory IDs may be canonical UUIDs, finish-suffixed IDs for another finish of the
same printing, or synthetic `csv:` IDs when identity cannot be resolved. Never send
a synthetic ID to goal matching as a verified UUID. [find_card_for_row](../../cardchart/importer.py#L153-L173)
owns finish collision handling; goal printing records retain canonical identities.

The separate reconciliation workflow stages CSV observations and completed
disposals. It requires reviewed exact printing matches, sets snapshot quantities as
absolute totals, and never deletes cards absent from a snapshot. Disposal counts
are subtracted only when the user confirms they are not already reflected. Applying
also updates linked goal printing quantities while preserving ownership metadata.
See [reconciliation](reconciliation.md) for file limits, identity and repeat safety;
do not fold this ledger behavior into ordinary importer upserts.

Bulk cache and metadata live in ignored `instance/scryfall/`. Refresh fetches the
`default_cards` item and its `jsonl_download_uri`; readers detect gzip JSON Lines or
an existing plain JSON array. The lookup cache is keyed by file mtime; downloads
write data then metadata directly, with no atomic swap or verified recovery protocol.
Do not treat cache contents as membership authority. Format support is observed in
code/tests; the live upstream contract was not reverified in this pass.

## Verification, limits and updates

Run `python -m unittest discover -s tests -p test_scryfall_bulk.py` and
`python -m unittest discover -s tests -p test_goals.py`.
[Bulk tests](../../tests/test_scryfall_bulk.py) cover actual gzip/array parsing,
set catalog and the mocked download interface. [Goal tests](../../tests/test_goals.py)
cover import matching, wrong-printing/finish rejection, enrichment failure warnings,
cross-goal matches, existing routes and inventory search/sort/pagination. A regression
imports both finishes of one printing, then reads actual bulk prices through the
inventory route and checks quantities, totals, sort order and unchanged storage IDs.
These tests
do not verify live rate limits, malformed live JSON handling or every retry branch.
Use [verification](../runbooks/verification.md) before running operational commands.

Inventory price-index requests and valuation reuse
`ownership.canonical_inventory_scryfall_id` to normalize finish-suffixed IDs to UUIDs.
Stored IDs and finishes remain unchanged; synthetic CSV identities stay unpriced.
If identity/CSV/cache contracts change, update this guide, the goals/pricing guide at
the integration boundary, and README's user-facing import notes. Record unresolved
work in the existing backlog. Original rationale for the inventory ID encoding and
an approved cache-recovery procedure remain unknown.
