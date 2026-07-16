# CardChart

CardChart is a small Flask app for tracking Magic: The Gathering collection values with UK-focused pricing sources.

It imports cards from CSV using Scryfall IDs, stores the collection in a local SQLite database, shows Scryfall images, and has scraper hooks for eBay UK sold listings and Cardmarket UK listings.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
flask --app cardchart init-db
flask --app cardchart run
```

Open http://127.0.0.1:5000.

## CSV format

```csv
Card Scryfall ID,Name,Set Code,Set Name,Collector Number,Rarity,Finish,Finish Display,Quantity
```

## Notes

Scraping routes are intentionally simple and transparent. eBay and Cardmarket markup can change, and both sites may apply bot protection or usage limits. Use the refresh action responsibly and review each site's terms before heavy use.
