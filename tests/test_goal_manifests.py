import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cardchart import create_app
from cardchart.goal_authoring import (
    build_candidate_preview,
    card_treatment_labels,
    validate_definitions_against_bulk,
)
from cardchart.goal_definitions import (
    GoalManifestError,
    cardmarket_wants_mapping,
    parse_goal_manifest,
    unregister_goal_definition,
)
from cardchart.models import Card, CollectionGoal, db
from cardchart.scryfall_bulk import ScryfallBulkLookup


PRINTING_ID = "11111111-1111-4111-8111-111111111111"
SECOND_PRINTING_ID = "22222222-2222-4222-8222-222222222222"
ORACLE_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
SECOND_ORACLE_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"


def manifest_data():
    return {
        "schema_version": 1,
        "position": 10,
        "slug": "test-goal",
        "title": "Test Goal",
        "description": "A curated test goal.",
        "defaults": {"set_code": "tst", "language": "en"},
        "cardmarket": {
            "expansion": "Test Expansion",
            "default_version": "V.1",
            "wants_list_version_key": "nonfoil",
        },
        "entries": [
            {
                "key": "tst-1",
                "name": "Test Card",
                "oracle_id": ORACLE_ID,
                "collector_number": "1",
                "versions": [
                    {
                        "key": "nonfoil",
                        "label": "Non-foil",
                        "scryfall_id": PRINTING_ID,
                        "finish": "nonfoil",
                    },
                    {
                        "key": "special",
                        "label": "Special foil",
                        "scryfall_id": SECOND_PRINTING_ID,
                        "collector_number": "2",
                        "finish": "foil",
                    },
                ],
            }
        ],
    }


def bulk_cards():
    return [
        {
            "id": PRINTING_ID,
            "oracle_id": ORACLE_ID,
            "name": "Test Card",
            "set": "tst",
            "collector_number": "1",
            "lang": "en",
            "finishes": ["nonfoil"],
            "games": ["paper"],
            "image_uris": {"normal": "https://cards.example/test.jpg"},
        },
        {
            "id": SECOND_PRINTING_ID,
            "oracle_id": ORACLE_ID,
            "name": "Test Card",
            "set": "tst",
            "collector_number": "2",
            "lang": "en",
            "finishes": ["foil"],
            "games": ["paper"],
        },
    ]


