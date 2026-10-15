import json
import tempfile
import unittest
from pathlib import Path

from rag.generation import MockGenerator
from rag.pipeline import build_context, build_prompt, save_query_record


class PipelineTests(unittest.TestCase):
    def test_record_contains_query_context_prompt_answer_and_sources(self):
        results = [
            {
                "chunk_id": "rag-0001",
                "source_name": "rag.md",
                "score": 0.9,
                "text": "RAG 使用检索上下文。",
            }
        ]

        context = build_context(results)
        prompt = build_prompt("RAG 是什么？", context)
        answer = MockGenerator().generate(prompt, results)
        record = {
            "query": "RAG 是什么？",
            "retrieval_results": results,
            "context": context,
            "prompt": prompt,
            "answer": answer,
            "generator": "mock",
        }

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "query.json"
            save_query_record(path, record)
            restored = json.loads(path.read_text(encoding="utf-8"))

        self.assertIn("[rag.md | rag-0001 | 0.9000]", restored["context"])
        self.assertIn("仅依据以下上下文", restored["prompt"])
        self.assertEqual(restored["retrieval_results"][0]["chunk_id"], "rag-0001")
        self.assertIn("mock", restored["answer"])


if __name__ == "__main__":
    unittest.main()
