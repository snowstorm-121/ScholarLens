import tempfile
import unittest
from pathlib import Path

import numpy as np

from rag.embeddings import encode_texts, load_embeddings, save_embeddings


class FakeEmbeddingModel:
    def __init__(self):
        self.texts = None
        self.normalize_embeddings = None

    def encode(self, texts, normalize_embeddings):
        self.texts = texts
        self.normalize_embeddings = normalize_embeddings
        return [[3.0, 4.0], [0.0, 1.0]]


class EmbeddingTests(unittest.TestCase):
    def test_encode_texts_returns_float32_matrix_and_requests_normalization(self):
        model = FakeEmbeddingModel()

        matrix = encode_texts(model, ["第一个 chunk", "第二个 chunk"])

        self.assertEqual(model.texts, ["第一个 chunk", "第二个 chunk"])
        self.assertTrue(model.normalize_embeddings)
        self.assertEqual(matrix.dtype, np.float32)
        self.assertEqual(matrix.shape, (2, 2))

    def test_saved_embeddings_round_trip_as_float32(self):
        matrix = np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "embeddings.npy"
            save_embeddings(path, matrix)
            restored = load_embeddings(path)

        self.assertEqual(restored.dtype, np.float32)
        np.testing.assert_array_equal(restored, matrix)


if __name__ == "__main__":
    unittest.main()
