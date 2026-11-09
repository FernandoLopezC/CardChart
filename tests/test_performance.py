import io
import sqlite3
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from flask import Flask
from werkzeug.datastructures import FileStorage

from cardchart.importer import import_cards

from cardchart.models import Card, CollectionGoal, GoalCard, GoalCardPrinting, GuideObservation, PriceSnapshot, QuantityLot, db
from cardchart.performance import observation_history, performance_summary, record_observation, sync_quantity_lots

ID = "11111111-1111-4111-8111-111111111111"
TODAY = datetime.now(timezone.utc).date().isoformat()
SOURCE = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
RATE = {"rate": "1", "rate_date": TODAY, "fetched_on": TODAY}


def index(price):
    return {ID: {"prices": {"eur": price}}}


class PerformanceTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.config.update(SQLALCHEMY_DATABASE_URI="sqlite://", MARKET_PRICING_ENABLED=True)
        db.init_app(self.app)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.card = Card(scryfall_id=ID, name="Test", set_code="x", set_name="X", collector_number="1", rarity="rare", finish="nonfoil", finish_display="Nonfoil", quantity=2)
        db.session.add(self.card)
        db.session.flush()

    def tearDown(self):
        db.session.remove()
        db.engine.dispose()
        self.context.pop()

    def capture(self, price, rate=RATE, source=SOURCE):
        return record_observation(index(price), rate, source)

    def test_additions_fifo_and_evidence(self):
        first = self.capture("10")
        self.card.quantity = 3
        sync_quantity_lots(self.card, 2)
        self.capture("12")
        summary = performance_summary(index("12"), RATE)
        self.assertEqual((summary["baseline_gbp"], summary["current_gbp"], summary["change_gbp"], summary["percent"]), ("32.00", "36.00", "4.00", "12.50"))
        self.card.quantity = 1
        sync_quantity_lots(self.card, 3)
        self.capture("12")
        self.assertEqual([lot.remaining_quantity for lot in QuantityLot.query.order_by(QuantityLot.id)], [0, 1])
        self.assertEqual(performance_summary(index("12"), RATE)["change_gbp"], "0.00")
        self.assertEqual(first.values[0].eur_unit, "10")
        self.assertEqual(first.fx_rate, "1")
        self.assertEqual([h["quantity_change"] for h in observation_history()], [2, 1, -2])
        db.session.commit()
        db.session.remove()
        self.assertEqual(GuideObservation.query.count(), 3)

    def test_missing_values_zero_and_latest_idempotency(self):
        self.capture(None)
        self.assertEqual(performance_summary(index("12"), RATE)["comparable_quantity"], 0)
        self.capture("0")
        self.assertIsNone(performance_summary(index("12"), RATE)["percent"])
        self.assertEqual(performance_summary(index(None), RATE)["comparable_quantity"], 0)
        self.capture("0")
        self.assertEqual(GuideObservation.query.count(), 2)
        self.capture("1")
        self.capture("0")
        self.assertEqual(GuideObservation.query.count(), 4)

    def test_missing_evidence_never_baselines_and_rollback(self):
        with patch("cardchart.performance.guide_metadata", return_value={"source_updated_at": None}):
            record_observation(index("10"), RATE)
        self.assertIsNone(QuantityLot.query.one().baseline_value_id)
        db.session.rollback()
        self.assertEqual(Card.query.count(), 0)
        self.assertEqual(QuantityLot.query.count(), 0)
        self.assertEqual(GuideObservation.query.count(), 0)

    def test_disabled_pricing_does_not_load_cached_sources(self):
        self.app.config["MARKET_PRICING_ENABLED"] = False
        with patch("cardchart.performance.load_eur_to_gbp_rate") as rate, patch("cardchart.performance.load_scryfall_price_index") as prices:
            record_observation()
        rate.assert_not_called()
        prices.assert_not_called()
        self.assertIsNone(QuantityLot.query.one().baseline_value_id)
        self.assertIsNone(observation_history()[0]["gbp"])

    def test_additive_tables_and_sqlite_backup_preserve_existing_records(self):
        goal = CollectionGoal(slug="test", name="Test")
        entry = GoalCard(goal=goal, stable_key="one", position=1, name="Test", notes="keep notes")
        db.session.add_all([goal, entry, GoalCardPrinting(goal_card=entry, card=self.card, scryfall_id=ID, set_code="x", collector_number="1", finish="nonfoil", language="en", quantity=2, notes="keep link"), PriceSnapshot(card=self.card, source="legacy", price_gbp=7, source_url="https://example.test")])
        self.capture("10")
        db.session.commit()
        with tempfile.TemporaryDirectory() as directory:
            backup_path = Path(directory) / "backup.sqlite"
            target = sqlite3.connect(backup_path)
            db.session.connection().connection.driver_connection.backup(target)
            target.close()
            restored = sqlite3.connect(backup_path)
            self.assertEqual(restored.execute("select notes from goal_card").fetchone()[0], "keep notes")
            self.assertEqual(restored.execute("select notes, card_id from goal_card_printing").fetchone(), ("keep link", self.card.id))
            self.assertEqual(restored.execute("select source, price_gbp from price_snapshot").fetchone(), ("legacy", 7.0))
            self.assertEqual(restored.execute("select count(*) from quantity_lot").fetchone()[0], 1)
            restored.close()

    def test_absolute_import_is_repeat_safe_and_hook_failure_rolls_back(self):
        def csv_file(quantity):
            data = ("Card Scryfall ID,Name,Set Code,Set Name,Collector Number,Rarity,Finish,Finish Display,Quantity\n"
                    f"{ID},Test,x,X,1,rare,nonfoil,Nonfoil,{quantity}\n")
            return FileStorage(stream=io.BytesIO(data.encode()))

        db.session.commit()
        with patch("cardchart.importer.load_scryfall_bulk_lookup", return_value=None), patch("cardchart.importer.fetch_scryfall_card", return_value={"id": ID}), patch("cardchart.performance.load_scryfall_price_index", return_value=index("10")), patch("cardchart.performance.load_eur_to_gbp_rate", return_value=RATE), patch("cardchart.performance.guide_metadata", return_value={"source_updated_at": SOURCE}):
            import_cards(csv_file(3))
            import_cards(csv_file(3))
            self.assertEqual([lot.original_quantity for lot in QuantityLot.query.order_by(QuantityLot.id)], [2, 1])
            self.assertEqual(GuideObservation.query.count(), 1)
            with patch("cardchart.importer.record_observation", side_effect=RuntimeError("failure")):
                with self.assertRaises(RuntimeError):
                    import_cards(csv_file(4))
                db.session.rollback()
            self.assertEqual(db.session.get(Card, self.card.id).quantity, 3)
            self.assertEqual(sum(lot.remaining_quantity for lot in QuantityLot.query.all()), 3)

    def test_readded_lot_cannot_reuse_observation_before_it_was_tracked(self):
        first = self.capture("10")
        self.card.quantity = 0
        sync_quantity_lots(self.card, 2)
        self.card.quantity = 2
        sync_quantity_lots(self.card, 0)
        second = self.capture("10")
        self.assertNotEqual(first.id, second.id)
        lot = QuantityLot.query.order_by(QuantityLot.id.desc()).first()
        self.assertEqual(lot.baseline_value.observation_id, second.id)
        self.assertGreaterEqual(second.recorded_at.replace(tzinfo=timezone.utc), lot.tracked_at.replace(tzinfo=timezone.utc))

    def test_duplicate_import_rows_sync_only_final_quantity(self):
        self.capture("10")
        db.session.commit()
        data = ("Card Scryfall ID,Name,Set Code,Set Name,Collector Number,Rarity,Finish,Finish Display,Quantity\n"
                f"{ID},Test,x,X,1,rare,nonfoil,Nonfoil,1\n"
                f"{ID},Test,x,X,1,rare,nonfoil,Nonfoil,2\n")
        with patch("cardchart.importer.load_scryfall_bulk_lookup", return_value=None), patch("cardchart.importer.fetch_scryfall_card", return_value={"id": ID}), patch("cardchart.performance.load_scryfall_price_index", return_value=index("10")), patch("cardchart.performance.load_eur_to_gbp_rate", return_value=RATE), patch("cardchart.performance.guide_metadata", return_value={"source_updated_at": SOURCE}):
            import_cards(FileStorage(stream=io.BytesIO(data.encode())))
        lot = QuantityLot.query.one()
        self.assertEqual((lot.original_quantity, lot.remaining_quantity), (2, 2))
        self.assertEqual(GuideObservation.query.count(), 1)

    def test_future_source_and_stale_fx_do_not_create_baselines(self):
        future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        self.capture("10", source=future)
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).date().isoformat()
        self.capture("10", rate={"rate": "1", "rate_date": yesterday, "fetched_on": yesterday})
        self.assertIsNone(QuantityLot.query.one().baseline_value_id)
        self.capture("10")
        self.assertIsNotNone(QuantityLot.query.one().baseline_value_id)

    def test_reconciliation_partial_repeat_and_already_reflected_preserve_fifo(self):
        from test_reconciliation import ReconciliationTests

        helper = ReconciliationTests("test_sale_updates_linked_goal_quantities_and_records_history_atomically")
        helper.setUp()
        try:
            with helper.app.app_context():
                card = db.session.get(Card, helper.card_id)
                card.quantity = 3
                sync_quantity_lots(card, 0)
                card.quantity = 5
                sync_quantity_lots(card, 3)
                db.session.commit()
            for order, basis in (("one", "unreflected"), ("one", "unreflected"), ("two", "already_reflected"), ("three", "unreflected")):
                batch = helper.upload([helper.sale(order, 2)], basis=basis)
                helper.map(batch)
                helper.apply(batch)
                with helper.app.app_context():
                    quantities = [lot.remaining_quantity for lot in QuantityLot.query.order_by(QuantityLot.id)]
                self.assertEqual(quantities, [0, 1] if order == "three" else [1, 2])
        finally:
            helper.tearDown()
