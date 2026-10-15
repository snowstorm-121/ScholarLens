"""Exercise the same Kotaemon index/retriever/QA components as its local UI."""

import argparse
import json
import platform
import sys
import time
from importlib.metadata import version
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))

from ktem.main import App
from t1_components import LocalQAPipeline

out_dir = root / "artifacts" / "t1"
out_dir.mkdir(parents=True, exist_ok=True)
parser = argparse.ArgumentParser()
parser.add_argument("--index-only", action="store_true")
args = parser.parse_args()
manifest = json.loads((root / "data/t1/manifest.json").read_text())
app = App()
app.make()
settings = app.default_settings.flatten()
index = app.index_manager.indices[0]
pipeline = index.get_indexing_pipeline(settings, "default")
paths = [root / paper["path"] for paper in manifest["papers"]]

# Reuse the existing upstream index if both files have already been imported.
file_ids = []
for path in paths:
    file_id = pipeline.route(path).get_id_if_exists(path)
    if file_id:
        file_ids.append(file_id)
        continue
    events = pipeline.stream([path], reindex=False)
    while True:
        try:
            event = next(events)
            print(event.text, flush=True)
        except StopIteration as complete:
            imported_ids, errors, _ = complete.value
            if any(errors) or not all(imported_ids):
                raise RuntimeError(f"Indexing failed: {errors}")
            file_ids.extend(imported_ids)
            break

selected = file_ids[1]
question = "Which release of the VQA dataset do the authors use?"
retrievers = index.get_retriever_pipelines(settings, "default", ["select", [selected], "default"])
docs = retrievers[0](text=question)
assert docs, "No evidence retrieved"
assert all(d.metadata["file_id"] == selected for d in docs), "Cross-file evidence leaked"
if args.index_only:
    summary = {"file_ids": file_ids, "question": question, "selected_file_id": selected,
        "chunks": [{"id": d.doc_id, "text": d.text, "metadata": d.metadata} for d in docs]}
    (out_dir / "index_smoke.json").write_text(json.dumps(summary, indent=2, default=str))
    print(json.dumps({"file_ids": file_ids, "selected_file_id": selected, "chunks": len(docs)}), flush=True)
    sys.exit(0)
qa = LocalQAPipeline.get_pipeline(settings, {"app": {}}, retrievers)
request_payloads = []
raw_responses = []
client = qa.answering_pipeline.llm._obj._client
original_request = client._request


def record_request(*args, **kwargs):
    if "json" in kwargs:
        request_payloads.append(kwargs["json"])
    response = original_request(*args, **kwargs)
    if kwargs.get("stream"):
        def tracked():
            for item in response:
                raw_responses.append(item.model_dump())
                yield item
        return tracked()
    raw_responses.append(response.model_dump())
    return response


client._request = record_request
start = time.perf_counter()
events = []
stream = qa.stream(question, "t1-local-smoke", [])
while True:
    try:
        event = next(stream)
        events.append({"channel": event.channel, "text": event.text})
    except StopIteration as complete:
        answer = complete.value
        break
elapsed = time.perf_counter() - start
matched_citations = qa.answering_pipeline.match_evidence_with_context(answer, docs)
result = {
    "question": question, "selected_file_id": selected, "file_ids": file_ids,
    "paper_id": manifest["papers"][1]["paper_id"],
    "answer": answer.text, "answer_metadata": answer.metadata,
    "retrieved": [{"id": d.doc_id, "text": d.text, "metadata": d.metadata} for d in docs],
    "events": events, "seconds": elapsed, "settings": settings,
    "requests": request_payloads,
    "raw_responses": raw_responses,
    "matched_citations": matched_citations,
    "question_source": "manual T1 fact check against the selected train paper",
    "environment": {"python": platform.python_version(), "platform": platform.platform(),
        "packages": {p: version(p) for p in ["kotaemon", "ktem", "gradio", "langchain-ollama", "chromadb"]}},
}
(out_dir / "smoke.json").write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str))
assert answer.text.strip(), "Generator produced no final answer; inspect smoke.json"
assert "1.0" in answer.text, "Answer missed the paper's VQA release"
assert answer.metadata["citation"], "No inline citations parsed"
assert matched_citations, "Citations did not map back to retrieved chunks"
assert set(matched_citations) <= {d.doc_id for d in docs}, "Citation escaped this query's context"
assert request_payloads and all(p.get("think") is False for p in request_payloads), "think=False was not sent"
print(json.dumps({"question": question, "answer": answer.text, "seconds": elapsed,
    "chunks": len(docs), "selected_file_id": selected}, indent=2, ensure_ascii=False), flush=True)
