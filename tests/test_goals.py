import io
import unittest
from unittest.mock import patch

from werkzeug.datastructures import FileStorage

from cardchart import create_app
from cardchart.goal_definitions import GoalDefinition, GoalEntryDefinition, synchronize_goals
from cardchart.importer import import_cards
from cardchart.models import Card, CollectionGoal, GoalCard, GoalCardPrinting, db


PRINTING_ID = "11111111-1111-4111-8111-111111111111"
OTHER_ID = "22222222-2222-4222-8222-222222222222"
UNACCEPTED_ID = "33333333-3333-4333-8333-333333333333"
CSV_HEADER = "Card Scryfall ID,Name,Set Code,Set Name,Collector Number,Rarity,Finish,Finish Display,Quantity\n"


class BulkLookup:
    def __init__(self, printing_id):
        self.printing_id = printing_id

    def find_by_id(self, _printing_id):
        return {
            "id": self.printing_id,
            "name": "Test Card",
            "set": "tst",
            "collector_number": "1",
            "lang": "ja",
        }

    def find_by_set_and_collector(self, _set_code, _collector_number):
        return None


class GoalTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI="sqlite://")
        with self.app.app_context():
            db.drop_all()
            db.create_all()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()

    def definition(self, accepted_id=PRINTING_ID):
        entries = (
            GoalEntryDefinition("one", "Test Card", (accepted_id,), collector_number="1"),
            GoalEntryDefinition("two", "Missing Card", (OTHER_ID,), collector_number="2"),
        )
        return GoalDefinition("test-goal", "Test Goal", "A test.", "tst", entries)

    def sync(self):
        synchronize_goals((self.definition(),))
        return CollectionGoal.query.filter_by(slug="test-goal").one()

    def add_printing(self, card, finish="nonfoil"):
        printing = GoalCardPrinting(
            goal_card=card,
            scryfall_id=PRINTING_ID,
            set_code="tst",
            collector_number="1",
            finish=finish,
            language="ja",
            quantity=1,
        )
        db.session.add(printing)
        db.session.commit()
        return printing

    def csv_file(self, printing_id=PRINTING_ID):
        row = f"{printing_id},Test Card,TST,Test Set,1,rare,nonfoil,Non-foil,1\n"
        return FileStorage(stream=io.BytesIO((CSV_HEADER + row).encode()))

    def test_synchronization_is_idempotent_and_preserves_ownership(self):
        with self.app.app_context():
            goal = self.sync()
            self.add_printing(goal.cards[0])
            synchronize_goals((self.definition(),))
            self.assertEqual(CollectionGoal.query.count(), 1)
            self.assertEqual(GoalCard.query.count(), 2)
            self.assertEqual(GoalCardPrinting.query.count(), 1)

    def test_progress_zero_partial_and_complete(self):
        with self.app.app_context():
            goal = self.sync()
            self.assertEqual((goal.percentage, goal.state), (0, "Not started"))
            self.add_printing(goal.cards[0])
            self.assertEqual((goal.percentage, goal.state), (50, "In progress"))
            self.add_printing(goal.cards[1])
            self.assertEqual((goal.percentage, goal.state), (100, "Complete"))

    def test_missing_cards_and_filters_are_visible(self):
        with self.app.app_context():
            goal = self.sync()
            self.add_printing(goal.cards[0])
            client = self.app.test_client()
            self.assertIn(b"Missing Card", client.get("/goals/test-goal").data)
            self.assertNotIn(b"Test Card</h2>", client.get("/goals/test-goal?filter=missing").data)
            self.assertNotIn(b"Missing Card", client.get("/goals/test-goal?filter=owned").data)

    def test_editor_updates_one_checklist_entry(self):
        with self.app.app_context():
            goal = self.sync()
            card = goal.cards[0]
            response = self.app.test_client().post(
                f"/goals/test-goal/cards/{card.id}",
                data={"status": "owned", "scryfall_id": PRINTING_ID, "set_code": "tst",
                      "collector_number": "1", "language": "ja", "finish": "foil",
                      "quantity": "1", "acquired_at": "", "notes": ""},
            )
            self.assertEqual(response.status_code, 302)
            self.assertEqual(GoalCard.query.count(), 2)
            self.assertEqual(card.printings[0].finish, "foil")

    def test_multiple_finishes_are_allowed(self):
        with self.app.app_context():
            card = self.sync().cards[0]
            self.add_printing(card, "nonfoil")
            self.add_printing(card, "foil")
            self.assertEqual(GoalCardPrinting.query.count(), 2)

    def test_explicit_import_match_updates_goal(self):
        with self.app.app_context(), patch(
            "cardchart.importer.load_scryfall_bulk_lookup", return_value=BulkLookup(PRINTING_ID)
        ):
            self.sync()
            result = import_cards(self.csv_file())
            self.assertEqual(result.goal_matches, 1)
            self.assertEqual(GoalCardPrinting.query.one().card.name, "Test Card")

    def test_same_name_unaccepted_printing_does_not_match(self):
        with self.app.app_context(), patch(
            "cardchart.importer.load_scryfall_bulk_lookup", return_value=BulkLookup(UNACCEPTED_ID)
        ):
            self.sync()
            result = import_cards(self.csv_file(UNACCEPTED_ID))
            self.assertEqual(result.goal_matches, 0)
            self.assertEqual(GoalCardPrinting.query.count(), 0)

    def test_csv_only_import_keeps_warning_when_enrichment_fails(self):
        with self.app.app_context(), patch(
            "cardchart.importer.load_scryfall_bulk_lookup", return_value=None
        ), patch("cardchart.importer.fetch_scryfall_card", return_value=None):
            result = import_cards(self.csv_file())
            self.assertEqual(Card.query.count(), 1)
            self.assertIn("without Scryfall enrichment", result.warnings[-1])
            self.assertEqual(result.goal_matches, 0)

    def test_inventory_and_card_detail_routes_remain_available(self):
        with self.app.app_context():
            card = Card(scryfall_id=PRINTING_ID, name="Test Card", set_code="tst",
                        set_name="Test", collector_number="1", rarity="rare",
                        finish="nonfoil", finish_display="Non-foil", quantity=1)
            db.session.add(card)
            db.session.commit()
            client = self.app.test_client()
            self.assertEqual(client.get("/inventory").status_code, 200)
            self.assertEqual(client.get(f"/cards/{card.id}").status_code, 200)


if __name__ == "__main__":
    unittest.main()
