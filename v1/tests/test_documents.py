import sys
import unittest
from pathlib import Path


V1_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V1_ROOT))

from rag.documents import build_chunks, extract_normalized_text


class ExtractNormalizedTextTests(unittest.TestCase):
    def test_extracts_qwen_article_role_main(self) -> None:
        html = "<article role='main'><h1>Quickstart</h1><p>A &amp; B</p></article>"

        self.assertEqual(extract_normalized_text(html), "Quickstart\n\nA & B\n")

    def test_preserves_code_block_indentation(self) -> None:
        html = "<main><p>Run this:</p><pre><code>if True:\n    print('ok')</code></pre></main>"

        self.assertEqual(
            extract_normalized_text(html),
            "Run this:\n\nif True:\n    print('ok')\n",
        )

    def test_builds_chunks_with_normalized_spans(self) -> None:
        chunks = build_chunks("example", "abcdefghij", chunk_size=6, overlap=2)

        self.assertEqual(
            [(chunk["normalized_start"], chunk["normalized_end"]) for chunk in chunks],
            [(0, 6), (4, 10)],
        )
        self.assertEqual([chunk["text"] for chunk in chunks], ["abcdef", "efghij"])


if __name__ == "__main__":
    unittest.main()
