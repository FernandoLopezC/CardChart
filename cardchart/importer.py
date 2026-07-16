import csv
from datetime import datetime, timezone

import requests

from .models import Card, db
from .scrapers import build_ebay_query, build_cardmarket_url

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


def import_cards(file_storage):
    rows = csv.DictReader(line.decode("utf-8-sig") for line in file_storage.stream)
    missing_headers = [header for header in REQUIRED_HEADERS if header not in rows.fieldnames]
    if missing_headers:
        raise ValueError(f"Missing CSV headers: {', '.join(missing_headers)}")

    imported = 0
    for row in rows:
        scryfall_id = row["Card Scryfall ID"].strip()
        if not scryfall_id:
            continue

        card = Card.query.filter_by(scryfall_id=scryfall_id).first() or Card(scryfall_id=scryfall_id)
        apply_csv_row(card, row)
        enrich_from_scryfall(card)
        db.session.add(card)
        imported += 1

    db.session.commit()
    return imported


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


def enrich_from_scryfall(card):
    response = requests.get(f"https://api.scryfall.com/cards/{card.scryfall_id}", timeout=20)
    response.raise_for_status()
    data = response.json()

    card.scryfall_uri = data.get("scryfall_uri")
    card.image_url = get_image_url(data)


def get_image_url(data):
    if data.get("image_uris"):
        return data["image_uris"].get("normal")

    card_faces = data.get("card_faces") or []
    if card_faces and card_faces[0].get("image_uris"):
        return card_faces[0]["image_uris"].get("normal")

    return None
