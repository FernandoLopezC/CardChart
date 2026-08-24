import io
import unittest
from unittest.mock import patch

from werkzeug.datastructures import FileStorage

from cardchart import create_app
from cardchart.goal_definitions import (
    GOAL_DEFINITIONS,
    GoalDefinition,
    GoalEntryDefinition,
    GoalVersionDefinition,
    goal_entry_versions,
    japanese_mystical_archive,
    middle_earth_classic_artists,
    synchronize_goals,
)
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
        self.app = create_app(
            {
                "TESTING": True,
                "SQLALCHEMY_DATABASE_URI": "sqlite://",
                "MARKET_PRICING_ENABLED": False,
            }
        )
        with self.app.app_context():
            db.drop_all()
            db.create_all()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.drop_all()
            db.engine.dispose()

    def definition(self, accepted_id=PRINTING_ID):
        entries = (
            GoalEntryDefinition("one", "Test Card", (accepted_id,), collector_number="1"),
            GoalEntryDefinition("two", "Missing Card", (OTHER_ID,), collector_number="2"),
        )
        return GoalDefinition("test-goal", "Test Goal", "A test.", "tst", entries)

    def versioned_definition(self, slug="test-goal", finish="nonfoil"):
        version = GoalVersionDefinition(
            key=finish,
            label=finish.title(),
            scryfall_id=PRINTING_ID,
            collector_number="1",
            finish=finish,
            language="ja",
            set_code="tst",
        )
        entry = GoalEntryDefinition(
            "one",
            "Test Card",
            (PRINTING_ID,),
            collector_number="1",
            language="ja",
            set_code="tst",
            versions=(version,),
        )
        return GoalDefinition(slug, slug.title(), "A test.", "tst", (entry,))

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

    def test_synchronization_matches_existing_inventory_by_printing_and_finish(self):
        with self.app.app_context():
            inventory_card = Card(
                scryfall_id=PRINTING_ID,
                name="Test Card",
                set_code="tst",
                set_name="Test Set",
                collector_number="1",
                rarity="rare",
                finish="nonfoil",
                finish_display="Non-foil",
                quantity=2,
            )
            db.session.add(inventory_card)
            db.session.commit()

            matched = synchronize_goals((self.versioned_definition(),))

            goal = CollectionGoal.query.filter_by(slug="test-goal").one()
            printing = GoalCardPrinting.query.one()
            self.assertEqual(matched, 1)
            self.assertTrue(goal.cards[0].is_owned)
            self.assertEqual(printing.card_id, inventory_card.id)
            self.assertEqual(printing.quantity, 2)

            self.assertEqual(
                synchronize_goals((self.versioned_definition(),)), 0
            )
            self.assertEqual(GoalCardPrinting.query.count(), 1)

    def test_synchronization_rejects_an_unreviewed_finish(self):
        with self.app.app_context():
            db.session.add(
                Card(
                    scryfall_id=PRINTING_ID,
                    name="Test Card",
                    set_code="tst",
                    set_name="Test Set",
                    collector_number="1",
                    rarity="rare",
                    finish="foil",
                    finish_display="Foil",
                    quantity=1,
                )
            )
            db.session.commit()

            matched = synchronize_goals((self.versioned_definition(),))

            self.assertEqual(matched, 0)
            self.assertEqual(GoalCardPrinting.query.count(), 0)

    def test_synchronization_matches_finish_suffixed_inventory_ids(self):
        with self.app.app_context():
            db.session.add(
                Card(
                    scryfall_id=f"{PRINTING_ID}:foil",
                    name="Test Card",
                    set_code="tst",
                    set_name="Test Set",
                    collector_number="1",
                    rarity="rare",
                    finish="foil",
                    finish_display="Foil",
                    quantity=1,
                )
            )
            db.session.commit()

            matched = synchronize_goals(
                (self.versioned_definition(finish="foil"),)
            )

            self.assertEqual(matched, 1)
            self.assertEqual(GoalCardPrinting.query.one().scryfall_id, PRINTING_ID)

    def test_synchronization_does_not_overwrite_existing_ownership(self):
        with self.app.app_context():
            definition = self.versioned_definition()
            synchronize_goals((definition,))
            goal_card = CollectionGoal.query.filter_by(slug="test-goal").one().cards[0]
            existing = GoalCardPrinting(
                goal_card=goal_card,
                scryfall_id=PRINTING_ID,
                set_code="tst",
                collector_number="1",
                finish="nonfoil",
                language="ja",
                quantity=1,
                notes="Keep this record",
            )
            db.session.add(existing)
            db.session.add(
                Card(
                    scryfall_id=PRINTING_ID,
                    name="Test Card",
                    set_code="tst",
                    set_name="Test Set",
                    collector_number="1",
                    rarity="rare",
                    finish="nonfoil",
                    finish_display="Non-foil",
                    quantity=5,
                )
            )
            db.session.commit()

            matched = synchronize_goals((definition,))

            db.session.refresh(existing)
            self.assertEqual(matched, 0)
            self.assertIsNone(existing.card_id)
            self.assertEqual(existing.quantity, 1)
            self.assertEqual(existing.notes, "Keep this record")

    def test_curated_definitions_have_verified_order_and_unique_printings(self):
        hoc_entries = middle_earth_classic_artists.entries
        soa_entries = japanese_mystical_archive.entries

        self.assertEqual(
            [entry.collector_number for entry in hoc_entries],
            [str(number) for number in range(13, 53)],
        )
        self.assertEqual(
            [entry.collector_number for entry in soa_entries],
            [str(number) for number in range(66, 131)],
        )
        self.assertTrue(all(entry.language == "en" for entry in hoc_entries))
        self.assertTrue(all(entry.language == "ja" for entry in soa_entries))
        self.assertTrue(
            all(len(entry.accepted_scryfall_ids) == 2 for entry in (*hoc_entries, *soa_entries))
        )

        accepted_ids = [
            printing_id
            for entry in (*hoc_entries, *soa_entries)
            for printing_id in entry.accepted_scryfall_ids
        ]
        self.assertEqual(len(accepted_ids), len(set(accepted_ids)))

    def test_curated_definitions_populate_all_maintained_goals(self):
        with self.app.app_context():
            synchronize_goals()

            goals = {
                goal.slug: goal for goal in CollectionGoal.query.order_by(CollectionGoal.slug)
            }
            self.assertEqual(goals["middle-earth-classic-artists"].total_count, 40)
            self.assertEqual(goals["japanese-mystical-archive"].total_count, 65)
            self.assertEqual(len(goals), len(GOAL_DEFINITIONS))
            self.assertEqual(
                GoalCard.query.count(),
                sum(len(definition.entries) for definition in GOAL_DEFINITIONS),
            )

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

    def test_goal_grid_is_paginated(self):
        with self.app.app_context():
            synchronize_goals()
            client = self.app.test_client()

            first_page = client.get("/goals/japanese-mystical-archive")
            last_page = client.get("/goals/japanese-mystical-archive?page=4")

            self.assertEqual(first_page.data.count(b'<article class="collection-card'), 20)
            self.assertIn(b"Page 1 of 4", first_page.data)
            self.assertEqual(last_page.data.count(b'<article class="collection-card'), 5)
            self.assertIn(b"Page 4 of 4", last_page.data)

    def test_quick_update_selects_verified_special_version_and_status(self):
        with self.app.app_context():
            synchronize_goals()
            goal = CollectionGoal.query.filter_by(
                slug="middle-earth-classic-artists"
            ).one()
            card = goal.cards[0]
            versions = goal_entry_versions(goal.slug, card.stable_key)
            special = next(version for version in versions if version.key == "special")
            client = self.app.test_client()

            response = client.post(
                f"/goals/{goal.slug}/cards/{card.id}/quick-update",
                data={"version": "special", "status": "owned", "filter": "all", "page": "2"},
            )

            self.assertEqual(response.status_code, 302)
            self.assertIn("page=2", response.location)
            printing = GoalCardPrinting.query.filter_by(goal_card_id=card.id).one()
            self.assertEqual(printing.scryfall_id, special.scryfall_id)
            self.assertEqual(printing.collector_number, "53")
            self.assertEqual(printing.finish, "foil")
            self.assertTrue(card.is_owned)

            client.post(
                f"/goals/{goal.slug}/cards/{card.id}/quick-update",
                data={"version": "special", "status": "missing"},
            )
            self.assertFalse(card.is_owned)
            self.assertEqual(GoalCardPrinting.query.filter_by(goal_card_id=card.id).count(), 0)

    def test_grid_offers_goal_specific_version_labels(self):
        with self.app.app_context():
            synchronize_goals()
            client = self.app.test_client()

            hoc_page = client.get("/goals/middle-earth-classic-artists")
            soa_page = client.get("/goals/japanese-mystical-archive")

            self.assertIn(b"Non-foil", hoc_page.data)
            self.assertIn(b">Foil</option>", hoc_page.data)
            self.assertIn(b"Surge foil (special)", hoc_page.data)
            self.assertIn(b"Silver Scroll foil (special)", soa_page.data)

    def test_missing_card_image_links_to_selected_cardmarket_printing(self):
        with self.app.app_context():
            synchronize_goals()
            goal = CollectionGoal.query.filter_by(
                slug="middle-earth-classic-artists"
            ).one()
            card = goal.cards[0]
            versions = goal_entry_versions(goal.slug, card.stable_key)
            price_index = {
                versions[0].scryfall_id: {
                    "prices": {"eur": "10.00", "eur_foil": "12.00"},
                    "cardmarket_url": "https://cardmarket.example/base",
                },
                versions[-1].scryfall_id: {
                    "prices": {"eur": None, "eur_foil": "15.00"},
                    "cardmarket_url": "https://cardmarket.example/special",
                },
            }
            self.app.config["MARKET_PRICING_ENABLED"] = True

            with patch(
                "cardchart.routes.load_goal_price_index", return_value=price_index
            ), patch(
                "cardchart.routes.load_eur_to_gbp_rate",
                return_value={"rate": "0.85", "rate_date": "2026-08-14"},
            ):
                response = self.app.test_client().get(f"/goals/{goal.slug}")

            self.assertIn(b"\xe2\x89\x88 \xc2\xa38.50", response.data)
            self.assertIn(b'href="https://cardmarket.example/base"', response.data)
            self.assertIn(b'data-cardmarket-url="https://cardmarket.example/special"', response.data)

    def test_goal_totals_use_owned_printing_and_cheapest_missing_printings(self):
        with self.app.app_context():
            synchronize_goals()
            goal = CollectionGoal.query.filter_by(
                slug="middle-earth-classic-artists"
            ).one()
            first_card = goal.cards[0]
            first_version = goal_entry_versions(goal.slug, first_card.stable_key)[1]
            db.session.add(
                GoalCardPrinting(
                    goal_card=first_card,
                    scryfall_id=first_version.scryfall_id,
                    set_code="hoc",
                    collector_number=first_version.collector_number,
                    finish=first_version.finish,
                    language=first_version.language,
                    quantity=2,
                )
            )
            db.session.commit()

            price_index = {"ltr-cheaper-reprint": {"prices": {"eur": "0.01"}}}
            for card in goal.cards:
                versions = goal_entry_versions(goal.slug, card.stable_key)
                price_index[versions[0].scryfall_id] = {
                    "prices": {"eur": "10.00", "eur_foil": "12.00"}
                }
                price_index[versions[-1].scryfall_id] = {
                    "prices": {"eur_foil": "5.00"}
                }
            self.app.config["MARKET_PRICING_ENABLED"] = True

            with patch(
                "cardchart.routes.load_goal_price_index", return_value=price_index
            ), patch(
                "cardchart.routes.load_eur_to_gbp_rate",
                return_value={"rate": "0.85", "rate_date": "2026-08-14"},
            ):
                response = self.app.test_client().get(
                    f"/goals/{goal.slug}?filter=missing"
                )

            self.assertIn(b"Owned value", response.data)
            self.assertIn(b"Missing cost", response.data)
            self.assertIn(b"\xe2\x89\x88 \xc2\xa320.40", response.data)
            self.assertIn(b"\xe2\x89\x88 \xc2\xa3165.75", response.data)
            self.assertIn(
                b"Owned value uses each recorded printing, finish, and quantity",
                response.data,
            )
            self.assertIn(
                b"Missing cost uses the cheapest accepted HOC version", response.data
            )

    def test_cardmarket_wants_export_uses_missing_cards_and_exact_versions(self):
        with self.app.app_context():
            synchronize_goals()
            hoc_goal = CollectionGoal.query.filter_by(
                slug="middle-earth-classic-artists"
            ).one()
            first_card = hoc_goal.cards[0]
            first_version = goal_entry_versions(
                hoc_goal.slug, first_card.stable_key
            )[0]
            db.session.add(
                GoalCardPrinting(
                    goal_card=first_card,
                    scryfall_id=first_version.scryfall_id,
                    set_code="hoc",
                    collector_number=first_version.collector_number,
                    finish=first_version.finish,
                    language=first_version.language,
                    quantity=1,
                )
            )
            db.session.commit()
            client = self.app.test_client()

            hoc_export = client.get(
                "/goals/middle-earth-classic-artists/exports/cardmarket-wants.txt"
            )
            soa_export = client.get(
                "/goals/japanese-mystical-archive/exports/cardmarket-wants.txt"
            )
            hoc_page = client.get("/goals/middle-earth-classic-artists")

            hoc_lines = hoc_export.text.splitlines()
            soa_lines = soa_export.text.splitlines()
            self.assertEqual(len(hoc_lines), 39)
            self.assertNotIn("Dawn of a New Age", hoc_export.text)
            self.assertEqual(
                hoc_lines[0],
                "1x Flowering of the White Tree (V.1) (The Hobbit: Eternal)",
            )
            self.assertNotIn("Lord of the Rings", hoc_export.text)
            self.assertEqual(len(soa_lines), 65)
            self.assertEqual(
                soa_lines[0],
                "1x Akroma's Will (V.2) "
                "(Secrets of Strixhaven: Mystical Archive)",
            )
            self.assertIn(
                "middle-earth-classic-artists-cardmarket-wants.txt",
                hoc_export.headers["Content-Disposition"],
            )
            self.assertIn(b"Export 39 missing cards for Cardmarket", hoc_page.data)

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

    def test_imported_printing_can_satisfy_more_than_one_goal(self):
        with self.app.app_context(), patch(
            "cardchart.importer.load_scryfall_bulk_lookup",
            return_value=BulkLookup(PRINTING_ID),
        ):
            synchronize_goals(
                (
                    self.definition(),
                    GoalDefinition(
                        "second-goal",
                        "Second Goal",
                        "Another test.",
                        "tst",
                        (
                            GoalEntryDefinition(
                                "one",
                                "Test Card",
                                (PRINTING_ID,),
                                collector_number="1",
                            ),
                        ),
                    ),
                )
            )

            result = import_cards(self.csv_file())

            self.assertEqual(result.goal_matches, 2)
            self.assertEqual(GoalCardPrinting.query.count(), 2)

    def test_same_name_unaccepted_printing_does_not_match(self):
        with self.app.app_context(), patch(
            "cardchart.importer.load_scryfall_bulk_lookup", return_value=BulkLookup(UNACCEPTED_ID)
        ):
            self.sync()
            result = import_cards(self.csv_file(UNACCEPTED_ID))
            self.assertEqual(result.goal_matches, 0)
            self.assertEqual(GoalCardPrinting.query.count(), 0)

    def test_import_does_not_match_an_unreviewed_finish(self):
        with self.app.app_context(), patch(
            "cardchart.importer.load_scryfall_bulk_lookup",
            return_value=BulkLookup(PRINTING_ID),
        ), patch(
            "cardchart.importer.goal_entry_versions",
            return_value=self.versioned_definition().entries[0].versions,
        ):
            self.sync()
            foil_csv = self.csv_file()
            foil_csv.stream = io.BytesIO(
                (
                    CSV_HEADER
                    + f"{PRINTING_ID},Test Card,TST,Test Set,1,rare,foil,Foil,1\n"
                ).encode()
            )

            result = import_cards(foil_csv)

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

    def test_inventory_uses_exact_printing_finish_and_quantity(self):
        with self.app.app_context():
            card = Card(
                scryfall_id=PRINTING_ID,
                name="Test Foil",
                set_code="tst",
                set_name="Test",
                collector_number="1",
                rarity="rare",
                finish="foil",
                finish_display="Foil",
                quantity=2,
            )
            db.session.add(card)
            db.session.commit()
            self.app.config["MARKET_PRICING_ENABLED"] = True

            with patch(
                "cardchart.routes.load_scryfall_price_index",
                return_value={
                    PRINTING_ID: {
                        "prices": {"eur": "10.00", "eur_foil": "12.00"}
                    }
                },
            ), patch(
                "cardchart.routes.load_eur_to_gbp_rate",
                return_value={"rate": "0.85", "rate_date": "2026-08-14"},
            ):
                response = self.app.test_client().get("/inventory")

            self.assertIn(b"Inventory guide value", response.data)
            self.assertIn(b"Scryfall guide", response.data)
            self.assertIn(b"\xe2\x89\x88 \xc2\xa310.20", response.data)
            self.assertIn(b"\xe2\x89\x88 \xc2\xa320.40", response.data)
            self.assertIn(b"exact Scryfall printing and finish", response.data)

    def test_inventory_paginates_searches_and_sorts(self):
        with self.app.app_context():
            for number in range(25):
                db.session.add(
                    Card(
                        scryfall_id=f"inventory-{number}",
                        name=f"Card {number:02d}",
                        set_code="tst" if number != 7 else "find",
                        set_name="Test Set" if number != 7 else "Find Me Set",
                        collector_number=str(number),
                        rarity="common",
                        finish="nonfoil",
                        finish_display="Non-foil",
                        quantity=number + 1,
                    )
                )
            db.session.commit()
            client = self.app.test_client()

            first_page = client.get("/inventory")
            second_page = client.get("/inventory?page=2")
            search = client.get("/inventory?q=Find+Me")
            descending = client.get("/inventory?sort=name-desc")

            self.assertEqual(first_page.data.count(b'<article class="card-tile">'), 20)
            self.assertIn(b"25 matching cards \xc2\xb7 Page 1 of 2", first_page.data)
            self.assertEqual(second_page.data.count(b'<article class="card-tile">'), 5)
            self.assertIn(b"Card 07", search.data)
            self.assertNotIn(b"Card 08", search.data)
            self.assertLess(descending.data.index(b"Card 24"), descending.data.index(b"Card 23"))

    def test_inventory_sorts_priced_lines_by_quantity_adjusted_value(self):
        with self.app.app_context():
            cards = (
                Card(scryfall_id="low", name="Low", set_code="tst", set_name="Test",
                     collector_number="1", rarity="common", finish="nonfoil",
                     finish_display="Non-foil", quantity=1),
                Card(scryfall_id="high", name="High", set_code="tst", set_name="Test",
                     collector_number="2", rarity="common", finish="nonfoil",
                     finish_display="Non-foil", quantity=3),
                Card(scryfall_id="missing", name="Missing Price", set_code="tst", set_name="Test",
                     collector_number="3", rarity="common", finish="nonfoil",
                     finish_display="Non-foil", quantity=1),
            )
            db.session.add_all(cards)
            db.session.commit()
            self.app.config["MARKET_PRICING_ENABLED"] = True

            with patch(
                "cardchart.routes.load_scryfall_price_index",
                return_value={
                    "low": {"prices": {"eur": "8.00"}},
                    "high": {"prices": {"eur": "4.00"}},
                },
            ), patch(
                "cardchart.routes.load_eur_to_gbp_rate",
                return_value={"rate": "1.00", "rate_date": "2026-08-14"},
            ):
                response = self.app.test_client().get("/inventory?sort=price-desc")

            self.assertLess(response.data.index(b"High"), response.data.index(b"Low"))
            self.assertLess(response.data.index(b"Low"), response.data.index(b"Missing Price"))


if __name__ == "__main__":
    unittest.main()
