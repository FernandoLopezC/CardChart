import csv
import time
from datetime import datetime, timezone
from urllib.parse import quote

import requests
from slugify import slugify

from .models import Card, db
from .scrapers import build_ebay_query, build_cardmarket_url
from .scryfall_bulk import load_bulk_lookup

REQUIRED_HEADERS = [
    "Card Scryfall ID",
    "Name",
    "Set Code",
    "Set Name",
    "Collector Number",
    "Rarity",
    "Finish",
    "Finish Display",
    "Quantity",
]

SCRYFALL_HEADERS = {
    "User-Agent": "CardChart/0.1 (+local collection tracker)",
    "Accept": "application/json;q=0.9,*/*;q=0.8",
}
MAX_SCRYFALL_ATTEMPTS = 3
DEFAULT_THROTTLE_SECONDS = 1
BULK_IMPORT_MIN_ROWS = 100


class ImportResult:
    def __init__(self):
        self.imported = 0
        self.enriched = 0
        self.fallbacks = 0
        self.warnings = []


def import_cards(file_storage):
    rows = csv.DictReader(line.decode("utf-8-sig") for line in file_storage.stream)
    missing_headers = [header for header in REQUIRED_HEADERS if header not in rows.fieldnames]
    if missing_headers:
        raise ValueError(f"Missing CSV headers: {', '.join(missing_headers)}")

    import_rows = list(rows)
    result = ImportResult()
    bulk_lookup = load_scryfall_bulk_lookup(result, len(import_rows))
    for line_number, row in enumerate(import_rows, start=2):
        import_card(row, line_number, result, bulk_lookup)

    db.session.commit()
    return result


def load_scryfall_bulk_lookup(result, row_count):
    refresh = row_count >= BULK_IMPORT_MIN_ROWS
    try:
        return load_bulk_lookup(refresh=refresh)
    except requests.RequestException as exc:
        result.warnings.append(f"Scryfall bulk data was unavailable ({exc}); using live lookups instead.")
    except (OSError, ValueError) as exc:
        result.warnings.append(f"Scryfall bulk cache could not be loaded ({exc}); using live lookups instead.")
    return None


def import_card(row, line_number, result, bulk_lookup=None):
    lookup_key = row.get("Card Scryfall ID", "").strip()
    if not lookup_key:
        result.fallbacks += 1

    scryfall_data = find_in_bulk_lookup(row, lookup_key, bulk_lookup)

    if not scryfall_data and lookup_key:
        scryfall_data = fetch_scryfall_card(f"https://api.scryfall.com/cards/{lookup_key}", result, line_number)
    elif not scryfall_data:
        scryfall_data = fetch_by_set_and_collector(row, result, line_number)

    scryfall_id = (scryfall_data or {}).get("id") or lookup_key or build_csv_fallback_id(row)
    with db.session.no_autoflush:
        card = Card.query.filter_by(scryfall_id=scryfall_id).first()

    if card is None:
        card = Card(scryfall_id=scryfall_id)

    apply_csv_row(card, row)
    if scryfall_data:
        apply_scryfall_data(card, scryfall_data)
        result.enriched += 1
    else:
        result.warnings.append(f"Line {line_number}: imported CSV details without Scryfall enrichment.")

    db.session.add(card)
    result.imported += 1


def find_in_bulk_lookup(row, lookup_key, bulk_lookup):
    if bulk_lookup is None:
        return None

    if lookup_key:
        card = bulk_lookup.find_by_id(lookup_key)
        if card:
            return card

    set_code = row["Set Code"].strip()
    collector_number = row["Collector Number"].strip()
    if not set_code or not collector_number:
        return None

    return bulk_lookup.find_by_set_and_collector(set_code, collector_number)


def fetch_by_set_and_collector(row, result, line_number):
    set_code = row["Set Code"].strip().lower()
    collector_number = quote(row["Collector Number"].strip(), safe="")
    if not set_code or not collector_number:
        result.warnings.append(f"Line {line_number}: missing Scryfall ID and set/collector fallback data.")
        return None

    url = f"https://api.scryfall.com/cards/{set_code}/{collector_number}"
    return fetch_scryfall_card(url, result, line_number)


def fetch_scryfall_card(url, result, line_number):
    for attempt in range(1, MAX_SCRYFALL_ATTEMPTS + 1):
        try:
            response = requests.get(url, timeout=20, headers=SCRYFALL_HEADERS)
        except requests.RequestException as exc:
            if attempt == MAX_SCRYFALL_ATTEMPTS:
                result.warnings.append(f"Line {line_number}: Scryfall request failed ({exc}).")
                return None
            time.sleep(DEFAULT_THROTTLE_SECONDS)
            continue

        if response.status_code == 429:
            time.sleep(retry_after_seconds(response))
            continue

        if response.status_code == 404:
            result.warnings.append(f"Line {line_number}: Scryfall card was not found.")
            return None

        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            if attempt == MAX_SCRYFALL_ATTEMPTS:
                result.warnings.append(f"Line {line_number}: Scryfall returned an error ({exc}).")
                return None
            time.sleep(DEFAULT_THROTTLE_SECONDS)
            continue

        return response.json()

    result.warnings.append(f"Line {line_number}: Scryfall throttled the request after {MAX_SCRYFALL_ATTEMPTS} attempts.")
    return None


def retry_after_seconds(response):
    retry_after = response.headers.get("Retry-After", "")
    try:
        return max(float(retry_after), DEFAULT_THROTTLE_SECONDS)
    except ValueError:
        return DEFAULT_THROTTLE_SECONDS


def build_csv_fallback_id(row):
    parts = [
        "csv",
        row["Set Code"].strip(),
        row["Collector Number"].strip(),
        row["Finish"].strip(),
        row["Name"].strip(),
    ]
    return ":".join(slugify(part) or "unknown" for part in parts)


def apply_csv_row(card, row):
    card.name = row["Name"].strip()
    card.set_code = row["Set Code"].strip()
    card.set_name = row["Set Name"].strip()
    card.collector_number = row["Collector Number"].strip()
    card.rarity = row["Rarity"].strip()
    card.finish = row["Finish"].strip()
    card.finish_display = row["Finish Display"].strip()
    card.quantity = int(row["Quantity"] or 1)
    card.ebay_query = build_ebay_query(card)
    card.cardmarket_url = build_cardmarket_url(card)
    card.updated_at = datetime.now(timezone.utc)


def apply_scryfall_data(card, data):
    card.scryfall_uri = data.get("scryfall_uri")
    card.image_url = get_image_url(data)
    if data.get("cardmarket_id"):
        card.cardmarket_id = int(data.get("cardmarket_id"))


def get_image_url(data):
    if data.get("image_uris"):
        return data["image_uris"].get("normal")

    card_faces = data.get("card_faces") or []
    if card_faces and card_faces[0].get("image_uris"):
        return card_faces[0]["image_uris"].get("normal")

    return None
