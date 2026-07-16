import json
from pathlib import Path

import requests
from flask import current_app

SCRYFALL_BULK_DATA_URL = "https://api.scryfall.com/bulk-data"
SCRYFALL_HEADERS = {
    "User-Agent": "CardChart/0.1 (+local collection tracker)",
    "Accept": "application/json;q=0.9,*/*;q=0.8",
}
CACHE_JSON = "scryfall-default-cards.json"
CACHE_META = "scryfall-default-cards.meta.json"


class ScryfallBulkLookup:
    def __init__(self, cards):
        self.by_id = {}
        self.by_set_collector = {}

        for card in cards:
            card_id = card.get("id")
            set_code = (card.get("set") or "").lower()
            collector_number = card.get("collector_number") or ""

            if card_id:
                self.by_id[card_id] = card
            if set_code and collector_number:
                self.by_set_collector[(set_code, collector_number)] = card

    def find_by_id(self, card_id):
        return self.by_id.get(card_id)

    def find_by_set_and_collector(self, set_code, collector_number):
        return self.by_set_collector.get((set_code.lower(), collector_number))


def load_bulk_lookup(refresh=True):
    cache_dir = Path(current_app.instance_path) / "scryfall"
    cache_dir.mkdir(parents=True, exist_ok=True)

    cards_path = cache_dir / CACHE_JSON
    meta_path = cache_dir / CACHE_META
    if not refresh:
        if not cards_path.exists():
            return None
        return read_bulk_lookup(cards_path)

    bulk_item = fetch_default_cards_bulk_item()

    if should_refresh_cache(cards_path, meta_path, bulk_item):
        download_default_cards(cards_path, meta_path, bulk_item)

    return read_bulk_lookup(cards_path)


def read_bulk_lookup(cards_path):
    with cards_path.open(encoding="utf-8") as bulk_file:
        return ScryfallBulkLookup(json.load(bulk_file))


def fetch_default_cards_bulk_item():
    response = requests.get(SCRYFALL_BULK_DATA_URL, timeout=20, headers=SCRYFALL_HEADERS)
    response.raise_for_status()

    for item in response.json().get("data", []):
        if item.get("type") == "default_cards":
            return item

    raise ValueError("Scryfall default_cards bulk data was not found.")


def should_refresh_cache(cards_path, meta_path, bulk_item):
    if not cards_path.exists() or not meta_path.exists():
        return True

    with meta_path.open(encoding="utf-8") as meta_file:
        cached_meta = json.load(meta_file)

    return (
        cached_meta.get("download_uri") != bulk_item.get("download_uri")
        or cached_meta.get("updated_at") != bulk_item.get("updated_at")
    )


def download_default_cards(cards_path, meta_path, bulk_item):
    response = requests.get(bulk_item["download_uri"], timeout=120, headers=SCRYFALL_HEADERS)
    response.raise_for_status()

    cards_path.write_bytes(response.content)
    meta_path.write_text(
        json.dumps(
            {
                "download_uri": bulk_item.get("download_uri"),
                "updated_at": bulk_item.get("updated_at"),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
