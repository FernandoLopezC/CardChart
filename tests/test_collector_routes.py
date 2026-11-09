import tempfile
import unittest
from unittest.mock import patch

import requests
from bs4 import BeautifulSoup

from cardchart import create_app
from cardchart.models import Card, CollectionGoal, GoalCard, GoalCardPrinting, PriceSnapshot, db


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


if __name__ == "__main__":
    unittest.main()
