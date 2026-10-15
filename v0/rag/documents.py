"""Load, normalize, chunk, and describe local documents."""

from pathlib import Path
import re


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    if chunk_size <= 0 or overlap < 0 or overlap >= chunk_size:
        raise ValueError("chunk_size must be positive and overlap must be smaller")

    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])
        if end == len(text):
            break
        start += chunk_size - overlap
    return chunks


def build_chunks(
    source_paths: list[Path],
    chunk_size: int = 500,
    overlap: int = 80,
) -> list[dict]:
    chunks = []
    for source_path in source_paths:
        source_path = Path(source_path)
        if source_path.suffix.lower() not in {".md", ".txt"}:
            raise ValueError(f"unsupported source extension: {source_path}")

        text = normalize_text(source_path.read_text(encoding="utf-8"))
        for index, chunk in enumerate(
            chunk_text(text, chunk_size, overlap),
            start=1,
        ):
            chunks.append(
                {
                    "chunk_id": f"{source_path.stem}-{index:04d}",
                    "source_path": str(source_path),
                    "source_name": source_path.name,
                    "chunk_index": index,
                    "text": chunk,
                }
            )
    return chunks
