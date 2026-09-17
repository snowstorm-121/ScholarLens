import unittest

import numpy as np

from rag.retrieval import cosine_scores, top_k_results


class RetrievalTests(unittest.TestCase):
    def test_top_k_rejects_mismatched_chunk_and_vector_counts(self):
        with self.assertRaisesRegex(ValueError, "chunk count and embedding rows differ"):
            top_k_results(
                np.array([1.0, 0.0], dtype=np.float32),
                np.array([[1.0, 0.0]], dtype=np.float32),
                [],
                k=1,
            )

    def test_top_k_returns_highest_score_first_with_source(self):
        matrix = np.array(
            [[1.0, 0.0], [0.0, 1.0], [0.8, 0.6]],
            dtype=np.float32,
        )
        query = np.array([1.0, 0.0], dtype=np.float32)
        chunks = [
            {"chunk_id": "a", "source_name": "a.md", "text": "A"},
            {"chunk_id": "b", "source_name": "b.md", "text": "B"},
            {"chunk_id": "c", "source_name": "c.md", "text": "C"},
        ]

        self.assertEqual(cosine_scores(query, matrix).shape, (3,))
        results = top_k_results(query, matrix, chunks, k=2)

        self.assertEqual([item["chunk_id"] for item in results], ["a", "c"])
        self.assertEqual(results[0]["rank"], 1)
        self.assertEqual(results[0]["source_name"], "a.md")


if __name__ == "__main__":
    unittest.main()
