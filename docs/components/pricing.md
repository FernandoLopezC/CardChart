# Guide values and legacy pricing

**Scope:** current working tree, 2026-10-18; price reader/conversion, route aggregates,
scrapers, models and relevant tests inspected. Human owner: **unknown**.
[Baseline](../README.md#inspection-baseline-and-existing-documentation).

## Purpose and boundary

Guide prices are informational Scryfall EUR estimates converted to GBP. Explicit
legacy refresh creates scraper-derived `PriceSnapshot` records independently.
Neither pipeline defines [goal membership](goals.md) or inventory identity.
[Product direction](../product-direction.md) owns pricing intent; the
[legacy-retirement decision](../remaining-tasks.md#decide-the-future-of-legacy-pricing)
remains open.

## Canonical owners and dependencies

| Concern | Source owner |
| --- | --- |
| Price index and cache freshness | [load_scryfall_price_index / build_price_index](../../cardchart/pricing.py#L24-L119), consumes Scryfall bulk data and metadata from [inventory's cache](inventory.md) |
| FX retrieval, validation, UTC-day cache | [load_eur_to_gbp_rate](../../cardchart/pricing.py#L122-L151), Frankfurter ECB EUR/GBP endpoint |
| Finish price, Decimal conversion and cheapest eligible version | [price_for_printing / cheapest_price_for_versions](../../cardchart/pricing.py#L154-L190) |
| Goal owned value and missing cost | [goal_price_summary / owned_card_price / cheapest_missing_card_price](../../cardchart/routes.py#L522-L580) |
| Quantity-adjusted inventory values and full total | [inventory / inventory_card_view](../../cardchart/routes.py#L76-L142) |
| Legacy network refresh and persisted best listing | [refresh_prices / save_best_price](../../cardchart/routes.py#L772-L799), [scrapers.py](../../cardchart/scrapers.py#L14-L86), [PriceSnapshot](../../cardchart/models.py#L39-L48) |

## Invariants and failure behavior

Implemented: the index selects goal UUIDs plus requested inventory IDs from cached
bulk data; it does not refresh Scryfall during page reads. A compact disk index and
process cache use source `updated_at` plus requested-ID coverage. The price reader
separately supports gzip JSON Lines and existing JSON arrays; changing formats must
consider both readers. Invalid bulk content is not uniformly caught by price reads.

Nonfoil uses `eur`; other supported finishes currently use `eur_foil`. Decimal GBP
conversion rounds half-up to pennies. Missing price/rate yields unavailable GBP,
not a zero-valued card. FX network/validation failure returns no rate; yesterday's
rate is not reused. Index and FX files are runtime artifacts under `instance/`.

Goal owned value requires every positive recorded printing to be accepted and priced,
then multiplies each by quantity. Missing cost takes the cheapest priced accepted
version per missing entry. Summaries include priced entries and expose coverage
counts; an empty bucket is zero, a wholly unpriced nonempty bucket is unavailable.
They cover the full checklist, independent of filtering/pagination. Inventory likewise
totals priced rows before filtering/pagination; line value includes quantity, and
unavailable prices sort after priced ones. Templates display these values rather
than recomputing business metrics.

Inventory normalizes stored IDs with
[ownership.canonical_inventory_scryfall_id](../../cardchart/ownership.py#L6-L15)
before requesting the index and calling `price_for_printing`. Finish-suffixed rows
therefore use the canonical UUID's price for their recorded finish without rewriting
stored identities. Synthetic CSV IDs remain unpriced.

Legacy scrapers call eBay/Cardmarket synchronously and persist the lowest parsed
listing for each source. Network errors propagate from refresh; no listings means
no new snapshot. Cardmarket's EUR parser currently feeds the field named
`price_gbp` without FX conversion ([scrape_cardmarket](../../cardchart/scrapers.py#L47-L60));
these snapshots must not be interpreted as the guide pipeline's converted estimates.
Live markup and currency semantics are unverified. Preserve legacy behavior/data
pending its product and retention decision.

## Verification and updates

Run `python -m unittest discover -s tests -p test_pricing.py` and
`python -m unittest discover -s tests -p test_goals.py`.
[Pricing tests](../../tests/test_pricing.py) exercise actual bulk projections,
finish conversion, daily FX caching and restricted cheapest-version selection.
[Route tests](../../tests/test_goals.py) check full goal totals, exact versions,
quantity-adjusted inventory sorting and legacy route availability. The import-to-page
regression uses the real bulk price index to verify both finishes contribute to the
inventory total while an unverified CSV identity remains unavailable. They do not
verify live scrapers or external API compatibility. [Runbook](../runbooks/verification.md).

Update this guide and README/product direction when visible valuation semantics
change; coordinate UUID contract changes with inventory and goal guides. Add a
sourced ADR for a consequential integration/consistency change, and use the existing
backlog for gaps. No live-market or deployment verification is implied by unit tests.
