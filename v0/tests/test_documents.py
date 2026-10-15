import tempfile
import unittest
from pathlib import Path

from rag.documents import build_chunks, chunk_text, normalize_text


class DocumentTests(unittest.TestCase):
    def test_normalize_text_preserves_headings_and_collapses_blank_lines(self):
        self.assertEqual(
            normalize_text("\r\n# 标题\r\n\r\n\r\n正文  \r\n"),
            "# 标题\n\n正文",
        )

    def test_chunk_text_keeps_requested_overlap(self):
        chunks = chunk_text("abcdefghij", chunk_size=6, overlap=2)
        self.assertEqual(chunks, ["abcdef", "efghij"])

    def test_build_chunks_preserves_source_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "note.md"
            source.write_text("# 标题\n正文内容", encoding="utf-8")
            chunks = build_chunks([source], chunk_size=100, overlap=10)

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0]["source_name"], "note.md")
        self.assertEqual(chunks[0]["chunk_id"], "note-0001")


if __name__ == "__main__":
    unittest.main()
