"""Real T4 storage/role/scope/three-way checks, only on train smoke questions."""

import json
import sys
from importlib.metadata import version
from pathlib import Path

import numpy as np

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))

from ktem.main import App
from ktem.db.models import engine
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from scholarlens.data import sha256, write_json
from scholarlens.embedding import NomicEncoder, task_input
from scholarlens.dataset import load_jsonl
from scholarlens.framework import FrameworkBackend
from scholarlens.indexing import index_context
from scholarlens.retrieval import rrf

_, config, corpus, descriptor = index_context()
build = json.loads((root / "data/indexes" / descriptor["fingerprint"] / "manifest.json").read_text())
assert build["status"] == "ready"
expected_papers = {p["paper_id"] for p in load_jsonl(corpus / "papers.jsonl")}
app = App()
app.make()
index = next(i for i in app.index_manager.indices if i.name == config["index"]["name"])
old_index = next(i for i in app.index_manager.indices if i.id == 1)
settings = app.default_settings.flatten()
Source, Links = index._resources["Source"], index._resources["Index"]
backend = FrameworkBackend(Source, Links, index._docstore, index._vs, "default", descriptor["fingerprint"])
with Session(engine) as session:
    sources = session.execute(select(Source)).scalars().all()
    assert all(s.note.get("complete") and s.note["fingerprint"] == descriptor["fingerprint"] for s in sources)
    counts = {kind: session.scalar(select(func.count()).select_from(Links).where(Links.relation_type == kind))
              for kind in ("document", "vector")}
    paper_count = len(sources)
    assert paper_count == len(expected_papers) == build["papers"]
    assert {s.note["paper_id"] for s in sources} == expected_papers
    old_counts = {"papers": session.scalar(select(func.count()).select_from(old_index._resources["Source"]))}
    old_links = old_index._resources["Index"]
    old_counts.update({kind: session.scalar(select(func.count()).select_from(old_links).where(
        old_links.relation_type == kind)) for kind in ("document", "vector")})
assert old_counts == {"papers": 2, "document": 28, "vector": 28}
counts["chroma"] = index._vs._client.client.count()
counts["lance"] = index._docstore.db_connection.open_table(index._docstore.collection_name).count_rows()
assert len(set(counts.values())) == 1
assert counts["chroma"] == build["chunks"]
ids = index._vs._client.client.get(limit=16, include=["embeddings"])
vectors = np.asarray(ids["embeddings"], dtype=np.float32)
assert vectors.shape[1] == 768 and np.allclose(np.linalg.norm(vectors, axis=1), 1, atol=1e-5)
encoder = NomicEncoder(config["index"]["embedding"])
encoder.verify_model()
probe = encoder.encode(["model"], "query")
assert probe.shape == (1, 768) and probe.dtype == np.float32

results = []
for paper_id in ("1601.00901", "1601.01705"):
    file_id, _ = backend.source_for(paper_id=paper_id)
    docs = backend.paper_documents(paper_id)
    assert any("model" in d.text.lower() for d in docs)
    for method in ("bm25", "dense", "hybrid"):
        user = {**settings, f"index.options.{index.id}.scholar_method": method}
        pipeline = index.get_retriever_pipelines(user, "default", ["select", [file_id], "default"])[0]
        first = pipeline.retrieve("model", paper_id, method, 5)
        assert first == pipeline.retrieve("model", paper_id, method, 5)
        rendered = pipeline(text="model")
        assert [r["chunk_id"] for r in first] == [d.doc_id for d in rendered]
        assert all(d.metadata["paper_id"] == paper_id and d.metadata["file_id"] == file_id for d in rendered)
        results.append({"paper_id": paper_id, "method": method, "results": first})

file_id, _ = backend.source_for(paper_id="1601.01705")
pipeline = index.get_retriever_pipelines(settings, "default", ["select", [file_id], "default"])[0]
question = "Which release of the VQA dataset do the authors use?"
example = pipeline.retrieve(question, "1601.01705", "hybrid", 5)
assert any("VQA 1.0" in row["text"] for row in example)
hand = rrf({"bm25": [{"chunk_id": "a"}, {"chunk_id": "b"}, {"chunk_id": "c"}],
            "dense": [{"chunk_id": "b"}, {"chunk_id": "a"}]})
assert [r["chunk_id"] for r in hand] == ["a", "b", "c"]
assert np.isclose(hand[0]["score"], 1 / 61 + 1 / 62)
report = {"paper_count": paper_count, "storage_counts": counts, "fingerprint": descriptor,
          "preserved_t1_index": old_counts,
          "sample_vectors": {"shape": list(vectors.shape), "dtype": str(vectors.dtype),
                             "norm_min": float(np.linalg.norm(vectors, axis=1).min()),
                             "norm_max": float(np.linalg.norm(vectors, axis=1).max())},
          "prefixes": {"document": task_input("sample", "document"), "query": task_input("sample", "query")},
          "shared_ui_cli_results": results, "train_fact_question": question, "train_fact_retrieval": example,
          "rrf_hand_check": hand, "uv_lock_sha256": sha256(root / "uv.lock"),
          "rank_bm25_version": version("rank-bm25"), "test_evaluation_run": False}
out = root / "artifacts/t4/verification.json"
out.parent.mkdir(parents=True, exist_ok=True)
write_json(out, report)
print(json.dumps({"paper_count": paper_count, "storage_counts": counts,
                  "ui_cli_match": True, "scope_and_repeatability": True,
                  "train_fact_evidence": True, "rrf_hand_check": True}, indent=2))
