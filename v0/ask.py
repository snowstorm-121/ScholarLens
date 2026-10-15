"""Query the local RAG index and save an auditable mock answer."""

import argparse
import json
from pathlib import Path
from uuid import uuid4

from rag.embeddings import encode_texts, load_embeddings
from rag.pipeline import answer_from_vectors, save_query_record

MODEL_NAME = "BAAI/bge-small-zh-v1.5"
PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"


def ask(query: str, data_dir: Path, model, *, top_k: int = 3) -> dict:
    if not query.strip():
        raise ValueError("query must not be empty")
    if top_k <= 0:
        raise ValueError("top-k must be positive")

    chunks_path = data_dir / "chunks.jsonl"
    matrix_path = data_dir / "embeddings.npy"
    if not chunks_path.exists() or not matrix_path.exists():
        raise FileNotFoundError("build the index before asking a question")

    chunks = [
        json.loads(line)
        for line in chunks_path.read_text(encoding="utf-8").splitlines()
    ]
    matrix = load_embeddings(matrix_path)
    if len(chunks) != matrix.shape[0]:
        raise ValueError("chunk count and embedding rows differ")

    query_embedding = encode_texts(model, [query])[0]
    record = answer_from_vectors(
        query,
        query_embedding,
        matrix,
        chunks,
        k=min(top_k, len(chunks)),
    )
    record["query_embedding_shape"] = list(query_embedding.shape)
    record["scores_shape"] = [int(matrix.shape[0])]
    return record


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("query")
    parser.add_argument("--top-k", type=int, default=3)
    args = parser.parse_args()

    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(MODEL_NAME, device="cpu", local_files_only=True)
    record = ask(args.query, DATA_DIR, model, top_k=args.top_k)
    artifact_path = PROJECT_ROOT / "artifacts" / "queries" / f"{uuid4().hex}.json"
    save_query_record(artifact_path, record)

    print(f"query_embedding_shape={tuple(record['query_embedding_shape'])}")
    print(f"scores_shape={tuple(record['scores_shape'])}")
    for item in record["retrieval_results"]:
        print(
            f"rank={item['rank']} score={item['score']:.4f} "
            f"source={item['source_name']} chunk={item['chunk_id']}"
        )
    print("context:\n" + record["context"])
    print("prompt:\n" + record["prompt"])
    print("answer:\n" + record["answer"])
    print(f"artifact={artifact_path}")


if __name__ == "__main__":
    main()
