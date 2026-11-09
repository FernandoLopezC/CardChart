# Guide prices, goal drops and archived checks

## Sources and boundaries

Current values use exact-printing Scryfall EUR bulk guides converted to GBP with
an ECB reference rate through Frankfurter. They are estimates, excluding shipping,
fees and condition adjustments. Unsupported etched and unknown finishes remain
unavailable. Legacy eBay/Cardmarket scrapers and their refresh route are retired.
Saved PriceSnapshot records remain readable under Archived price checks on card
detail. Legacy Cardmarket currency remains uncertain and never enters GBP guides,
goal comparisons or collection Performance.

Scryfall downloads remain available through **Refresh guides**, the existing bulk
refresh actions and `flask --app cardchart goals refresh-bulk`. CLI downloads do not
capture goal-price history; Refresh guides does that after a download.

## Owners

| Concern | Source |
| --- | --- |
| Streaming index, exact-finish prices, FX and freshness | [pricing.py](../../cardchart/pricing.py) |
| Validated atomic bulk publication | [scryfall_bulk.py](../../cardchart/scryfall_bulk.py) |
| Goal-price capture and comparison | [goal_prices.py](../../cardchart/goal_prices.py) |
| Refresh transaction, goal totals, filters and views | [routes.py](../../cardchart/routes.py) |
| GoalPriceObservation and retained PriceSnapshot | [models.py](../../cardchart/models.py) |
| Physical-inventory lots and history | [Performance](performance.md) |

## Guide invariants

Only nonfoil uses `eur` and foil uses `eur_foil`. Prices must be finite and
nonnegative, FX rates finite and positive, and source/FX dates valid. Zero is a
valid price. Decimal conversion rounds half-up to pennies. Missing values stay
unavailable; no yesterday-rate or alternate-provider fallback is introduced.

Downloads validate complete gzip JSON Lines or JSON arrays before publication.
Content-addressed generation files are published through one atomic metadata-pointer
replacement. Failed publication preserves the previously referenced cache. Original
fixed-name caches remain readable. Old generations remain on disk for recovery.
The derived index is keyed by generation and mtime. Pages do not download bulk data.
Source data older than 48 hours is labelled stale.

Goal owned value uses accepted positive printing quantities. Missing cost uses the
cheapest priced accepted version for each missing card. Totals cover the complete
goal regardless of filters or pagination. Inventory totals use canonical UUID,
finish and quantity; overlapping goal totals never form collection value. Empty
buckets are zero; wholly unpriced nonempty buckets are unavailable. Partial coverage
is disclosed. [Goals](goals.md) owns acceptance and preservation of unaccepted rows.

## Goal price-drop comparisons

The user selected previous successful guide refresh and a minimum GBP 0.01 decrease.
`record_goal_prices` captures all maintained accepted versions in one additional
GoalPriceObservation table. Each row retains source timestamp, FX rate/date, captured
GBP by UUID/finish and capture time. Startup creates the missing table; no existing
columns or rows are changed. Back up the configured database before startup.

Capture joins the collection observation transaction in `POST /guides/refresh`.
No page read, import, or background task creates goal-price history. Invalid source
or missing current FX cannot establish a comparison. A failed database write rolls
back both histories and reports failure; published bulk data may already be newer.
Identical source, FX and prices do not append a snapshot or clear existing flags.

Compare the latest two distinct captures for the same UUID and finish. Flag only
currently missing cards with a decrease of at least GBP 0.01 per copy. Never compare
one version's old price against another version's new price. Unknown prior/current
values do not count as zero. New versions need two comparable captures. GBP movement
can include FX. A zero current price can represent a 100% decrease; a zero previous
price cannot generate a drop.

Display requires the current source/FX evidence and price to match the latest
capture. A separate bulk download or changed FX prompts Refresh guides instead of
showing a comparison against different current data. Cards filters to matching
entries; Binder keeps pocket positions and dims only nonmatching artwork. Drop
counts cover the full goal. Inspectors identify each version and show old/current
GBP, decrease and percentage, with the current exact marketplace link where present.

This is an in-app signal, not live offers or purchase profit. No notifications,
scheduler, paid data source, schema migration or guessed history is added.
[ADR-0005](../decisions/0005-goal-price-drops.md) records the decision and preservation
boundary; [ADR-0004](../decisions/0004-guide-performance.md) still owns inventory history.

## Verification

Run `python -m unittest discover -s tests -p test_goal_price_drops.py`,
`python -m unittest discover -s tests -p test_ownership_editor.py`, pricing/goal/bulk
checks, then the complete [offline suite](../runbooks/verification.md).
Tests use real services, temporary caches and isolated SQLite. They cover exact
versions, unchanged refreshes, unavailable evidence, zero prices, FX movement,
transaction rollback, filters, retained records and retired endpoints.
Live-provider contracts were not changed by this feature.
