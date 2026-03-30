import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from bgrules import config, rag, scraper


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


if __name__ == "__main__":
    unittest.main()
