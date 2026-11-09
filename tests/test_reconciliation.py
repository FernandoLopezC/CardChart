import csv
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cardchart import create_app
from cardchart.goal_definitions import middle_earth_classic_artists, synchronize_goals
from cardchart.models import Card, GoalCardPrinting, ReconciliationBatch, ReconciliationEntry, db
from cardchart.reconciliation import ReconciliationError, apply_review


PRINTING_ID = middle_earth_classic_artists.entries[0].versions[0].scryfall_id
OTHER_ID = "22222222-2222-4222-8222-222222222222"
HEADERS = ["Name", "ID", "Finish", "Qty", "Order", "Line", "Status"]


class ReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite://", "MARKET_PRICING_ENABLED": False, "SECRET_KEY": "test"})
        self.app.instance_path = self.directory.name
        self.client = self.app.test_client()
        with self.app.app_context():
            card = Card(scryfall_id=PRINTING_ID, name="Test Card", set_code="hoc", set_name="Test Set", collector_number="13", rarity="rare", finish="nonfoil", finish_display="Non-foil", quantity=5)
            db.session.add(card)
            db.session.commit()
            self.card_id = card.id
            synchronize_goals()
        self.client.get("/reconcile")
        with self.client.session_transaction() as session:
            self.csrf = session["reconciliation_csrf"]

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.engine.dispose()
        self.directory.cleanup()

    def upload(self, rows, *, source="ebay", kind="disposal", basis="unreflected", **settings):
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(HEADERS)
        writer.writerows(rows)
        response = self.client.post("/reconcile", data={
            "csrf_token": self.csrf, "source": source, "kind": kind,
            "basis": basis, "observed_on": "2026-01-01", **settings,
            "csv_file": (io.BytesIO(output.getvalue().encode()), "export.csv"),
        })
        self.assertEqual(response.status_code, 302, response.text)
        batch_id = int(response.location.split("/")[-2])
        return batch_id

    def map(self, batch_id, **overrides):
        fields = {"name": "Name", "scryfall_id": "ID", "finish": "Finish", "quantity": "Qty", "reference": "Order", "line_id": "Line", "status": "Status", "eligible_statuses": "Completed"}
        response = self.client.post(f"/reconcile/{batch_id}/map", data={"csrf_token": self.csrf, **fields, **overrides})
        self.assertEqual(response.status_code, 302, response.text)
        page = self.client.get(response.location)
        self.assertEqual(page.status_code, 200, page.text)
        return page

    def apply(self, batch_id, rows=(0,), **overrides):
        with self.app.app_context():
            token = db.session.get(ReconciliationBatch, batch_id).preview_token
        form = {"csrf_token": self.csrf, "preview_token": token, "confirmed": "yes"}
        form.update({f"apply_{i}": "yes" for i in rows})
        form.update(overrides)
        return self.client.post(f"/reconcile/{batch_id}/review", data=form, follow_redirects=True)

    def stock(self):
        with self.app.app_context():
            return db.session.get(Card, self.card_id).quantity

    def sale(self, order="order-1", amount=2, **overrides):
        row = {"Name": "Test Card", "ID": PRINTING_ID, "Finish": "nonfoil", "Qty": amount, "Order": order, "Line": "item-1", "Status": "Completed", **overrides}
        return [row[k] for k in HEADERS]

    def test_staging_and_mapping_do_not_change_stock_and_show_source_samples(self):
        batch = self.upload([self.sale()])
        mapping = self.client.get(f"/reconcile/{batch}/map")
        self.assertIn("order-1", mapping.text)
        page = self.map(batch)
        self.assertIn("Review matched rows", page.text)
        self.assertEqual(self.stock(), 5)
        with self.app.app_context():
            self.assertEqual(ReconciliationEntry.query.count(), 0)
            self.assertNotIn("csrf_token", db.session.get(ReconciliationBatch, batch).mapping_json)

    def test_sale_updates_linked_goal_quantities_and_records_history_atomically(self):
        batch = self.upload([self.sale()])
        self.map(batch)
        page = self.apply(batch)
        self.assertIn("Reconciliation saved", page.text)
        self.assertEqual(self.stock(), 3)
        with self.app.app_context():
            self.assertEqual(GoalCardPrinting.query.filter_by(card_id=self.card_id).one().quantity, 3)
            entry = ReconciliationEntry.query.one()
            self.assertEqual((entry.before_quantity, entry.after_quantity), (5, 3))
            self.assertEqual(db.session.get(ReconciliationBatch, batch).raw_json, "{}")

    def test_overlapping_repeat_file_skips_recorded_rows_and_applies_only_new_sales(self):
        first = self.upload([self.sale()])
        self.map(first)
        self.apply(first)
        second = self.upload([self.sale(), self.sale("order-2", 1)])
        page = self.map(second)
        self.assertIn("Already applied", page.text)
        self.apply(second, rows=(0, 1))
        self.assertEqual(self.stock(), 2)
        with self.app.app_context():
            self.assertEqual(ReconciliationEntry.query.count(), 2)

    def test_multiple_transactions_for_one_printing_deduct_the_combined_amount(self):
        batch = self.upload([self.sale("a", 1), self.sale("b", 2)])
        self.map(batch)
        self.apply(batch, rows=(0, 1))
        self.assertEqual(self.stock(), 2)
        with self.app.app_context():
            self.assertEqual([(e.before_quantity, e.after_quantity) for e in ReconciliationEntry.query.order_by(ReconciliationEntry.id)], [(5, 4), (4, 2)])

    def test_already_reflected_sales_are_recorded_without_subtracting_again(self):
        batch = self.upload([self.sale()], basis="already_reflected")
        self.map(batch)
        self.apply(batch)
        self.assertEqual(self.stock(), 5)
        repeated = self.upload([self.sale()])
        self.map(repeated)
        self.apply(repeated)
        self.assertEqual(self.stock(), 5)

    def test_tracker_snapshots_replace_counts_instead_of_adding_them(self):
        for source in ("collectr", "deckcheck"):
            batch = self.upload([self.sale(amount=3)], source=source, kind="snapshot")
            self.map(batch)
            self.apply(batch)
        self.assertEqual(self.stock(), 3)

    def test_repeat_snapshot_cannot_restore_stock_after_a_sale(self):
        rows = [self.sale(amount=5)]
        snapshot = self.upload(rows, source="collectr", kind="snapshot")
        self.map(snapshot)
        self.apply(snapshot)
        sale = self.upload([self.sale()])
        self.map(sale)
        self.apply(sale)
        repeated = self.upload(rows, source="collectr", kind="snapshot")
        self.map(repeated)
        self.apply(repeated)
        self.assertEqual(self.stock(), 3)

    def test_cancelled_rows_and_missing_references_cannot_be_applied(self):
        for row in (self.sale(Status="Cancelled"), self.sale(Order="")):
            with self.subTest(row=row):
                batch = self.upload([row])
                self.map(batch)
                self.apply(batch)
                self.assertEqual(self.stock(), 5)
        with self.app.app_context():
            self.assertEqual(ReconciliationEntry.query.count(), 0)

    def test_duplicate_line_references_and_overselling_roll_back_the_whole_batch(self):
        for rows in ([self.sale(), self.sale()], [self.sale("a", 2), self.sale("b", 4)]):
            with self.subTest(rows=rows):
                batch = self.upload(rows)
                self.map(batch)
                self.apply(batch, rows=(0, 1))
                self.assertEqual(self.stock(), 5)
                with self.app.app_context():
                    self.assertEqual(ReconciliationEntry.query.count(), 0)
                    self.assertEqual(db.session.get(ReconciliationBatch, batch).state, "review")

    def test_changed_transaction_contents_are_a_conflict(self):
        first = self.upload([self.sale()])
        self.map(first)
        self.apply(first)
        second = self.upload([self.sale(amount=3)])
        page = self.map(second)
        self.assertIn("different contents", page.text)
        self.apply(second)
        self.assertEqual(self.stock(), 3)

    def test_changing_line_id_mapping_cannot_deduct_the_same_sale_again(self):
        for original, repeated in (("", "Line"), ("Line", "")):
            with self.subTest(original=original):
                reference = "mode-" + (original or "none")
                first = self.upload([self.sale(reference, 1)])
                self.map(first, line_id=original)
                self.apply(first)
                before = self.stock()
                second = self.upload([self.sale(reference, 1)])
                page = self.map(second, line_id=repeated)
                self.assertIn("mapping changed", page.text)
                self.apply(second)
                self.assertEqual(self.stock(), before)

    def test_remapping_invalidates_an_open_review_before_redirect_is_followed(self):
        batch = self.upload([self.sale()])
        self.map(batch)
        with self.app.app_context():
            old_token = db.session.get(ReconciliationBatch, batch).preview_token
        response = self.client.post(f"/reconcile/{batch}/map", data={
            "csrf_token": self.csrf, "name": "Name", "quantity": "Qty", "finish": "Finish",
            "scryfall_id": "ID", "reference": "Order", "line_id": "Line", "confirmed_completed": "yes",
        })
        self.assertEqual(response.status_code, 302)
        page = self.apply(batch, preview_token=old_token)
        self.assertIn("out of date", page.text)
        self.assertEqual(self.stock(), 5)

    def test_name_only_match_requires_explicit_inventory_selection(self):
        batch = self.upload([self.sale(ID="")])
        page = self.map(batch)
        self.assertIn("No unique exact match", page.text)
        self.apply(batch)
        self.assertEqual(self.stock(), 5)
        self.apply(batch, card_0=str(self.card_id))
        self.assertEqual(self.stock(), 3)

    def test_review_is_rejected_if_inventory_or_preview_changed(self):
        batch = self.upload([self.sale()])
        self.map(batch)
        with self.app.app_context():
            old_token = db.session.get(ReconciliationBatch, batch).preview_token
            card = db.session.get(Card, self.card_id)
            card.quantity = 4
            db.session.commit()
        self.apply(batch)
        self.assertEqual(self.stock(), 4)
        page = self.apply(batch, preview_token=old_token)
        self.assertIn("out of date", page.text)
        self.assertEqual(self.stock(), 4)

    def test_commit_failure_rolls_back_inventory_links_batch_and_ledger(self):
        batch = self.upload([self.sale()])
        self.map(batch)
        with self.app.app_context():
            obj = db.session.get(ReconciliationBatch, batch)
            form = {"preview_token": obj.preview_token, "confirmed": "yes", "apply_0": "yes"}
            with patch.object(db.session, "commit", side_effect=RuntimeError("failed")):
                with self.assertRaisesRegex(RuntimeError, "failed"):
                    apply_review(obj, form)
            self.assertEqual(db.session.get(Card, self.card_id).quantity, 5)
            self.assertEqual(GoalCardPrinting.query.filter_by(card_id=self.card_id).one().quantity, 5)
            self.assertEqual(ReconciliationEntry.query.count(), 0)
            self.assertEqual(db.session.get(ReconciliationBatch, batch).state, "review")

    def test_new_snapshot_printing_requires_cached_metadata(self):
        batch = self.upload([self.sale(ID=OTHER_ID)], source="collectr", kind="snapshot")
        self.map(batch)
        self.apply(batch)
        with self.app.app_context():
            self.assertEqual(Card.query.count(), 1)
        cache = Path(self.directory.name) / "scryfall"
        cache.mkdir(exist_ok=True)
        metadata = {"id": OTHER_ID, "name": "Other Card", "set": "tst", "set_name": "Test", "collector_number": "7", "rarity": "rare", "lang": "en", "finishes": ["nonfoil"], "games": ["paper"]}
        (cache / "scryfall-default-cards.json").write_text(json.dumps([metadata]), encoding="utf-8")
        self.client.get(f"/reconcile/{batch}/review")
        self.apply(batch)
        with self.app.app_context():
            self.assertEqual(Card.query.filter_by(scryfall_id=OTHER_ID).one().quantity, 2)

    def test_source_namespaces_keep_buylist_vendors_separate(self):
        for vendor in ("Store A", "Store B"):
            batch = self.upload([self.sale(amount=1)], source="buylist", source_account=vendor)
            self.map(batch)
            self.apply(batch)
        self.assertEqual(self.stock(), 3)

    def test_manual_cached_printing_match_is_previewed_before_application(self):
        batch = self.upload([self.sale(ID="")], basis="already_reflected")
        self.map(batch)
        cache = Path(self.directory.name) / "scryfall"
        cache.mkdir(exist_ok=True)
        metadata = {"id": OTHER_ID, "name": "Previously sold card", "set": "tst", "collector_number": "7", "lang": "en", "finishes": ["foil"], "games": ["paper"]}
        (cache / "scryfall-default-cards.json").write_text(json.dumps([metadata]), encoding="utf-8")
        page = self.client.post(f"/reconcile/{batch}/review", data={
            "csrf_token": self.csrf, "action": "match", "printing_0": OTHER_ID, "printing_finish_0": "foil",
        }, follow_redirects=True)
        self.assertIn("Previously sold card", page.text)
        with self.app.app_context():
            self.assertEqual(Card.query.count(), 1)
        self.apply(batch)
        with self.app.app_context():
            card = Card.query.filter_by(scryfall_id=OTHER_ID).one()
            self.assertEqual((card.quantity, card.finish), (0, "foil"))

    def test_already_reflected_absent_printing_is_recorded_at_zero_stock(self):
        cache = Path(self.directory.name) / "scryfall"
        cache.mkdir(exist_ok=True)
        metadata = {"id": OTHER_ID, "name": "Sold Card", "set": "tst", "set_name": "Test", "collector_number": "7", "rarity": "rare", "lang": "en", "finishes": ["nonfoil"], "games": ["paper"]}
        (cache / "scryfall-default-cards.json").write_text(json.dumps([metadata]), encoding="utf-8")
        for _ in range(2):
            batch = self.upload([self.sale(ID=OTHER_ID)], basis="already_reflected")
            self.map(batch)
            self.apply(batch)
        self.assertEqual(self.stock(), 5)
        with self.app.app_context():
            self.assertEqual(Card.query.filter_by(scryfall_id=OTHER_ID).one().quantity, 0)
            self.assertEqual(ReconciliationEntry.query.count(), 1)

    def test_csrf_is_required_and_export_is_downloadable(self):
        self.assertEqual(self.client.post("/reconcile", data={}).status_code, 400)
        response = self.client.get("/reconcile/inventory.csv")
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response.headers["Content-Disposition"])
        records = list(csv.DictReader(io.StringIO(response.text)))
        self.assertEqual(records[0]["Quantity"], "5")

    def test_multiple_historical_sales_create_only_one_absent_printing(self):
        cache = Path(self.directory.name) / "scryfall"
        cache.mkdir(exist_ok=True)
        metadata = {"id": OTHER_ID, "name": "Sold Card", "set": "tst", "collector_number": "7", "lang": "en", "finishes": ["nonfoil"], "games": ["paper"]}
        (cache / "scryfall-default-cards.json").write_text(json.dumps([metadata]), encoding="utf-8")
        batch = self.upload([self.sale(order, ID=OTHER_ID) for order in ("a", "b", "c")], basis="already_reflected")
        self.map(batch)
        page = self.apply(batch, rows=(0, 1, 2))
        self.assertIn("Reconciliation saved", page.text)
        with self.app.app_context():
            cards = Card.query.filter(Card.scryfall_id.startswith(OTHER_ID)).all()
            self.assertEqual(len(cards), 1)
            self.assertEqual(cards[0].quantity, 0)
            entries = ReconciliationEntry.query.order_by(ReconciliationEntry.id).all()
            self.assertEqual(len(entries), 3)
            self.assertEqual({entry.card_id for entry in entries}, {cards[0].id})
            self.assertEqual([(entry.before_quantity, entry.after_quantity) for entry in entries], [(0, 0)] * 3)
