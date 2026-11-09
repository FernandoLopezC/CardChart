import gzip
import json
import tempfile
import unittest
from datetime import datetime, timezone
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

    def test_prices_only_supported_finishes_and_rejects_invalid_amounts(self):
        versions = {
            "nonfoil": GoalVersionDefinition("base", "Base", "card", "1", "nonfoil", "en"),
            "foil": GoalVersionDefinition("foil", "Foil", "card", "1", "foil", "en"),
            "etched": GoalVersionDefinition("etched", "Etched", "card", "1", "etched", "en"),
        }
        for finish, eur in (("nonfoil", "2.00"), ("foil", "3.00"), ("etched", None)):
            with self.subTest(finish=finish):
                price = price_for_version(
                    versions[finish],
                    {"card": {"prices": {"eur": "2", "eur_foil": "3"}}},
                    {"rate": "1"},
                )
                self.assertEqual(price["eur"], eur)

        for value in ("-0.01", "NaN", "Infinity", "not a price", None):
            with self.subTest(value=value):
                price = price_for_version(
                    versions["nonfoil"],
                    {"card": {"prices": {"eur": value}}},
                    {"rate": "1"},
                )
                self.assertIsNone(price["eur"])
                self.assertIsNone(price["gbp"])

        zero = price_for_version(
            versions["nonfoil"], {"card": {"prices": {"eur": "0"}}}, {"rate": "0.85"}
        )
        self.assertEqual((zero["eur"], zero["gbp"]), ("0.00", "0.00"))

    def test_gbp_conversion_rounds_half_up_to_pennies(self):
        version = GoalVersionDefinition("base", "Base", "card", "1", "nonfoil", "en")
        price = price_for_version(
            version,
            {"card": {"prices": {"eur": "1.01"}}},
            {"rate": "0.5"},
        )
        self.assertEqual(price["gbp"], "0.51")

    @patch("cardchart.pricing.requests.get")
    def test_invalid_today_cache_does_not_fall_back_to_yesterday(self, get):
        from cardchart.pricing import requests
        get.side_effect = requests.ConnectionError("offline")
        with tempfile.TemporaryDirectory() as directory:
            app = Flask(__name__, instance_path=directory)
            Path(directory, "eur-gbp-rate.json").write_text(
                json.dumps({"rate": "0.85", "rate_date": "2026-08-13", "fetched_on": "2026-08-13"}),
                encoding="utf-8",
            )
            with app.app_context():
                self.assertIsNone(load_eur_to_gbp_rate())
        get.assert_called_once()

    @patch("cardchart.pricing.requests.get")
    def test_rejects_malformed_rate_response_and_tolerates_cache_write_error(self, get):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"date": "bad", "base": "EUR", "quote": "GBP", "rate": "1"}
        get.return_value = response
        with tempfile.TemporaryDirectory() as directory:
            app = Flask(__name__, instance_path=directory)
            with app.app_context(), patch("cardchart.pricing.Path.write_text", side_effect=OSError("read only")):
                self.assertIsNone(load_eur_to_gbp_rate())
                response.json.return_value = {
                    "date": datetime.now(timezone.utc).date().isoformat(),
                    "base": "EUR", "quote": "GBP", "rate": "0.85",
                }
                self.assertEqual(load_eur_to_gbp_rate()["rate"], "0.85")

    def test_malformed_price_cache_rebuilds_and_write_failure_keeps_result(self):
        with tempfile.TemporaryDirectory() as directory:
            cache_dir = Path(directory, "scryfall")
            cache_dir.mkdir()
            cards_path = cache_dir / "scryfall-default-cards.json"
            cards_path.write_text(json.dumps([{"id": "requested", "prices": {"eur": "4"}}]), encoding="utf-8")
            (cache_dir / "scryfall-default-cards.meta.json").write_text(json.dumps({"updated_at": "2026-08-14T00:00:00Z"}), encoding="utf-8")
            price_cache = cache_dir / "scryfall-card-prices.json"
            price_cache.write_text("{broken", encoding="utf-8")
            app = Flask(__name__, instance_path=directory)
            with app.app_context(), patch("cardchart.pricing.Path.write_text", side_effect=OSError("read only")):
                from cardchart.pricing import load_scryfall_price_index
                result = load_scryfall_price_index({"requested"})
        self.assertEqual(result["requested"]["prices"]["eur"], "4")


if __name__ == "__main__":
    unittest.main()
