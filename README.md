# CardChart

CardChart is a small Flask app for tracking curated Magic: The Gathering collection goals and imported physical cards.

It keeps desired cards visible even when they are missing and associates exact owned printings with each checklist entry. CSV import uses Scryfall IDs and can explicitly match accepted goal printings. Existing UK-focused pricing tools remain available as legacy inventory behavior.

The initial maintained goal manifests include 40 Middle-earth Classic Artist checklist entries and 65 Japanese Mystical Archive entries. Additional reviewed manifests created through the wizard load through the same registry. Each entry accepts only its verified Scryfall printing UUIDs and finishes, including paired special-foil printings where applicable.

See [product direction](docs/product-direction.md) for product and data-model intent and [remaining tasks](docs/remaining-tasks.md) for genuine blockers and decisions.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
flask --app cardchart run
```

Open http://127.0.0.1:5000.

On startup, CardChart creates the configured database when absent, adds any missing modeled tables, and synchronizes the curated goal definitions. The `flask --app cardchart init-db` command remains available as an explicit readiness check. Startup does not modify existing table columns or remove data; structural changes to existing tables still require an approved migration.

## Adding a curated goal

Goal membership and version choices live in reviewed JSON manifests under `cardchart/goals/`. The application validates every maintained manifest before startup synchronization, so adding a goal does not require route, pricing, or template changes.

From the goals dashboard, select **Add goal**. The first step has a searchable set dropdown and a live card gallery. Treatment chips derived from Scryfall's public promo/frame metadata—including Source material, Showcase, Extended art, Surge foil, Silver Scroll, Borderless, and Full art—let you narrow the gallery, while individual card controls and a compact selection preview show exactly what will continue. Collector ranges and exact metadata filters remain available under **Advanced filters**. The second step reviews printings, labels, treatment notes, and Cardmarket defaults. Activation validates the selected printings, creates the maintained manifest, checks the existing collection for exact accepted printing-and-finish matches, and opens the synchronized goal with those cards already owned. It will not replace an existing goal or manifest.

The CLI remains available for scripted authoring:

```bash
flask --app cardchart goals refresh-bulk
flask --app cardchart goals scaffold --slug example-goal --title "Example Goal" --description "A curated subset." --set-code abc
flask --app cardchart goals validate instance/goal-candidates/example-goal.json
```

Review the generated membership, versions, labels, and Cardmarket mapping before moving a CLI candidate into `cardchart/goals/`. See [goal manifest authoring](docs/goal-manifests.md) for both workflows and the schema.

The root page opens the goals dashboard. Imported cards remain available at `/inventory`.

## CSV format

```csv
Card Scryfall ID,Name,Set Code,Set Name,Collector Number,Rarity,Finish,Finish Display,Quantity
```

## Notes

Scraping routes are intentionally simple and transparent. eBay and Cardmarket markup can change, and both sites may apply bot protection or usage limits. Use the refresh action responsibly and review each site's terms before heavy use.

Imports of 100 or more rows refresh Scryfall's `default_cards` bulk data cache. CardChart reads Scryfall's current compressed JSON Lines download and continues to accept an existing JSON-array cache.

Collection matching uses the canonical Scryfall printing UUID and finish, never a card name or a different printing of the same Oracle card. A positive-quantity inventory row can satisfy matching checklist entries in more than one goal. Repeated goal synchronization adds only missing links and preserves ownership records that already exist.

Goal and inventory pages derive guide prices from that bulk cache and convert EUR values to approximate GBP using a daily ECB reference rate retrieved through Frankfurter. The goal summary values owned cards using their recorded printing, finish, and quantity, while missing cost uses the cheapest available accepted version for each missing entry. Accepted printing UUIDs keep these totals inside the curated set—for example, the Middle-earth Classic Artist total uses HOC printings and cannot substitute an LTR reprint. Inventory values likewise use each imported card's exact Scryfall printing and finish, multiplied by quantity. Inventory is paginated in groups of 20 and supports search plus sorting by name, set, quantity, or GBP line value. Missing-card images link to the corresponding Cardmarket product page. Prices are informational and may differ from live listings, checkout exchange rates, condition adjustments, and shipping.

Each goal page can download its missing entries as a UTF-8 Cardmarket Wants List text file. The export follows Cardmarket's documented `amount card name (version) (expansion)` decklist syntax and requests one standard copy per missing entry. HOC entries export as `(V.1) (The Hobbit: Eternal)` and SOA Japanese Mystical Archive entries as `(V.2) (Secrets of Strixhaven: Mystical Archive)`, preventing a generic name match from substituting another expansion. Paste the downloaded lines into Cardmarket's **Add MtG Decklist** field.
