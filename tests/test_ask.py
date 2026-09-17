import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from ask import ask


class FakeQueryModel:
    def encode(self, texts, normalize_embeddings):
        self.texts = texts
        self.normalize_embeddings = normalize_embeddings
        return np.array([[1.0, 0.0]], dtype=np.float32)


class AskTests(unittest.TestCase):
    def test_ask_loads_index_and_returns_auditable_record(self):
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory) / "data"
            data_dir.mkdir()
            (data_dir / "chunks.jsonl").write_text(
                json.dumps(
                    {
                        "chunk_id": "rag-0001",
                        "source_name": "rag.md",
                        "text": "RAG 使用检索。",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )
            np.save(data_dir / "embeddings.npy", np.array([[1.0, 0.0]], dtype=np.float32))
            model = FakeQueryModel()

            record = ask("RAG 是什么？", data_dir, model, top_k=1)

        self.assertEqual(model.texts, ["RAG 是什么？"])
        self.assertTrue(model.normalize_embeddings)
        self.assertEqual(record["retrieval_results"][0]["chunk_id"], "rag-0001")
        self.assertEqual(record["generator"], "mock")
        self.assertEqual(record["query_embedding_shape"], [2])
        self.assertEqual(record["scores_shape"], [1])


if __name__ == "__main__":
    unittest.main()
