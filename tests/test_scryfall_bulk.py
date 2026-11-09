import gzip
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import os
import requests
from flask import Flask

from cardchart.scryfall_bulk import (
    CACHE_JSON,
    CACHE_META,
    ScryfallBulkLookup,
    bulk_cards_path,
    download_default_cards,
    load_bulk_lookup,
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
        "prices": {"eur": "0.00", "eur_foil": None},
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
        content = gzip.compress(b"\n".join(json.dumps(card).encode() for card in CARDS) + b"\n")
        response = Mock(content=content)
        response.raise_for_status.return_value = None
        get.return_value = response
        bulk_item = {
            "jsonl_download_uri": "https://data.scryfall.io/cards.jsonl.gz",
            "updated_at": "2026-08-14T21:05:38Z",
        }

        with tempfile.TemporaryDirectory() as directory:
            cards_path = Path(directory) / CACHE_JSON
            meta_path = Path(directory) / CACHE_META

            download_default_cards(cards_path, meta_path, bulk_item)

            generation_path = bulk_cards_path(cards_path.parent)
            self.assertEqual(generation_path.read_bytes(), content)
            self.assertEqual(read_bulk_lookup(generation_path).find_by_id("printing-one"), CARDS[0])
            metadata = json.loads(meta_path.read_text(encoding="utf-8"))
            self.assertEqual(metadata["download_uri"], bulk_item["jsonl_download_uri"])
            self.assertEqual(metadata["updated_at"], bulk_item["updated_at"])
            self.assertEqual(metadata["cache_file"], generation_path.name)
            get.assert_called_once_with(
                bulk_item["jsonl_download_uri"],
                timeout=120,
                headers={
                    "User-Agent": "CardChart/0.1 (+local collection tracker)",
                    "Accept": "application/json;q=0.9,*/*;q=0.8",
                },
            )

    @patch("cardchart.scryfall_bulk.fetch_default_cards_bulk_item")
    @patch("cardchart.scryfall_bulk.requests.get")
    def test_unchanged_upstream_generation_is_not_downloaded_again(self, get, fetch):
        content = gzip.compress(b"\n".join(json.dumps(card).encode() for card in CARDS) + b"\n")
        response = Mock(content=content)
        response.raise_for_status.return_value = None
        get.return_value = response
        item = {
            "jsonl_download_uri": "https://data.scryfall.io/cards.jsonl.gz",
            "updated_at": "2026-08-14T21:05:38Z",
        }
        fetch.return_value = item
        with tempfile.TemporaryDirectory() as directory:
            app = Flask(__name__, instance_path=directory)
            with app.app_context():
                first = load_bulk_lookup()
                second = load_bulk_lookup()
        self.assertEqual(first.find_by_id("printing-one"), second.find_by_id("printing-one"))
        get.assert_called_once()
        self.assertEqual(fetch.call_count, 2)

    def test_failed_downloads_preserve_published_generation_and_metadata(self):
        valid = gzip.compress(b"\n".join(json.dumps(card).encode() for card in CARDS) + b"\n")
        item = {
            "jsonl_download_uri": "https://data.scryfall.io/cards.jsonl.gz",
            "updated_at": "2026-08-14T21:05:38Z",
        }
        failures = (
            ("timeout", None, requests.Timeout("timed out")),
            ("malformed", b"not json", None),
            ("truncated", valid[:-8], None),
            ("invalid cards", gzip.compress(b"[]"), None),
        )
        for name, content, error in failures:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                cache_dir = Path(directory)
                cards_path = cache_dir / "scryfall-default-cards.json"
                meta_path = cache_dir / "scryfall-default-cards.meta.json"
                response = Mock(content=valid)
                response.raise_for_status.return_value = None
                with patch("cardchart.scryfall_bulk.requests.get", return_value=response):
                    download_default_cards(cards_path, meta_path, item)
                old_metadata = meta_path.read_bytes()
                old_generation = bulk_cards_path(cache_dir)
                if error:
                    outcome = patch("cardchart.scryfall_bulk.requests.get", side_effect=error)
                else:
                    outcome = patch("cardchart.scryfall_bulk.requests.get", return_value=Mock(content=content, raise_for_status=Mock()))
                with outcome, self.assertRaises((OSError, ValueError, EOFError)):
                    download_default_cards(cards_path, meta_path, {**item, "updated_at": "2026-08-15T00:00:00Z"})
                self.assertEqual(meta_path.read_bytes(), old_metadata)
                self.assertEqual(bulk_cards_path(cache_dir), old_generation)
                self.assertEqual(read_bulk_lookup(old_generation).find_by_id("printing-one"), CARDS[0])

    @patch("cardchart.scryfall_bulk.requests.get")
    def test_metadata_publication_failure_keeps_previous_generation_active(self, get):
        old_content = gzip.compress(json.dumps(CARDS[0]).encode() + b"\n")
        new_content = gzip.compress(json.dumps(CARDS[1]).encode() + b"\n")
        item = {"jsonl_download_uri": "https://data.scryfall.io/cards.jsonl.gz", "updated_at": "2026-01-01T00:00:00Z"}
        with tempfile.TemporaryDirectory() as directory:
            cache_dir = Path(directory)
            cards_path = cache_dir / "scryfall-default-cards.json"
            meta_path = cache_dir / "scryfall-default-cards.meta.json"
            response = Mock(content=old_content)
            response.raise_for_status.return_value = None
            get.return_value = response
            download_default_cards(cards_path, meta_path, item)
            previous_metadata = meta_path.read_bytes()
            previous_generation = bulk_cards_path(cache_dir)
            response.content = new_content
            real_replace = os.replace

            def fail_metadata_replace(source, destination):
                if Path(destination) == meta_path:
                    raise OSError("metadata disk error")
                return real_replace(source, destination)

            with patch("cardchart.scryfall_bulk.os.replace", side_effect=fail_metadata_replace):
                with self.assertRaises(OSError):
                    download_default_cards(cards_path, meta_path, {**item, "updated_at": "2026-01-02T00:00:00Z"})
            self.assertEqual(meta_path.read_bytes(), previous_metadata)
            self.assertEqual(bulk_cards_path(cache_dir), previous_generation)
            self.assertEqual(read_bulk_lookup(previous_generation).find_by_id("printing-one"), CARDS[0])


if __name__ == "__main__":
    unittest.main()
