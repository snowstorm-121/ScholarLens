"""Build a local RAG index from Markdown or text documents."""

import argparse
import json
from pathlib import Path

from rag.documents import build_chunks
from rag.embeddings import encode_texts, save_embeddings

MODEL_NAME = "BAAI/bge-small-zh-v1.5"
PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a traceable local RAG index.",
    )
    parser.add_argument(
        "sources",
        nargs="+",
        type=Path,
        help="Markdown or text documents to index.",
    )
    parser.add_argument(
        "--local-files-only",
        action="store_true",
        help="Load the embedding model only from the local cache.",
    )
    return parser.parse_args(argv)


def build_index(
    source_paths: list[Path],
    data_dir: Path,
    model,
    *,
    model_name: str,
    chunk_size: int = 500,
    overlap: int = 80,
) -> dict:
    chunks = build_chunks(source_paths, chunk_size=chunk_size, overlap=overlap)
    if not chunks:
        raise ValueError("no non-empty chunks were built")

    matrix = encode_texts(model, [chunk["text"] for chunk in chunks])
    if matrix.ndim != 2 or matrix.shape[0] != len(chunks):
        raise ValueError("embedding rows must match the chunk count")

    data_dir.mkdir(parents=True, exist_ok=True)
    chunks_path = data_dir / "chunks.jsonl"
    chunks_path.write_text(
        "\n".join(json.dumps(chunk, ensure_ascii=False) for chunk in chunks) + "\n",
        encoding="utf-8",
    )
    save_embeddings(data_dir / "embeddings.npy", matrix)
    manifest = {
        "model_name": model_name,
        "device": "cpu",
        "source_paths": [str(path) for path in source_paths],
        "chunk_size": chunk_size,
        "overlap": overlap,
        "chunk_count": len(chunks),
        "vector_dimension": int(matrix.shape[1]),
    }
    (data_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {"chunk_count": len(chunks), "embedding_shape": tuple(matrix.shape)}


def load_model(local_files_only: bool):
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(
        MODEL_NAME,
        device="cpu",
        local_files_only=local_files_only,
    )


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    model = load_model(args.local_files_only)
    summary = build_index(args.sources, DATA_DIR, model, model_name=MODEL_NAME)
    print(f"chunks={summary['chunk_count']}")
    print(f"embedding_shape={summary['embedding_shape']}")
    print(f"data_dir={DATA_DIR}")


if __name__ == "__main__":
    main()