class GoalManifestTests(unittest.TestCase):
    def test_manifest_declares_versions_and_cardmarket_default(self):
        definition = parse_goal_manifest(manifest_data())
        entry = definition.entries[0]

        self.assertEqual(entry.accepted_scryfall_ids, (PRINTING_ID, SECOND_PRINTING_ID))
        self.assertEqual([version.key for version in entry.versions], ["nonfoil", "special"])
        self.assertEqual(
            cardmarket_wants_mapping(definition, entry),
            ("V.1", "Test Expansion"),
        )
        self.assertEqual(definition.position, 10)

    def test_manifest_rejects_duplicate_printings_across_entries(self):
        data = manifest_data()
        duplicate = json.loads(json.dumps(data["entries"][0]))
        duplicate["key"] = "tst-2"
        duplicate["versions"] = duplicate["versions"][:1]
        data["entries"].append(duplicate)

        with self.assertRaisesRegex(GoalManifestError, "belongs to both"):
            parse_goal_manifest(data)

    def test_manifest_rejects_incomplete_or_mistyped_version_data(self):
        data = manifest_data()
        data["entries"][0]["versions"][0]["wants_list_default"] = "yes"

        with self.assertRaisesRegex(GoalManifestError, "must be true or false"):
            parse_goal_manifest(data)

    def test_bulk_validation_checks_locked_metadata(self):
        definition = parse_goal_manifest(manifest_data())
        cards = bulk_cards()
        cards[1]["collector_number"] = "99"

        errors = validate_definitions_against_bulk(
            (definition,), ScryfallBulkLookup(cards)
        )

        self.assertEqual(len(errors), 1)
        self.assertIn("collector number", errors[0])

    def test_treatment_preview_uses_public_scryfall_metadata(self):
        card = bulk_cards()[0]
        card.update(
            {
                "promo_types": ["sourcematerial", "universesbeyond"],
                "frame_effects": ["showcase", "legendary"],
                "border_color": "borderless",
                "full_art": True,
            }
        )

        labels = card_treatment_labels(card)
        preview = build_candidate_preview([card], "tst")

        self.assertEqual(
            labels,
            ("Source material", "Showcase", "Borderless", "Full art"),
        )
        self.assertEqual(preview["entries"][0]["treatment_keys"][0], "source-material")
        self.assertEqual(preview["treatments"][0]["label"], "Borderless")

    def test_live_preview_route_returns_grouped_cards_and_treatments(self):
        app = create_app(
            {
                "TESTING": True,
                "SQLALCHEMY_DATABASE_URI": "sqlite://",
                "MARKET_PRICING_ENABLED": False,
            }
        )
        card = bulk_cards()[0]
        card["promo_types"] = ["sourcematerial"]
        try:
            with patch(
                "cardchart.routes.load_bulk_lookup",
                return_value=ScryfallBulkLookup([card]),
            ):
                response = app.test_client().get(
                    "/goals/new/preview?set_code=tst&language=en"
                )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json["entries"][0]["name"], "Test Card")
            self.assertEqual(
                response.json["treatments"][0]["label"], "Source material"
            )
        finally:
            with app.app_context():
                db.session.remove()
                db.engine.dispose()

    def test_scaffold_uses_local_bulk_and_writes_review_candidate(self):
        app = create_app(
            {
                "TESTING": True,
                "SQLALCHEMY_DATABASE_URI": "sqlite://",
                "MARKET_PRICING_ENABLED": False,
            }
        )
        cards = bulk_cards()[:1]
        cards[0]["finishes"] = ["nonfoil", "foil"]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "candidate.json"
            with patch(
                "cardchart.goal_cli.load_bulk_lookup",
                return_value=ScryfallBulkLookup(cards),
            ):
                result = app.test_cli_runner().invoke(
                    args=[
                        "goals",
                        "scaffold",
                        "--slug",
                        "new-goal",
                        "--title",
                        "New Goal",
                        "--description",
                        "A new curated goal.",
                        "--set-code",
                        "tst",
                        "--cardmarket-expansion",
                        "Test Expansion",
                        "--cardmarket-version",
                        "V.1",
                        "--output",
                        str(output),
                    ]
                )

            self.assertEqual(result.exit_code, 0, result.output)
            candidate = json.loads(output.read_text(encoding="utf-8"))
            definition = parse_goal_manifest(candidate)
            self.assertEqual(len(definition.entries), 1)
            self.assertEqual(
                [version.key for version in definition.entries[0].versions],
                ["nonfoil", "foil"],
            )
            self.assertTrue(
                definition.entries[0].versions[0].wants_list_default
            )
        with app.app_context():
            db.session.remove()
            db.engine.dispose()

    def test_scaffold_refuses_existing_candidate_without_truncating_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = create_app(
                {
                    "TESTING": True,
                    "SQLALCHEMY_DATABASE_URI": "sqlite://",
                    "MARKET_PRICING_ENABLED": False,
                }
            )
            app.instance_path = str(root)
            cards = bulk_cards()[:1]
            cases = [root / "explicit.json", root / "goal-candidates" / "new-goal.json"]
            for index, output in enumerate(cases):
                output.parent.mkdir(parents=True, exist_ok=True)
                original = b"reviewed candidate must survive\n"
                output.write_bytes(original)
                args = [
                    "goals", "scaffold", "--slug", "new-goal", "--title", "New Goal",
                    "--description", "A new curated goal.", "--set-code", "tst",
                ]
                if index == 0:
                    args += ["--output", str(output)]
                with patch(
                    "cardchart.goal_cli.load_bulk_lookup",
                    return_value=ScryfallBulkLookup(cards),
                ):
                    result = app.test_cli_runner().invoke(args=args)
                self.assertNotEqual(result.exit_code, 0)
                self.assertIn("Candidate output already exists", result.output)
                self.assertEqual(output.read_bytes(), original)
            with app.app_context():
                db.session.remove()
                db.engine.dispose()

    def test_ui_creates_reviews_and_activates_a_goal(self):
        cards = bulk_cards()
        cards[1].update(
            {
                "oracle_id": SECOND_ORACLE_ID,
                "name": "Other Card",
            }
        )
        lookup = ScryfallBulkLookup(cards)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = create_app(
                {
                    "TESTING": True,
                    "SQLALCHEMY_DATABASE_URI": "sqlite://",
                    "MARKET_PRICING_ENABLED": False,
                    "GOAL_DRAFT_DIRECTORY": root / "drafts",
                }
            )
            client = app.test_client()
            try:
                with app.app_context():
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
                            quantity=3,
                        )
                    )
                    db.session.commit()
                self.assertIn(b"Add goal", client.get("/goals").data)
                with patch(
                    "cardchart.routes.load_bulk_lookup", return_value=lookup
                ):
                    candidate_response = client.post(
                        "/goals/new",
                        data={
                            "slug": "ui-goal",
                            "title": "UI Goal",
                            "description": "Created through the UI.",
                            "set_code": "tst",
                            "language": "en",
                            "collector_from": "",
                            "collector_to": "",
                            "metadata_filters": "",
                            "cardmarket_expansion": "Test Expansion",
                            "cardmarket_version": "V.1",
                            "selected_entry_keys": '["tst-1"]',
                        },
                    )

                self.assertEqual(candidate_response.status_code, 302)
                review_url = candidate_response.location
                review_page = client.get(review_url)
                self.assertIn(b"Review UI Goal", review_page.data)
                self.assertIn(b"1 candidate cards", review_page.data)
                self.assertNotIn(b"Other Card", review_page.data)
                with patch(
                    "cardchart.routes.load_bulk_lookup", return_value=lookup
                ):
                    self.assertIn(
                        b"Nothing becomes active", client.get("/goals/new").data
                    )

                with patch(
                    "cardchart.routes.load_bulk_lookup", return_value=lookup
                ), patch(
                    "cardchart.goal_authoring.MANIFEST_DIRECTORY",
                    root / "manifests",
                ):
                    activation = client.post(
                        review_url,
                        data={
                            "title": "UI Goal",
                            "description": "Created through the UI.",
                            "include_entry_0": "yes",
                            "entry_name_0": "Test Card",
                            "treatment_0": "Reviewed treatment",
                            "include_version_0_0": "yes",
                            "version_label_0_0": "Non-foil",
                            "wants_default_0": "0",
                        },
                    )

                self.assertEqual(activation.status_code, 302)
                self.assertTrue((root / "manifests" / "ui-goal.json").exists())
                with app.app_context():
                    goal = CollectionGoal.query.filter_by(slug="ui-goal").one()
                    self.assertEqual(goal.total_count, 1)
                    self.assertEqual(goal.owned_count, 1)
                    self.assertEqual(goal.cards[0].printings[0].quantity, 3)
                goal_page = client.get(activation.location)
                self.assertIn(b"UI Goal", goal_page.data)
                self.assertIn(b"Test Card", goal_page.data)
                self.assertIn(b"Found 1 already owned", goal_page.data)

                conflict = client.post(
                    "/goals/new",
                    data={
                        "slug": "ui-goal",
                        "title": "Duplicate UI Goal",
                        "description": "Must remain inactive.",
                        "set_code": "tst",
                        "language": "en",
                    },
                )
                self.assertEqual(conflict.status_code, 200)
                self.assertIn(b"already exists", conflict.data)
                with app.app_context():
                    self.assertEqual(
                        CollectionGoal.query.filter_by(slug="ui-goal").count(), 1
                    )
            finally:
                unregister_goal_definition("ui-goal")
                with app.app_context():
                    db.session.remove()
                    db.drop_all()
                    db.engine.dispose()


if __name__ == "__main__":
    unittest.main()
