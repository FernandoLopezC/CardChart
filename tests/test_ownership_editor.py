import unittest
from datetime import date
from unittest.mock import patch

from cardchart import create_app
from cardchart.goal_definitions import goal_entry_versions
from cardchart.importer import match_goal_printings
from cardchart.models import Card, CollectionGoal, GoalCardPrinting, PriceSnapshot, db
from cardchart.routes import goal_price_summary


class OwnershipEditorTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite://", "MARKET_PRICING_ENABLED": False})
        self.context = self.app.app_context()
        self.context.push()
        self.client = self.app.test_client()
        self.goal = CollectionGoal.query.filter_by(slug="middle-earth-classic-artists").one()
        self.entry = self.goal.cards[0]
        versions = goal_entry_versions(self.goal.slug, self.entry.stable_key)
        self.version, self.other = versions[0], versions[-1]
        self.path = f"/goals/{self.goal.slug}/cards/{self.entry.id}"
        self.client.get(self.path + "/edit")
        with self.client.session_transaction() as session:
            self.token = session["reconciliation_csrf"]

    def tearDown(self):
        db.session.remove()
        db.engine.dispose()
        self.context.pop()

    def save(self, **changes):
        data = {"csrf_token": self.token, "status": "owned", "version": self.version.key, "quantity": "3", "acquired_at": "2026-01-01", "notes": "Keep this"}
        data.update(changes)
        return self.client.post(self.path, data=data, follow_redirects=True)

    def inventory(self, version=None):
        version = version or self.version
        card = Card(scryfall_id=version.scryfall_id + ":" + version.finish, name=self.entry.name, set_code=version.set_code, set_name="Test", collector_number=version.collector_number, rarity="rare", finish=version.finish, finish_display=version.label, quantity=4)
        db.session.add(card)
        db.session.commit()
        return card

    def test_accepted_edit_preserves_other_printings_and_ownership_details(self):
        self.save()
        first = GoalCardPrinting.query.one()
        self.save(version=self.other.key, quantity="2", notes="Other version")
        other = GoalCardPrinting.query.filter_by(finish=self.other.finish).one()
        inventory = self.inventory(self.other)
        response = self.save(printing_id=str(other.id), version=self.other.key, card_id=str(inventory.id), notes="Linked copy")
        self.assertIn("Ownership updated", response.text)
        db.session.refresh(first)
        db.session.refresh(other)
        self.assertEqual((first.quantity, first.notes, first.acquired_at), (3, "Keep this", date(2026, 1, 1)))
        self.assertEqual((other.quantity, other.card_id, other.notes), (4, inventory.id, "Linked copy"))
        page = self.client.get(self.path + f"/edit?printing_id={other.id}")
        self.assertIn(f'name="printing_id" value="{other.id}"', page.text)
        self.assertIn("Other ownership records", page.text)

    def test_rejects_invalid_inputs_without_mutating_existing_record(self):
        self.save()
        printing = GoalCardPrinting.query.one()
        unrelated = self.inventory(self.other)
        for changes in ({"version": "invented"}, {"quantity": "0"}, {"quantity": "bad"}, {"acquired_at": "bad"}, {"card_id": "bad"}, {"card_id": "999999"}, {"card_id": str(unrelated.id)}):
            with self.subTest(changes=changes):
                response = self.save(printing_id=str(printing.id), notes="Overwrite", **changes)
                self.assertIn("Ownership was not changed", response.text)
                db.session.refresh(printing)
                self.assertEqual((printing.quantity, printing.notes, printing.acquired_at, printing.card_id), (3, "Keep this", date(2026, 1, 1), None))
        self.assertEqual(self.client.post(self.path, data={"status": "missing"}).status_code, 400)
        self.assertEqual(GoalCardPrinting.query.count(), 1)

    def test_duplicate_identity_is_rejected_without_merging_records(self):
        self.save()
        first = GoalCardPrinting.query.one()
        self.save(version=self.other.key)
        response = self.save(printing_id=str(first.id), version=self.other.key)
        self.assertIn("already has an ownership record", response.text)
        self.assertEqual(GoalCardPrinting.query.count(), 2)
        db.session.refresh(first)
        self.assertEqual(first.scryfall_id, self.version.scryfall_id)

    def test_legacy_uppercase_identity_is_recognized_without_duplicate_ownership(self):
        self.save()
        printing = GoalCardPrinting.query.one()
        printing.scryfall_id = printing.scryfall_id.upper()
        printing.finish = printing.finish.upper()
        printing.language = printing.language.upper()
        db.session.commit()
        page = self.client.get(self.path + "/edit")
        self.assertNotIn("outside the goal", page.text)
        self.assertIn("already has an ownership record", self.save().text)
        self.assertEqual(GoalCardPrinting.query.count(), 1)
        index = {self.version.scryfall_id: {"prices": {"eur": "10"}}}
        self.assertEqual(goal_price_summary([self.entry], index, {"rate": "1"})["owned"]["gbp"], "30.00")
        self.client.post(self.path + "/quick-update", data={"status": "owned", "version": self.version.key})
        self.assertEqual(GoalCardPrinting.query.count(), 1)
        self.assertEqual(printing.quantity, 3)
        printing.scryfall_id = printing.scryfall_id.upper()
        printing.finish = printing.finish.upper()
        printing.language = printing.language.upper()
        inventory = self.inventory()
        matched = match_goal_printings(inventory, self.version.scryfall_id,
            {"Finish": self.version.finish, "Quantity": "4", "Set Code": self.version.set_code, "Collector Number": self.version.collector_number},
            {"lang": self.version.language, "set": self.version.set_code, "collector_number": self.version.collector_number})
        db.session.commit()
        self.assertEqual(matched, 1)
        self.assertEqual(GoalCardPrinting.query.count(), 1)
        self.assertEqual((printing.quantity, printing.notes), (4, "Keep this"))

    def test_unaccepted_records_remain_but_progress_export_and_values_agree(self):
        old = GoalCardPrinting(goal_card=self.entry, scryfall_id="unaccepted", set_code="old", collector_number="1", finish="nonfoil", language="en", quantity=7, notes="Keep legacy record", acquired_at=date(2025, 1, 1))
        db.session.add(old)
        db.session.commit()
        self.assertFalse(self.entry.is_owned)
        self.assertEqual(self.goal.owned_count, 0)
        index = {self.version.scryfall_id: {"prices": {"eur": "10"}}}
        summary = goal_price_summary([self.entry], index, {"rate": "1"})
        self.assertEqual(summary["missing"]["gbp"], "10.00")
        self.assertIn(self.entry.name, self.client.get(f"/goals/{self.goal.slug}/exports/cardmarket-wants.txt").text)
        self.assertIn("kept for review", self.client.get(self.path + "/edit").text)
        self.save()
        self.assertTrue(self.entry.is_owned)
        self.assertEqual(goal_price_summary([self.entry], index, {"rate": "1"})["owned"]["gbp"], "30.00")
        self.assertEqual((old.quantity, old.notes, old.acquired_at), (7, "Keep legacy record", date(2025, 1, 1)))

    def test_scrapers_retired_archive_and_scryfall_download_remain(self):
        card = self.inventory()
        price = PriceSnapshot(card=card, source="cardmarket_uk", price_gbp=12, source_url="https://example.test", title="Archived listing")
        db.session.add(price)
        db.session.commit()
        with patch("requests.get") as network:
            self.assertEqual(self.client.post(f"/cards/{card.id}/refresh").status_code, 404)
            page = self.client.get(f"/cards/{card.id}")
            network.assert_not_called()
        self.assertIn("Archived listing", page.text)
        self.assertIn("currency uncertain", page.text)
        self.assertIn("Refresh guides", page.text)
        self.assertNotIn("Run legacy price check", page.text)
        self.assertEqual(PriceSnapshot.query.count(), 1)
        with patch("cardchart.goal_cli.load_bulk_lookup") as download:
            download.return_value.cards = [1, 2]
            result = self.app.test_cli_runner().invoke(args=["goals", "refresh-bulk"])
        self.assertEqual(result.exit_code, 0)
        download.assert_called_once_with(refresh=True)
        self.assertIn("2 cards", result.output)


if __name__ == "__main__":
    unittest.main()
