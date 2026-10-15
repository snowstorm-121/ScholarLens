import json
import sys
from pathlib import Path


V1_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(V1_ROOT))

from rag.documents import extract_normalized_text


MANIFEST_PATH = V1_ROOT / "corpus" / "manifest.jsonl"
NORMALIZED_DIR = V1_ROOT / "corpus" / "normalized"


def load_manifest() -> list[dict]:
    return [
        json.loads(line)
        for line in MANIFEST_PATH.read_text(encoding="utf-8").splitlines()
        if line
    ]


def normalize_corpus() -> dict:
    normalized_documents = []
    for record in load_manifest():
        raw_path = V1_ROOT / record["local_path"]
        html = raw_path.read_text(encoding="utf-8")
        text = extract_normalized_text(html)
        normalized_documents.append((record["doc_id"], text))

    NORMALIZED_DIR.mkdir(parents=True, exist_ok=True)
    for doc_id, text in normalized_documents:
        (NORMALIZED_DIR / f"{doc_id}.txt").write_text(text, encoding="utf-8")

    return {
        "documents": len(normalized_documents),
        "characters": sum(len(text) for _, text in normalized_documents),
    }


def main() -> None:
    summary = normalize_corpus()
    print(f"documents={summary['documents']} characters={summary['characters']}")


if __name__ == "__main__":
    main()
