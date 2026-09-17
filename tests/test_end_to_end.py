import unittest

import numpy as np

from rag.pipeline import answer_from_vectors


class EndToEndTests(unittest.TestCase):
    def test_answer_from_vectors_returns_auditable_record(self):
        chunks = [
            {
                "chunk_id": "rag-0001",
                "source_name": "rag.md",
                "text": "RAG 使用检索。",
            }
        ]

        record = answer_from_vectors(
            "RAG 是什么？",
            np.array([1.0, 0.0], dtype=np.float32),
            np.array([[1.0, 0.0]], dtype=np.float32),
            chunks,
            k=1,
        )

        self.assertEqual(record["retrieval_results"][0]["chunk_id"], "rag-0001")
        self.assertEqual(record["generator"], "mock")
        self.assertIn("[rag.md | rag-0001 | 1.0000]", record["context"])


if __name__ == "__main__":
    unittest.main()
