import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from typer.testing import CliRunner

from bgrules import bgg, config, rag, scraper
from bgrules.db import Base
from bgrules.main import app


class DebugModeTests(unittest.TestCase):
    def test_is_debug_mode_reads_current_sys_argv(self):
        original_argv = list(config.sys.argv)
        try:
            config.sys.argv[:] = ["bgrules"]
            self.assertFalse(config.is_debug_mode())

            config.sys.argv.append("--debug")
            self.assertTrue(config.is_debug_mode())
        finally:
            config.sys.argv[:] = original_argv

    def test_scraper_debug_print_responds_to_runtime_debug_flag(self):
        original_argv = list(config.sys.argv)
        try:
            config.sys.argv[:] = ["bgrules"]
            quiet = io.StringIO()
            with redirect_stdout(quiet):
                scraper.debug_print("hidden")
            self.assertEqual("", quiet.getvalue())

            config.sys.argv.append("--debug")
            loud = io.StringIO()
            with redirect_stdout(loud):
                scraper.debug_print("shown")
            self.assertIn("shown", loud.getvalue())
        finally:
            config.sys.argv[:] = original_argv


class RagIndexingTests(unittest.TestCase):
    def test_chunk_text_splits_long_text_into_overlapping_chunks(self):
        text = "A" * 1800 + "B" * 1800

        chunks = rag._chunk_text(text, chunk_size=1500, chunk_overlap=200)

        self.assertGreater(len(chunks), 2)
        self.assertEqual(1500, len(chunks[0]))
        self.assertTrue(chunks[1].startswith("A" * 200))

    def test_build_game_index_indexes_multiple_chunks(self):
        class FakeIndex:
            def __init__(self, texts):
                self.texts = texts
                self.saved_to = None

            def save_local(self, path):
                self.saved_to = path

        class FakeFAISS:
            captured_texts = None

            @classmethod
            def from_texts(cls, texts, embeddings):
                cls.captured_texts = list(texts)
                return FakeIndex(texts)

        long_text = "Rule section. " * 400

        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = Path(tmpdir) / "rules.pdf"
            pdf_path.write_bytes(b"%PDF-1.4 fake")

            with patch.object(rag, "FAISS_INDEX_DIR", tmpdir), \
                 patch.object(rag, "_load_faiss", return_value=FakeFAISS), \
                 patch("bgrules.rag.ParserAgent") as parser_cls:
                parser_cls.return_value.run.return_value = long_text

                index = rag._build_game_index("game-stem", pdf_path, "Test Game", object())

        self.assertIsNotNone(index)
        self.assertIsNotNone(FakeFAISS.captured_texts)
        self.assertGreater(len(FakeFAISS.captured_texts), 1)


class RagCliMessageTests(unittest.TestCase):
    def test_interactive_rag_pdf_hint_mentions_game_name_not_flag(self):
        output = io.StringIO()
        with patch("bgrules.rag.build_retriever", return_value=object()), \
             patch("builtins.input", side_effect=["pdf", "exit"]), \
             redirect_stdout(output):
            rag.interactive_rag(game=None)

        rendered = output.getvalue()
        self.assertIn("'pdf' is only available when a single game name is provided.", rendered)
        self.assertNotIn("--game", rendered)


class BoardGameGeekStorageTests(unittest.TestCase):
    def test_save_and_load_game_info_round_trip(self):
        engine = create_engine("sqlite:///:memory:")
        TestingSession = sessionmaker(bind=engine)
        Base.metadata.create_all(engine)

        info = bgg.BoardGameGeekInfo(
            game_name="Catan",
            bgg_id=13,
            bgg_name="CATAN",
            year_published=1995,
            average_rating=7.11,
            min_players=3,
            max_players=4,
            playing_time_minutes=60,
            average_weight=2.32,
            fetched_at="2026-04-01T00:00:00+00:00",
        )

        bgg.save_game_info(info, session_factory=TestingSession)
        stored = bgg.get_saved_game_info("Catan", session_factory=TestingSession)

        self.assertIsNotNone(stored)
        self.assertEqual(13, stored.bgg_id)
        self.assertEqual("CATAN", stored.bgg_name)
        self.assertEqual(60, stored.playing_time_minutes)
        self.assertAlmostEqual(2.32, stored.average_weight)


class BoardGameGeekApiAuthTests(unittest.TestCase):
    def test_request_xml_requires_configured_token(self):
        with patch("bgrules.bgg.BGG_API_TOKEN", ""):
            with self.assertRaisesRegex(bgg.BoardGameGeekError, "requires an API token"):
                bgg._request_xml("https://example.com", {})

    def test_request_xml_rewrites_401_as_actionable_error(self):
        response = mock.Mock(status_code=401)
        response.raise_for_status.side_effect = RuntimeError("should not be called")

        with patch("bgrules.bgg.BGG_API_TOKEN", "token"), \
             patch("bgrules.bgg.requests.get", return_value=response):
            with self.assertRaisesRegex(bgg.BoardGameGeekError, "rejected the API token"):
                bgg._request_xml("https://example.com", {})


class InfoCliTests(unittest.TestCase):
    def test_info_command_renders_live_boardgamegeek_data(self):
        runner = CliRunner()
        fake_record = bgg.BoardGameGeekInfo(
            game_name="Catan",
            bgg_id=13,
            bgg_name="CATAN",
            year_published=1995,
            average_rating=7.11,
            min_players=3,
            max_players=4,
            playing_time_minutes=60,
            average_weight=2.32,
            fetched_at="2026-04-01T00:00:00+00:00",
        )

        with patch("bgrules.bgg.fetch_and_store_game_info", return_value=fake_record):
            result = runner.invoke(app, ["info", "Catan"])

        self.assertEqual(0, result.exit_code)
        self.assertIn("Game: CATAN (1995)", result.output)
        self.assertIn("Players: 3-4", result.output)
        self.assertIn("Weight: 2.32/5", result.output)
        self.assertIn("Source: BoardGameGeek", result.output)

    def test_info_command_falls_back_to_cached_data(self):
        runner = CliRunner()

        class CachedRecord:
            bgg_id = 13
            bgg_name = "CATAN"
            year_published = 1995
            average_rating = 7.11
            min_players = 3
            max_players = 4
            playing_time_minutes = 60
            average_weight = 2.32

        with patch("bgrules.bgg.fetch_and_store_game_info", side_effect=RuntimeError("network down")), \
             patch("bgrules.bgg.get_saved_game_info", return_value=CachedRecord()):
            result = runner.invoke(app, ["info", "Catan"])

        self.assertEqual(0, result.exit_code)
        self.assertIn("using stored data", result.output)
        self.assertIn("Source: local cache", result.output)


if __name__ == "__main__":
    unittest.main()
