import gzip
import hashlib
import json
import os
import tempfile
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

    meta_path = cache_dir / CACHE_META
    cards_path = bulk_cards_path(cache_dir)
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
        cards_path = bulk_cards_path(cache_dir)

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
        value = json.loads(meta_path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except (OSError, ValueError):
        return None


def bulk_cache_available():
    cards_path = bulk_cards_path(Path(current_app.instance_path) / "scryfall")
    return cards_path.exists()


def bulk_cards_path(cache_dir):
    """Resolve the atomically published generation, including pre-generation caches."""
    try:
        metadata = json.loads((cache_dir / CACHE_META).read_text(encoding="utf-8"))
        filename = metadata.get("cache_file")
        if filename:
            if Path(filename).name != filename or not filename.startswith("scryfall-cards-"):
                raise ValueError("Invalid Scryfall cache filename.")
            return cache_dir / filename
    except (OSError, json.JSONDecodeError, AttributeError):
        pass
    return cache_dir / CACHE_JSON


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

    data = response.json()
    if not isinstance(data, dict) or not isinstance(data.get("data"), list):
        raise ValueError("Invalid Scryfall bulk metadata.")
    for item in data["data"]:
        if isinstance(item, dict) and item.get("type") == "default_cards":
            if not item.get("updated_at") or not str(item.get("jsonl_download_uri", "")).startswith("https://data.scryfall.io/"):
                raise ValueError("Invalid Scryfall default_cards metadata.")
            return item

    raise ValueError("Scryfall default_cards bulk data was not found.")


def should_refresh_cache(cards_path, meta_path, bulk_item):
    if not cards_path.exists() or not meta_path.exists():
        return True

    try:
        with meta_path.open(encoding="utf-8") as meta_file:
            cached_meta = json.load(meta_file)
        if not isinstance(cached_meta, dict):
            return True
    except (OSError, ValueError):
        return True

    return (
        cached_meta.get("download_uri") != bulk_item.get("jsonl_download_uri")
        or cached_meta.get("updated_at") != bulk_item.get("updated_at")
    )


def download_default_cards(cards_path, meta_path, bulk_item):
    download_uri = bulk_item["jsonl_download_uri"]
    response = requests.get(download_uri, timeout=120, headers=SCRYFALL_HEADERS)
    response.raise_for_status()

    content = response.content
    expected_size = bulk_item.get("compressed_size")
    if expected_size is not None and len(content) != expected_size:
        raise ValueError("Incomplete Scryfall bulk download.")
    # Publish the metadata pointer last so a failed download never replaces good data.
    generation = cards_path.parent / f"scryfall-cards-{hashlib.sha256(content).hexdigest()}.json"
    data_temp = meta_temp = None
    try:
        with tempfile.NamedTemporaryFile(dir=cards_path.parent, delete=False) as output:
            data_temp = Path(output.name)
            output.write(content)
        lookup = read_bulk_lookup(data_temp)
        if not lookup.cards or any(not isinstance(card, dict) or not card.get("id") for card in lookup.cards):
            raise ValueError("Invalid Scryfall card data.")
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=meta_path.parent, delete=False) as output:
            meta_temp = Path(output.name)
            json.dump({"download_uri": download_uri, "updated_at": bulk_item["updated_at"], "cache_file": generation.name}, output)
        os.replace(data_temp, generation)
        os.replace(meta_temp, meta_path)
    except (AttributeError, TypeError, EOFError) as exc:
        raise ValueError("Invalid Scryfall card data.") from exc
    finally:
        for path in (data_temp, meta_temp):
            if path is not None:
                path.unlink(missing_ok=True)
