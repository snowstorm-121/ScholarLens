import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from build_index import build_index, parse_args


class FakeEmbeddingModel:
    def encode(self, texts, normalize_embeddings):
        self.assertTrue(normalize_embeddings)
        return np.ones((len(texts), 2), dtype=np.float32)

    def assertTrue(self, value):
        if not value:
            raise AssertionError("expected normalized embeddings")


class BuildIndexTests(unittest.TestCase):
    def test_parse_args_accepts_multiple_sources_and_offline_mode(self):
        args = parse_args(
            ["--local-files-only", "first.md", "second.txt"],
        )

        self.assertEqual(args.sources, [Path("first.md"), Path("second.txt")])
        self.assertTrue(args.local_files_only)

        online_args = parse_args(["first.md"])
        self.assertFalse(online_args.local_files_only)

    def test_build_index_writes_aligned_chunks_vectors_and_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "note.md"
            source.write_text("# 标题\nRAG 使用检索。", encoding="utf-8")
            data_dir = root / "data"

            summary = build_index(
                [source],
                data_dir,
                FakeEmbeddingModel(),
                model_name="fake-model",
                chunk_size=100,
                overlap=10,
            )

            chunks = [
                json.loads(line)
                for line in (data_dir / "chunks.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            matrix = np.load(data_dir / "embeddings.npy")
            manifest = json.loads(
                (data_dir / "manifest.json").read_text(encoding="utf-8")
            )

        self.assertEqual(summary["chunk_count"], 1)
        self.assertEqual(len(chunks), matrix.shape[0])
        self.assertEqual(matrix.shape, (1, 2))
        self.assertEqual(manifest["model_name"], "fake-model")
        self.assertEqual(manifest["vector_dimension"], 2)


if __name__ == "__main__":
    unittest.main()
