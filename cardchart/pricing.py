import gzip
import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

import requests
from flask import current_app

from .goal_definitions import GOAL_DEFINITIONS
from .scryfall_bulk import CACHE_JSON, CACHE_META

PRICE_CACHE = "scryfall-card-prices.json"
FX_CACHE = "eur-gbp-rate.json"
EUR_GBP_RATE_URL = (
    "https://api.frankfurter.dev/v2/rate/EUR/GBP?providers=ECB"
)
FX_HEADERS = {
    "User-Agent": "CardChart/0.1 (+local collection tracker)",
    "Accept": "application/json",
}


def load_scryfall_price_index(required_ids=()):
    cache_dir = Path(current_app.instance_path) / "scryfall"
    cards_path = cache_dir / CACHE_JSON
    meta_path = cache_dir / CACHE_META
    price_cache_path = cache_dir / PRICE_CACHE
    if not cards_path.exists():
        return {}

    wanted_ids = goal_printing_ids() | {value for value in required_ids if value}
    source_updated_at = read_bulk_updated_at(meta_path)
    extension_cache = current_app.extensions.get("cardchart_scryfall_prices")
    if (
        extension_cache
        and extension_cache["source_updated_at"] == source_updated_at
        and wanted_ids <= extension_cache["requested_ids"]
    ):
        return extension_cache["cards"]

    cached = read_json(price_cache_path)
    cached_ids = set(cached.get("requested_ids", ())) if cached else set()
    if (
        cached
        and cached.get("source_updated_at") == source_updated_at
        and wanted_ids <= cached_ids
    ):
        prices = cached.get("cards", {})
        requested_ids = cached_ids
    else:
        requested_ids = wanted_ids | cached_ids
        prices = build_price_index(cards_path, requested_ids)
        price_cache_path.write_text(
            json.dumps(
                {
                    "source_updated_at": source_updated_at,
                    "requested_ids": sorted(requested_ids),
                    "cards": prices,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    current_app.extensions["cardchart_scryfall_prices"] = {
        "source_updated_at": source_updated_at,
        "requested_ids": requested_ids,
        "cards": prices,
    }
    return prices


def load_goal_price_index():
    return load_scryfall_price_index()


def goal_printing_ids():
    return {
        printing_id
        for definition in GOAL_DEFINITIONS
        for entry in definition.entries
        for printing_id in entry.accepted_scryfall_ids
    }


def build_goal_price_index(cards_path):
    return build_price_index(cards_path, goal_printing_ids())


def build_price_index(cards_path, wanted_ids):
    wanted_ids = set(wanted_ids)
    prices = {}
    for card in iter_bulk_cards(cards_path):
        card_id = card.get("id")
        if card_id not in wanted_ids:
            continue
        prices[card_id] = {
            "prices": card.get("prices") or {},
            "cardmarket_url": (card.get("purchase_uris") or {}).get("cardmarket"),
        }
        if len(prices) == len(wanted_ids):
            break
    return prices


def iter_bulk_cards(cards_path):
    with cards_path.open("rb") as bulk_file:
        is_gzip = bulk_file.read(2) == b"\x1f\x8b"

    if is_gzip:
        with gzip.open(cards_path, "rt", encoding="utf-8") as bulk_file:
            for line in bulk_file:
                if line.strip():
                    yield json.loads(line)
        return

    with cards_path.open(encoding="utf-8") as bulk_file:
        yield from json.load(bulk_file)


def load_eur_to_gbp_rate():
    cache_path = Path(current_app.instance_path) / FX_CACHE
    today = datetime.now(timezone.utc).date().isoformat()
    extension_cache = current_app.extensions.get("cardchart_eur_gbp_rate")
    if extension_cache and extension_cache.get("fetched_on") == today:
        return extension_cache

    cached = read_json(cache_path)
    if cached and cached.get("fetched_on") == today:
        current_app.extensions["cardchart_eur_gbp_rate"] = cached
        return cached

    try:
        response = requests.get(EUR_GBP_RATE_URL, headers=FX_HEADERS, timeout=10)
        response.raise_for_status()
        data = response.json()
        rate = Decimal(str(data["rate"]))
        if data.get("base") != "EUR" or data.get("quote") != "GBP" or rate <= 0:
            raise ValueError("Unexpected EUR to GBP exchange-rate response.")
    except (requests.RequestException, KeyError, TypeError, ValueError, InvalidOperation):
        return None

    rate_info = {
        "rate": str(rate),
        "rate_date": data.get("date"),
        "fetched_on": today,
    }
    cache_path.write_text(json.dumps(rate_info, indent=2), encoding="utf-8")
    current_app.extensions["cardchart_eur_gbp_rate"] = rate_info
    return rate_info


def price_for_version(version, price_index, rate_info):
    return price_for_printing(
        version.scryfall_id, version.finish, price_index, rate_info
    )


def price_for_printing(scryfall_id, finish, price_index, rate_info):
    price_data = price_index.get(scryfall_id, {})
    prices = price_data.get("prices", {})
    eur_value = prices.get("eur" if finish == "nonfoil" else "eur_foil")
    try:
        eur = Decimal(eur_value)
        rate = Decimal(rate_info["rate"]) if rate_info else None
    except (InvalidOperation, TypeError, KeyError):
        eur = None
        rate = None

    gbp = None
    if eur is not None and rate is not None:
        gbp = (eur * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    return {
        "eur": f"{eur:.2f}" if eur is not None else None,
        "gbp": f"{gbp:.2f}" if gbp is not None else None,
        "cardmarket_url": price_data.get("cardmarket_url"),
    }


def cheapest_price_for_versions(versions, price_index, rate_info):
    available = [
        price_for_version(version, price_index, rate_info)
        for version in versions
    ]
    available = [price for price in available if price["gbp"] is not None]
    if not available:
        return None
    return min(available, key=lambda price: Decimal(price["gbp"]))


def read_bulk_updated_at(meta_path):
    meta = read_json(meta_path)
    return meta.get("updated_at") if meta else None


def read_json(path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
