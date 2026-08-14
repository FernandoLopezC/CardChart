# CardChart

CardChart is a small Flask app for tracking curated Magic: The Gathering collection goals and imported physical cards.

It keeps desired cards visible even when they are missing and associates exact owned printings with each checklist entry. CSV import uses Scryfall IDs and can explicitly match accepted goal printings. Existing UK-focused pricing tools remain available as legacy inventory behavior.

See [product direction](docs/product-direction.md) for product and data-model intent and [remaining tasks](docs/remaining-tasks.md) for genuine blockers and decisions.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
flask --app cardchart init-db
flask --app cardchart run
```

Open http://127.0.0.1:5000.

The root page opens the goals dashboard. Imported cards remain available at `/inventory`.

## CSV format

```csv
Card Scryfall ID,Name,Set Code,Set Name,Collector Number,Rarity,Finish,Finish Display,Quantity
```

## Notes

Scraping routes are intentionally simple and transparent. eBay and Cardmarket markup can change, and both sites may apply bot protection or usage limits. Use the refresh action responsibly and review each site's terms before heavy use.
