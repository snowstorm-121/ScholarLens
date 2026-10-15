import hashlib
import json
from datetime import date
from pathlib import Path
from urllib.request import Request, urlopen


V1_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = V1_ROOT / "corpus" / "manifest.jsonl"
RAW_DIR = V1_ROOT / "corpus" / "raw"


def load_manifest(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def download(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "rag-minimal-v1-corpus-fetcher/1.0"})
    with urlopen(request, timeout=30) as response:
        return response.read()


def fetch_corpus() -> dict:
    records = load_manifest(MANIFEST_PATH)
    snapshot = f"snapshot-{date.today().isoformat()}"
    downloaded = []

    for record in records:
        content = download(record["source_url"])
        digest = sha256_bytes(content)
        expected_digest = record["sha256"]
        if expected_digest is not None and expected_digest != digest:
            raise ValueError(
                f"hash mismatch for {record['doc_id']}: "
                f"expected {expected_digest}, got {digest}"
            )

        path = V1_ROOT / record["local_path"]
        if RAW_DIR not in path.resolve().parents:
            raise ValueError(f"local_path must be inside corpus/raw: {record['local_path']}")
        downloaded.append((record, content, digest, path))

    for _, content, digest, path in downloaded:
        if path.exists() and sha256_bytes(path.read_bytes()) != digest:
            raise ValueError(f"local file differs from downloaded source: {path}")

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    created = 0
    for record, content, digest, path in downloaded:
        if not path.exists():
            path.write_bytes(content)
            created += 1
        record["revision"] = record["revision"] or snapshot
        record["sha256"] = digest

    MANIFEST_PATH.write_text(
        "\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n",
        encoding="utf-8",
    )
    return {"records": len(records), "created": created, "snapshot": snapshot}


def main() -> None:
    summary = fetch_corpus()
    print(
        f"records={summary['records']} created={summary['created']} "
        f"snapshot={summary['snapshot']}"
    )


if __name__ == "__main__":
    main()
