import gzip
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from cardchart.scryfall_bulk import (
    ScryfallBulkLookup,
    download_default_cards,
    read_bulk_lookup,
)


CARDS = [
    {
        "id": "printing-one",
        "set": "tst",
        "set_name": "Test Set",
        "collector_number": "1",
        "lang": "en",
        "games": ["paper"],
        "released_at": "2026-01-01",
    },
    {
        "id": "printing-two",
        "set": "TST",
        "set_name": "Test Set",
        "collector_number": "2",
        "lang": "en",
        "games": ["paper"],
        "released_at": "2026-01-01",
    },
]


class ScryfallBulkTests(unittest.TestCase):
    def test_reads_current_gzipped_json_lines_format(self):
        with tempfile.TemporaryDirectory() as directory:
            cards_path = Path(directory) / "cards.json"
            with gzip.open(cards_path, "wt", encoding="utf-8") as bulk_file:
                for card in CARDS:
                    bulk_file.write(json.dumps(card) + "\n")

            lookup = read_bulk_lookup(cards_path)

            self.assertEqual(lookup.find_by_id("printing-one"), CARDS[0])
            self.assertEqual(
                lookup.find_by_set_and_collector("tst", "2"), CARDS[1]
            )

    def test_keeps_reading_existing_json_array_caches(self):
        with tempfile.TemporaryDirectory() as directory:
            cards_path = Path(directory) / "cards.json"
            cards_path.write_text(json.dumps(CARDS), encoding="utf-8")

            lookup = read_bulk_lookup(cards_path)

            self.assertEqual(lookup.find_by_id("printing-two"), CARDS[1])

    def test_builds_a_paper_set_catalog_for_the_wizard(self):
        lookup = ScryfallBulkLookup(CARDS)

        self.assertEqual(
            lookup.set_catalog(),
            (
                {
                    "code": "tst",
                    "name": "Test Set",
                    "released_at": "2026-01-01",
                    "set_type": None,
                    "card_count": 2,
                },
            ),
        )

    @patch("cardchart.scryfall_bulk.requests.get")
    def test_downloads_current_json_lines_uri(self, get):
        response = Mock(content=b"compressed cards")
        response.raise_for_status.return_value = None
        get.return_value = response
        bulk_item = {
            "jsonl_download_uri": "https://data.scryfall.io/cards.jsonl.gz",
            "updated_at": "2026-08-14T21:05:38Z",
        }

        with tempfile.TemporaryDirectory() as directory:
            cards_path = Path(directory) / "cards.json"
            meta_path = Path(directory) / "cards.meta.json"

            download_default_cards(cards_path, meta_path, bulk_item)

            self.assertEqual(cards_path.read_bytes(), b"compressed cards")
            self.assertEqual(
                json.loads(meta_path.read_text(encoding="utf-8")),
                {
                    "download_uri": bulk_item["jsonl_download_uri"],
                    "updated_at": bulk_item["updated_at"],
                },
            )
            get.assert_called_once_with(
                bulk_item["jsonl_download_uri"],
                timeout=120,
                headers={
                    "User-Agent": "CardChart/0.1 (+local collection tracker)",
                    "Accept": "application/json;q=0.9,*/*;q=0.8",
                },
            )


if __name__ == "__main__":
    unittest.main()
