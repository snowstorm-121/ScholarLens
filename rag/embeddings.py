"""Create and persist embedding vectors."""

from pathlib import Path

import numpy as np


def encode_texts(model, texts: list[str]) -> np.ndarray:
    return np.asarray(
        model.encode(texts, normalize_embeddings=True),
        dtype=np.float32,
    )


def save_embeddings(path: Path, matrix: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.save(path, np.asarray(matrix, dtype=np.float32))


def load_embeddings(path: Path) -> np.ndarray:
    return np.load(path).astype(np.float32, copy=False)
