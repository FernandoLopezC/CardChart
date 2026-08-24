import gzip
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
        self.cards = []
        self.by_id = {}
        self.by_set_collector = {}
        self.sets = {}

        for card in cards:
            self.cards.append(card)
            card_id = card.get("id")
            set_code = (card.get("set") or "").lower()
            collector_number = card.get("collector_number") or ""

            if card_id:
                self.by_id[card_id] = card
            if set_code and collector_number:
                self.by_set_collector[(set_code, collector_number)] = card
            if (
                set_code
                and (not card.get("games") or "paper" in card.get("games", ()))
                and (card.get("lang") or "en").lower() == "en"
            ):
                item = self.sets.setdefault(
                    set_code,
                    {
                        "code": set_code,
                        "name": card.get("set_name") or set_code.upper(),
                        "released_at": card.get("released_at"),
                        "set_type": card.get("set_type"),
                        "card_count": 0,
                    },
                )
                item["card_count"] += 1

    def find_by_id(self, card_id):
        return self.by_id.get(card_id)

    def find_by_set_and_collector(self, set_code, collector_number):
        return self.by_set_collector.get((set_code.lower(), collector_number))

    def matching_cards(self, set_code=None, language=None):
        set_code = set_code.lower() if set_code else None
        language = language.lower() if language else None
        return tuple(
            card
            for card in self.cards
            if (not set_code or (card.get("set") or "").lower() == set_code)
            and (not language or (card.get("lang") or "").lower() == language)
        )

    def set_catalog(self):
        return tuple(
            sorted(
                self.sets.values(),
                key=lambda item: (
                    item.get("released_at") or "",
                    item["name"].casefold(),
                ),
                reverse=True,
            )
        )


def load_bulk_lookup(refresh=True):
    cache_dir = Path(current_app.instance_path) / "scryfall"
    cache_dir.mkdir(parents=True, exist_ok=True)

    cards_path = cache_dir / CACHE_JSON
    meta_path = cache_dir / CACHE_META
    if not refresh:
        if not cards_path.exists():
            return None
        cached = current_app.extensions.get("cardchart_scryfall_bulk_lookup")
        source_mtime = cards_path.stat().st_mtime_ns
        if cached and cached["source_mtime"] == source_mtime:
            return cached["lookup"]
        lookup = read_bulk_lookup(cards_path)
        current_app.extensions["cardchart_scryfall_bulk_lookup"] = {
            "source_mtime": source_mtime,
            "lookup": lookup,
        }
        return lookup

    bulk_item = fetch_default_cards_bulk_item()

    if should_refresh_cache(cards_path, meta_path, bulk_item):
        download_default_cards(cards_path, meta_path, bulk_item)

    lookup = read_bulk_lookup(cards_path)
    current_app.extensions["cardchart_scryfall_bulk_lookup"] = {
        "source_mtime": cards_path.stat().st_mtime_ns,
        "lookup": lookup,
    }
    return lookup


def load_bulk_metadata():
    meta_path = Path(current_app.instance_path) / "scryfall" / CACHE_META
    if not meta_path.exists():
        return None
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def bulk_cache_available():
    cards_path = Path(current_app.instance_path) / "scryfall" / CACHE_JSON
    return cards_path.exists()


def read_bulk_lookup(cards_path):
    with cards_path.open("rb") as bulk_file:
        is_gzip = bulk_file.read(2) == b"\x1f\x8b"

    if is_gzip:
        with gzip.open(cards_path, "rt", encoding="utf-8") as bulk_file:
            return ScryfallBulkLookup(
                json.loads(line) for line in bulk_file if line.strip()
            )

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
        cached_meta.get("download_uri") != bulk_item.get("jsonl_download_uri")
        or cached_meta.get("updated_at") != bulk_item.get("updated_at")
    )


def download_default_cards(cards_path, meta_path, bulk_item):
    download_uri = bulk_item["jsonl_download_uri"]
    response = requests.get(download_uri, timeout=120, headers=SCRYFALL_HEADERS)
    response.raise_for_status()

    cards_path.write_bytes(response.content)
    meta_path.write_text(
        json.dumps(
            {
                "download_uri": download_uri,
                "updated_at": bulk_item.get("updated_at"),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
