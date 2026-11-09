import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from bs4 import BeautifulSoup

from cardchart import create_app
from cardchart.goal_definitions import goal_entry_versions
from cardchart.goal_prices import goal_price_drops, record_goal_prices
from cardchart.models import CollectionGoal, GoalCardPrinting, GoalPriceObservation, GuideObservation, db
from cardchart.pricing import load_goal_price_index
from cardchart.scryfall_bulk import CACHE_JSON, CACHE_META


class GoalPriceDropTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite://", "MARKET_PRICING_ENABLED": True})
        self.app.instance_path = self.temp.name
        self.context = self.app.app_context()
        self.context.push()
        self.client = self.app.test_client()
        self.goal = CollectionGoal.query.filter_by(slug="middle-earth-classic-artists").one()
        self.card = self.goal.cards[0]
        self.versions = goal_entry_versions(self.goal.slug, self.card.stable_key)
        self.base, self.foil = self.versions[0], self.versions[-1]
        self.now = datetime.now(timezone.utc)
        self.rate = {"rate": "1", "rate_date": self.now.date().isoformat(), "fetched_on": self.now.date().isoformat()}
        self.path = f"/goals/{self.goal.slug}"
        self.cache = Path(self.temp.name) / "scryfall"
        self.cache.mkdir()
        self.client.get("/reconcile")
        with self.client.session_transaction() as session:
            self.token = session["reconciliation_csrf"]

    def tearDown(self):
        db.session.remove()
        db.engine.dispose()
        self.context.pop()
        self.temp.cleanup()

    def source(self, days, normal="10", foil="20"):
        rows = [
            {"id": self.base.scryfall_id, "prices": {"eur": normal}, "purchase_uris": {"cardmarket": "https://example.test/base"}},
            {"id": self.foil.scryfall_id, "prices": {"eur_foil": foil}, "purchase_uris": {"cardmarket": "https://example.test/foil"}},
        ]
        (self.cache / CACHE_JSON).write_text(json.dumps(rows), encoding="utf-8")
        (self.cache / CACHE_META).write_text(json.dumps({"updated_at": (self.now - timedelta(days=days)).isoformat()}), encoding="utf-8")

    def refresh(self):
        with patch("cardchart.routes.load_bulk_lookup"), patch("cardchart.routes.load_eur_to_gbp_rate", return_value=self.rate):
            return self.client.post("/guides/refresh", data={"csrf_token": self.token, "return_to": self.path}, follow_redirects=True)

    def drops(self):
        return goal_price_drops(self.goal, load_goal_price_index(), self.rate)

    def test_refresh_tracks_missing_versions_without_inventing_inventory(self):
        self.source(2)
        self.assertIn("A later change gives us a comparison", self.refresh().text)
        self.assertEqual(GoalPriceObservation.query.count(), 1)
        self.source(1, "12", "15")
        response = self.refresh()
        self.assertIn("1 missing card has lower guide prices", response.text)
        self.assertIn("down £5.00 (25.0%)", response.text)
        drop = self.drops()["cards"][self.card.id][0]
        self.assertEqual(drop["version"].key, self.foil.key)
        self.assertEqual(drop["url"], "https://example.test/foil")
        self.assertEqual(GuideObservation.query.order_by(GuideObservation.id.desc()).first().values, [])

    def test_unchanged_refresh_keeps_flags_and_page_reads_do_not_record(self):
        self.source(2)
        self.refresh()
        self.source(1, "9")
        self.refresh()
        for _ in range(2):
            self.refresh()
            self.assertEqual(GoalPriceObservation.query.count(), 2)
            self.assertIn(self.card.id, self.drops()["cards"])
        with patch("cardchart.routes.load_eur_to_gbp_rate", return_value=self.rate):
            self.client.get(self.path)
        self.assertEqual(GoalPriceObservation.query.count(), 2)
        self.source(0, "9")
        self.refresh()
        self.assertEqual(self.drops()["cards"], {})

    def test_absent_prices_and_zero_are_not_invented_drops(self):
        self.source(2, None, "0")
        self.refresh()
        self.source(1, "1", "0")
        self.refresh()
        self.assertEqual(self.drops()["cards"], {})
        self.source(0, "0", None)
        self.refresh()
        drop = self.drops()["cards"][self.card.id][0]
        self.assertEqual((drop["after"], drop["percent"]), ("0.00", "100.0"))

    def test_owned_cards_are_excluded_and_filters_keep_binder_positions(self):
        self.source(2)
        self.refresh()
        self.source(1, "9")
        self.refresh()
        with patch("cardchart.routes.load_eur_to_gbp_rate", return_value=self.rate):
            cards = BeautifulSoup(self.client.get(self.path + "?filter=drops").data, "html.parser")
            binder = BeautifulSoup(self.client.get(self.path + "?view=binder&filter=drops").data, "html.parser")
        self.assertEqual(len(cards.select("article.goal-pocket")), 1)
        self.assertEqual(len(binder.select("article.goal-pocket")), 9)
        self.assertEqual(len(binder.select("article.filtered-pocket")), 8)
        db.session.add(GoalCardPrinting(goal_card=self.card, scryfall_id=self.base.scryfall_id, set_code=self.base.set_code, collector_number=self.base.collector_number, finish=self.base.finish, language=self.base.language, quantity=1))
        db.session.commit()
        self.assertEqual(self.drops()["cards"], {})

    def test_failed_history_write_rolls_back_both_histories(self):
        self.source(2)
        self.refresh()
        before = (GoalPriceObservation.query.count(), GuideObservation.query.count())
        self.source(1, "9")
        with patch("cardchart.routes.record_goal_prices", side_effect=RuntimeError("disk failure")):
            response = self.refresh()
        self.assertIn("price history could not be saved", response.text)
        self.assertEqual((GoalPriceObservation.query.count(), GuideObservation.query.count()), before)
        self.assertEqual(self.drops()["status"], "refresh")

    def test_missing_fx_does_not_replace_comparison_and_fx_change_is_explicit(self):
        self.source(2)
        self.refresh()
        self.source(1, "9")
        self.refresh()
        record_goal_prices(None)
        db.session.commit()
        self.assertEqual(GoalPriceObservation.query.count(), 2)
        self.assertEqual(goal_price_drops(self.goal, load_goal_price_index(), None)["status"], "unavailable")
        self.rate = {**self.rate, "rate": "0.8"}
        self.assertEqual(self.drops()["status"], "refresh")
        self.refresh()
        self.assertEqual(self.drops()["cards"][self.card.id][0]["drop"], "1.80")

    def test_stale_source_cannot_be_recorded_over_newer_history(self):
        self.source(1)
        self.refresh()
        self.source(2, "1")
        with self.assertRaisesRegex(ValueError, "older"):
            record_goal_prices(self.rate)
        db.session.rollback()
        self.assertEqual(GoalPriceObservation.query.count(), 1)

    def test_comparison_survives_database_backup_and_reopen(self):
        self.source(2)
        self.refresh()
        self.source(1, "8")
        self.refresh()
        saved = Path(self.temp.name) / "saved.sqlite"
        with closing(sqlite3.connect(saved)) as target:
            db.session.connection().connection.driver_connection.backup(target)
        restored = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{saved.as_posix()}", "MARKET_PRICING_ENABLED": True})
        restored.instance_path = self.temp.name
        with restored.app_context():
            goal = CollectionGoal.query.filter_by(slug=self.goal.slug).one()
            drops = goal_price_drops(goal, load_goal_price_index(), self.rate)
            self.assertEqual(drops["cards"][goal.cards[0].id][0]["drop"], "2.00")
            self.assertEqual(GoalPriceObservation.query.count(), 2)
            db.session.remove()
            db.engine.dispose()


if __name__ == "__main__":
    unittest.main()
