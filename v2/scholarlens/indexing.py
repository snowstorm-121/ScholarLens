"""QASPER body-only reader and position-preserving character chunking."""

import hashlib
import json
from importlib.metadata import version
from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter

from .data import NORMALIZATION, sha256, validate_spans, write_json


ROOT = Path(__file__).resolve().parents[1]


def index_context(config_path=None):
    path = Path(config_path or ROOT / "configs/local.json").resolve()
    config = json.loads(path.read_text())
    corpus = path.parent.parent / config["output_dir"]
    manifest = json.loads((corpus / "corpus_manifest.json").read_text())
    for name in ("papers.jsonl", "paragraphs.jsonl"):
        if sha256(corpus / name) != manifest["outputs"][name]:
            raise ValueError(f"Corpus changed: {name}")
    descriptor = {"schema": "scholarlens-index-v1", "normalization": NORMALIZATION,
                  "corpus_sha256": sha256(corpus / "corpus_manifest.json"),
                  "splitter": "RecursiveCharacterTextSplitter", "splitter_version": version("langchain-text-splitters"),
                  "chunk_size": config["index"]["chunk_size"], "overlap": config["index"]["overlap"],
                  "embedding": config["index"]["embedding"],
                  "prefixes": {"document": "search_document: ", "query": "search_query: "},
                  "vectors": "float32, full dimension, L2-normalized", "space": "squared_l2",
                  "bm25_version": version("rank-bm25")}
    digest = hashlib.sha256(json.dumps(descriptor, sort_keys=True).encode()).hexdigest()
    return path.parent.parent, config, corpus, {"fingerprint": digest, **descriptor}


def paper_chunks(paper, paragraphs, chunk_size=1600, overlap=200):
    if set(paper) != {"paper_id", "split", "title", "abstract", "normalized_text", "source_url",
                      "section_count", "paragraph_ids", "text_sha256"}:
        raise ValueError("Index input must be a body-only exported paper, not a QA object")
    if not 0 <= overlap < chunk_size:
        raise ValueError("Invalid character chunk size/overlap")
    if [p["paragraph_id"] for p in paragraphs] != paper["paragraph_ids"]:
        raise ValueError("Paragraph sequence does not match paper")
    validate_spans(paper, paragraphs, [])
    splitter = RecursiveCharacterTextSplitter(chunk_size=chunk_size, chunk_overlap=overlap,
                                              length_function=len, add_start_index=True,
                                              strip_whitespace=False, separators=["\n\n", "\n", " ", ""])
    chunks = []
    for paragraph in paragraphs:
        if paragraph["paper_id"] != paper["paper_id"] or any(
                key in paragraph for key in ("qas", "question", "answer", "references", "gold_evidence")):
            raise ValueError("Foreign paragraph or QA fields in index input")
        covered = 0
        for document in splitter.create_documents([paragraph["text"]]):
            relative = document.metadata["start_index"]
            text = document.page_content
            if relative < 0 or relative > covered or paragraph["text"][relative:relative + len(text)] != text:
                raise ValueError("Splitter lost source position/coverage")
            start = paragraph["start"] + relative
            end = start + len(text)
            identity = f"{NORMALIZATION}|{paragraph['paragraph_id']}|{start}|{end}|{chunk_size}|{overlap}|{text}"
            cid = hashlib.sha256(identity.encode()).hexdigest()
            metadata = {key: paragraph[key] for key in ("paper_id", "title", "section", "paragraph_id", "source_url", "split")}
            metadata.update(chunk_id=cid, start=start, end=end,
                            paragraph_start=paragraph["start"], paragraph_end=paragraph["end"], type="text")
            chunks.append({"chunk_id": cid, "text": text, "metadata": metadata})
            covered = max(covered, relative + len(text))
        if covered != len(paragraph["text"]):
            raise ValueError("Splitter did not cover the complete paragraph")
    return chunks


def export_paper_inputs(corpus):
    """Export only corpus allowlisted objects, never opening question/gold files."""
    from .dataset import load_jsonl

    blocks = {}
    for paragraph in load_jsonl(corpus / "paragraphs.jsonl"):
        blocks.setdefault(paragraph["paper_id"], []).append(paragraph)
    directory = corpus / "paper_inputs"
    directory.mkdir(exist_ok=True)
    paths = []
    for paper in sorted(load_jsonl(corpus / "papers.jsonl"), key=lambda p: (p["split"] != "train", p["paper_id"])):
        path = directory / f"{paper['paper_id']}.qasper.json"
        payload = {"schema": "scholarlens.paper.v1", "paper": paper, "paragraphs": blocks[paper["paper_id"]]}
        if path.exists():
            if json.loads(path.read_text()) != payload:
                raise ValueError(f"Exported paper changed: {path}")
        else:
            write_json(path, payload)
        paths.append(path)
    return paths


def read_paper(path, settings):
    payload = json.loads(Path(path).read_text())
    if set(payload) != {"schema", "paper", "paragraphs"} or payload["schema"] != "scholarlens.paper.v1":
        raise ValueError("Only body-only ScholarLens paper exports may be indexed")
    chunks = paper_chunks(payload["paper"], payload["paragraphs"], settings["chunk_size"], settings["overlap"])
    return payload["paper"], chunks
