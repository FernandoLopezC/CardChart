import gzip
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

import requests
from bs4 import BeautifulSoup

from cardchart import create_app
from cardchart.models import Card, CollectionGoal, GoalCard, GoalCardPrinting, GuideObservation, PriceSnapshot, db
from cardchart.pricing import load_scryfall_price_index, price_for_printing
from cardchart.scryfall_bulk import CACHE_JSON, CACHE_META, bulk_cards_path


class CollectorRouteTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite://", "MARKET_PRICING_ENABLED": False})
        self.app.instance_path = self.directory.name
        self.client = self.app.test_client()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
        self.directory.cleanup()

    def test_binder_keeps_manifest_pockets_and_focus_across_filters(self):
        path = "/goals/japanese-mystical-archive"
        with self.app.app_context():
            ids = [card.id for card in CollectionGoal.query.filter_by(slug="japanese-mystical-archive").one().cards]
        for selected_filter in ("all", "owned", "missing"):
            response = self.client.get(f"{path}?view=binder&filter={selected_filter}&page=2")
            self.assertEqual(response.status_code, 200)
            soup = BeautifulSoup(response.data, "html.parser")
            pockets = soup.select("article.goal-pocket")
            self.assertEqual([p["id"] for p in pockets], [f"card-{value}" for value in ids[9:18]])
        focused = self.client.get(f"{path}?view=binder&focus={ids[20]}")
        self.assertIn(b"Page 3 of 8", focused.data)
        self.assertIn(f'id="card-{ids[20]}"', focused.text)
        export = self.client.get(f"{path}/exports/cardmarket-wants.txt")
        self.assertEqual(len(export.text.splitlines()), 65)

    def test_dashboard_values_inventory_once_and_does_not_invent_history(self):
        with self.app.app_context():
            card = Card(scryfall_id="11111111-1111-4111-8111-111111111111", name="Tracked card", set_code="tst", set_name="Test", collector_number="1", rarity="rare", finish="nonfoil", finish_display="Non-foil", quantity=2)
            db.session.add(card)
            db.session.flush()
            db.session.add(PriceSnapshot(card=card, source="cardmarket_uk", price_gbp=99999, source_url="https://example.test"))
            for number in range(2):
                goal = CollectionGoal(slug=f"mirror-{number}", name=f"Mirror {number}")
                entry = GoalCard(goal=goal, stable_key="card", position=1, name=card.name, accepted_scryfall_ids=card.scryfall_id)
                db.session.add(GoalCardPrinting(goal_card=entry, card=card, scryfall_id=card.scryfall_id, set_code="tst", collector_number="1", finish="nonfoil", language="en", quantity=2))
            db.session.commit()
        self.app.config["MARKET_PRICING_ENABLED"] = True
        with patch("cardchart.routes.load_scryfall_price_index", return_value={"11111111-1111-4111-8111-111111111111": {"prices": {"eur": "10.00"}}}), patch("cardchart.routes.load_eur_to_gbp_rate", return_value={"rate": "0.85", "rate_date": "2026-11-06"}):
            for path in ("/", "/performance", "/performance?movers=fallers"):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                soup = BeautifulSoup(response.data, "html.parser")
                content = soup.get_text()
                self.assertEqual(soup.select_one(".inventory-value-summary strong").get_text(strip=True), "≈ £17.00")
                self.assertNotIn("99999", content)
                self.assertIn("No collection value snapshots yet", content)

    def test_guide_refresh_requires_csrf_and_reports_failure(self):
        self.assertEqual(self.client.post("/guides/refresh").status_code, 400)
        self.client.get("/inventory")
        with self.client.session_transaction() as session:
            token = session["reconciliation_csrf"]
        with patch("cardchart.routes.load_bulk_lookup", side_effect=requests.Timeout("timeout")):
            response = self.client.post("/guides/refresh", data={"csrf_token": token, "return_to": "/inventory"}, follow_redirects=True)
        self.assertIn(b"Guide refresh failed", response.data)
        self.assertNotIn(b"guide data updated", response.data)

    def test_guide_refresh_uses_bulk_pipeline_and_distinguishes_unchanged(self):
        self.client.get("/inventory")
        with self.client.session_transaction() as session:
            token = session["reconciliation_csrf"]
        with patch("cardchart.routes.load_bulk_lookup") as bulk, patch("cardchart.routes.load_eur_to_gbp_rate", return_value={"rate": "0.85", "rate_date": "2026-11-06"}), patch("cardchart.routes.scrape_cardmarket") as legacy:
            response = self.client.post("/guides/refresh", data={"csrf_token": token, "return_to": "/inventory"}, follow_redirects=True)
        bulk.assert_called_once_with(refresh=True)
        legacy.assert_not_called()
        self.assertIn(b"unchanged upstream", response.data)

    def test_malformed_refresh_retains_guide_cache_and_records_no_observation(self):
        self.app.config["MARKET_PRICING_ENABLED"] = True
        printing = "11111111-1111-4111-8111-111111111111"
        cache = Path(self.directory.name) / "scryfall"
        cache.mkdir()
        valid = {"id": printing, "prices": {"eur": "10.00", "eur_foil": None}}
        old_cards = json.dumps([valid]).encode()
        old_meta = json.dumps({"updated_at": "2026-01-01T00:00:00Z"}).encode()
        (cache / CACHE_JSON).write_bytes(old_cards)
        (cache / CACHE_META).write_bytes(old_meta)
        with self.app.app_context():
            db.session.add(Card(scryfall_id=printing, name="Tracked card", set_code="tst", set_name="Test", collector_number="1", rarity="rare", finish="nonfoil", finish_display="Non-foil", quantity=1))
            db.session.commit()
        self.client.get("/reconcile")
        with self.client.session_transaction() as session:
            token = session["reconciliation_csrf"]
        invalid_cards = [
            {**valid, "prices": "malformed"},
            {**valid, "prices": []},
            *({**valid, "prices": {"eur": value}} for value in ({}, [], True, 10, "bad", "NaN", "-1")),
            {**valid, "prices": {"eur_foil": []}},
            {**valid, "purchase_uris": "malformed"},
        ]
        cases = [(card, "2026-01-02T00:00:00Z") for card in invalid_cards]
        cases += [(valid, value) for value in ("bad", "2026-01-02", {}, (datetime.now(timezone.utc)+timedelta(days=1)).isoformat())]
        for card, timestamp in cases:
            with self.subTest(card=card, timestamp=timestamp):
                (cache / CACHE_JSON).write_bytes(old_cards)
                (cache / CACHE_META).write_bytes(old_meta)
                self.app.extensions.pop("cardchart_scryfall_prices", None)
                metadata = {"data": [{"type": "default_cards", "updated_at": timestamp, "jsonl_download_uri": "https://data.scryfall.io/cards.jsonl.gz"}]}
                responses = [Mock(json=Mock(return_value=metadata)), Mock(content=gzip.compress(json.dumps(card).encode()+b"\n"))]
                with patch("cardchart.scryfall_bulk.requests.get", side_effect=responses):
                    response = self.client.post("/guides/refresh", data={"csrf_token":token,"return_to":"/reconcile"}, follow_redirects=True)
                self.assertIn(b"Guide refresh failed", response.data)
                self.assertNotIn(b"guide data updated", response.data)
                self.assertNotIn(b"Collection observation saved", response.data)
                self.assertEqual((cache/CACHE_META).read_bytes(), old_meta)
                self.assertEqual(bulk_cards_path(cache).read_bytes(), old_cards)
                with self.app.app_context():
                    self.assertEqual(GuideObservation.query.count(), 0)
                    price = price_for_printing(printing, "nonfoil", load_scryfall_price_index([printing]), {"rate":"1"})
                    self.assertEqual(price["gbp"], "10.00")


if __name__ == "__main__":
    unittest.main()
