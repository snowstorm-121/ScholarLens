"""Build the local RAG index from the approved source notes."""

import json
from pathlib import Path

from rag.documents import build_chunks
from rag.embeddings import encode_texts, save_embeddings

MODEL_NAME = "BAAI/bge-small-zh-v1.5"
PROJECT_ROOT = Path(__file__).resolve().parent
DATA_DIR = PROJECT_ROOT / "data"
SOURCE_PATHS = [
    Path(
        "/Users/yyy/Documents/知识库/Notes/Pytorch学习/stage6/"
        "Stage 6 学习笔记：RAG 理论学习与复盘.md"
    ),
    Path(
        "/Users/yyy/Documents/知识库/Notes/Pytorch学习/stage5/"
        "Stage 5 学习笔记：BERT 全量微调与 LoRA 参数高效微调对比实验.md"
    ),
    Path(
        "/Users/yyy/Documents/知识库/Notes/Pytorch学习/stage4/"
        "Day 3 学习笔记：HuggingFace BERT tokenizer 与 DataLoader.md"
    ),
    Path(
        "/Users/yyy/Documents/知识库/Notes/Pytorch学习/stage4/"
        "Day 1 学习笔记：Attention 机制原理——Scaled Dot-Product Attention.md"
    ),
]


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


def main() -> None:
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(MODEL_NAME, device="cpu", local_files_only=True)
    summary = build_index(SOURCE_PATHS, DATA_DIR, model, model_name=MODEL_NAME)
    print(f"chunks={summary['chunk_count']}")
    print(f"embedding_shape={summary['embedding_shape']}")
    print(f"data_dir={DATA_DIR}")


if __name__ == "__main__":
    main()
