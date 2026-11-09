import gzip
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from flask import Flask

from cardchart.goal_definitions import (
    GoalVersionDefinition,
    middle_earth_classic_artists,
)
from cardchart.pricing import (
    build_goal_price_index,
    build_price_index,
    cheapest_price_for_versions,
    load_eur_to_gbp_rate,
    price_for_version,
)


class PricingTests(unittest.TestCase):
    def test_builds_small_goal_index_from_compressed_bulk_data(self):
        entry = middle_earth_classic_artists.entries[0]
        cards = [
            {"id": "unrelated"},
            {
                "id": entry.accepted_scryfall_ids[0],
                "prices": {"eur": "10.00", "eur_foil": "12.00"},
                "purchase_uris": {"cardmarket": "https://cardmarket.example/base"},
            },
            {
                "id": entry.accepted_scryfall_ids[1],
                "prices": {"eur": None, "eur_foil": "15.00"},
                "purchase_uris": {"cardmarket": "https://cardmarket.example/special"},
            },
        ]

        with tempfile.TemporaryDirectory() as directory:
            cards_path = Path(directory) / "cards.json"
            with gzip.open(cards_path, "wt", encoding="utf-8") as bulk_file:
                for card in cards:
                    bulk_file.write(json.dumps(card) + "\n")

            index = build_goal_price_index(cards_path)

        self.assertEqual(len(index), 2)
        self.assertEqual(
            index[entry.accepted_scryfall_ids[1]]["cardmarket_url"],
            "https://cardmarket.example/special",
        )

    def test_builds_price_index_for_requested_inventory_printings(self):
        cards = [
            {"id": "unrelated"},
            {"id": "inventory-id", "prices": {"eur_foil": "12.00"}},
        ]
        with tempfile.TemporaryDirectory() as directory:
            cards_path = Path(directory) / "cards.json"
            cards_path.write_text(json.dumps(cards), encoding="utf-8")
            index = build_price_index(cards_path, {"inventory-id"})

        self.assertEqual(index["inventory-id"]["prices"]["eur_foil"], "12.00")

    @patch("cardchart.pricing.requests.get")
    def test_daily_exchange_rate_is_cached(self, get):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "date": "2026-08-14",
            "base": "EUR",
            "quote": "GBP",
            "rate": 0.85,
        }
        get.return_value = response

        with tempfile.TemporaryDirectory() as directory:
            app = Flask(__name__, instance_path=directory)
            with app.app_context():
                first = load_eur_to_gbp_rate()
                second = load_eur_to_gbp_rate()

        self.assertEqual(first, second)
        self.assertEqual(first["rate"], "0.85")
        get.assert_called_once()

    def test_converts_selected_finish_and_keeps_cardmarket_link(self):
        version = GoalVersionDefinition(
            "foil", "Foil", "printing-id", "1", "foil", "en"
        )
        price = price_for_version(
            version,
            {
                "printing-id": {
                    "prices": {"eur": "10.00", "eur_foil": "12.00"},
                    "cardmarket_url": "https://cardmarket.example/printing",
                }
            },
            {"rate": "0.85"},
        )

        self.assertEqual(price["eur"], "12.00")
        self.assertEqual(price["gbp"], "10.20")
        self.assertEqual(
            price["cardmarket_url"], "https://cardmarket.example/printing"
        )

    def test_selects_cheapest_price_only_from_supplied_versions(self):
        versions = (
            GoalVersionDefinition(
                "base", "Non-foil", "hoc-base", "13", "nonfoil", "en"
            ),
            GoalVersionDefinition(
                "special", "Surge foil", "hoc-special", "53", "foil", "en"
            ),
        )
        price = cheapest_price_for_versions(
            versions,
            {
                "hoc-base": {"prices": {"eur": "10.00"}},
                "hoc-special": {"prices": {"eur_foil": "6.00"}},
                "ltr-reprint": {"prices": {"eur": "0.01"}},
            },
            {"rate": "0.85"},
        )

        self.assertEqual(price["eur"], "6.00")
        self.assertEqual(price["gbp"], "5.10")


if __name__ == "__main__":
    unittest.main()
