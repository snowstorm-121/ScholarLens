"""Rank chunk embeddings for a query."""

import numpy as np


def cosine_scores(
    query_embedding: np.ndarray,
    embedding_matrix: np.ndarray,
) -> np.ndarray:
    normalized_query = query_embedding / np.linalg.norm(query_embedding)
    normalized_matrix = embedding_matrix / np.linalg.norm(
        embedding_matrix,
        axis=1,
        keepdims=True,
    )
    return normalized_matrix @ normalized_query


def top_k_results(
    query_embedding: np.ndarray,
    embedding_matrix: np.ndarray,
    chunks: list[dict],
    k: int,
) -> list[dict]:
    if len(chunks) != len(embedding_matrix):
        raise ValueError("chunk count and embedding rows differ")

    scores = cosine_scores(query_embedding, embedding_matrix)
    indices = np.argsort(-scores)[:k]
    return [
        {**chunks[index], "rank": rank, "score": float(scores[index])}
        for rank, index in enumerate(indices, start=1)
    ]
