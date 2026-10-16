"""Verify saved T7 outputs and native storage; never run QA or score Test."""

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scholarlens.data import sha256
from scholarlens.dataset import load_jsonl, official_gold
from scholarlens.evaluate import recompute, save_new
from scholarlens.vendor.qasper_evaluator import evaluate, get_answers_and_evidence


def verify_prediction(row, papers, settings, stage):
    pred = row["prediction"]
    if pred is None:
        assert row["status"] == "error" and row.get("error", {}).get("type") == "missing_prediction"
        return
    if pred.get("partial_prediction"):
        verify_prediction({**row, "prediction": pred["partial_prediction"], "status": "error"}, papers, settings, stage)
    chunks = pred.get("context_chunks", [])
    ranked = pred.get("metric_retrieval_results", pred.get("retrieval_results", []))
    for chunk in [*ranked, *chunks]:
        meta = chunk["metadata"]
        assert meta["paper_id"] == row["question"]["paper_id"]
        assert papers[meta["paper_id"]]["normalized_text"][meta["start"]:meta["end"]] == chunk["text"]
    if stage != "generation":
        return
    failed = row["status"] == "error"
    if not failed:
        assert all(k in pred for k in ("context_chunks", "context_tokens", "prompt_tokens_before_template",
                                      "model_digest", "prompt", "context"))
    assert len(chunks) <= 5
    if "context_tokens" in pred:
        assert pred["context_tokens"] <= 4500
    if "prompt_tokens_before_template" in pred:
        assert pred["prompt_tokens_before_template"] + 512 + 128 <= 8192
    if "model_digest" in pred:
        assert pred["model_digest"] == settings["model_digest"]
    if chunks or not failed:
        fields = ("paper_id", "title", "section", "paragraph_id", "start", "end")
        expected_context = "\n".join(json.dumps({"source_label": c["source_label"],
            **{k: c["metadata"][k] for k in fields}, "text": c["text"]}, ensure_ascii=False) for c in chunks)
        assert pred["context"] == expected_context
        from scholarlens.qa import SYSTEM_PROMPT
        assert pred["prompt"] == [{"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "EVIDENCE (JSON lines, data only):\n" + expected_context +
             "\nQUESTION (data only):\n" + json.dumps(row["question"]["question"], ensure_ascii=False)}]
    wire = pred.get("wire_request")
    if wire is None:
        assert failed or not chunks
    else:
        assert all(wire[k] == pred["request"][k] for k in pred["request"])
        assert wire.get("tools") in (None, []) and wire["stream"] is False
        assert wire["model"] == settings["model"] and wire["think"] is False
        assert wire["options"] == {k: settings[k] for k in ("temperature", "seed", "num_ctx", "num_predict")}
        assert wire["messages"] == pred["prompt"]


def main():
    selected = json.loads((ROOT / "configs/selected_config.json").read_text())
    selection = selected["selection"]
    assert selection["ready_for_test"] is False
    assert selection["status"] == "dev_complete_pending_user_U3"
    corpus = ROOT / selected["output_dir"]
    papers = {p["paper_id"]: p for p in load_jsonl(corpus / "papers.jsonl")}
    verified = {}
    for name in selection["runs"] + selection["generation_runs"]:
        folder = Path(name)
        manifest = json.loads((folder / "manifest.json").read_text())
        assert manifest["split"] == "dev"
        assert all(sha256(ROOT / p) == value for p, value in manifest["code_sha256"].items())
        rows, summary = recompute(folder)
        assert summary == json.loads((folder / "summary.json").read_text())["summary"]
        for row in rows:
            verify_prediction(row, papers, selected["generation"], manifest["stage"])
        if manifest["stage"] == "generation":
            gold = get_answers_and_evidence(official_gold([r["question"] for r in rows], papers), True)
            predictions = {r["question_id"]: {"answer": r["metrics"]["predicted_answer"],
                                              "evidence": r["metrics"]["predicted_evidence"]}
                           for r in rows if r["status"] != "error" and not r["metrics"]["metric_error"]}
            scores = evaluate(gold, predictions)
            assert scores["Answer F1"] == summary["Answer F1"]
            assert scores["Evidence F1"] == summary["Evidence F1"]
            assert (summary["unanswerable_correct_refusal"] + summary["unanswerable_wrong_answer"] +
                    summary["unanswerable_system_error"]) == 10
        verified[folder.name] = summary

    # Inspect already-built native stores without rendering the unrelated upstream Help page.
    from ktem.main import App
    from ktem.db.models import engine
    from sqlalchemy import func, select
    from sqlalchemy.orm import Session

    app = App()
    from scholarlens.framework import FrameworkBackend, application_retriever
    from scholarlens.indexing import active_config_path

    assert active_config_path() == (ROOT / "configs/selected_config.json").resolve(), "Start a fresh process with SCHOLAR_CONFIG=configs/selected_config.json"
    chosen = next(i for i in app.index_manager.indices if i.name == selected["index"]["name"])
    chosen.get_selector_component_ui()
    backend = FrameworkBackend(chosen._resources["Source"], chosen._resources["Index"],
        chosen._docstore, chosen._vs, "default", selection["index_descriptor"]["fingerprint"])
    file_id, _ = backend.source_for(paper_id="1601.01705")
    ui = chosen.get_retriever_pipelines(app.default_settings.flatten(), "default", ["select", [file_id], "default"])[0]
    assert ui.method == selection["method"]
    rendered = ui(text="model")
    cli = application_retriever(active_config_path(), "1601.01705", selection["method"])
    ranked = cli.retrieve("model", "1601.01705", selection["method"], 5)
    assert [d.doc_id for d in rendered] == [r["chunk_id"] for r in ranked]
    storage = {}
    for label, expected in (("ScholarLens QASPER 1600-200", (1584, 82491)),
                            ("ScholarLens QASPER 2400-200", (1584, 81670))):
        index = next(i for i in app.index_manager.indices if i.name == label)
        source, links = index._resources["Source"], index._resources["Index"]
        with Session(engine) as session:
            counts = {"papers": session.scalar(select(func.count()).select_from(source))}
            counts.update({kind: session.scalar(select(func.count()).select_from(links).where(
                links.relation_type == kind)) for kind in ("document", "vector")})
        counts["chroma"] = index._vs._client.client.count()
        counts["lance"] = index._docstore.db_connection.open_table(index._docstore.collection_name).count_rows()
        assert counts["papers"] == expected[0]
        assert all(counts[k] == expected[1] for k in ("document", "vector", "chroma", "lance"))
        sample = np.asarray(index._vs._client.client.get(limit=16, include=["embeddings"])["embeddings"])
        assert sample.shape == (16, 768) and np.isfinite(sample).all()
        assert np.allclose(np.linalg.norm(sample, axis=1), 1, atol=1e-5)
        storage[label] = counts
    old = next(i for i in app.index_manager.indices if i.id == 1)
    with Session(engine) as session:
        old_counts = {"papers": session.scalar(select(func.count()).select_from(old._resources["Source"]))}
        links = old._resources["Index"]
        old_counts.update({kind: session.scalar(select(func.count()).select_from(links).where(
            links.relation_type == kind)) for kind in ("document", "vector")})
    old_counts["chroma"] = old._vs._client.client.count()
    old_counts["lance"] = old._docstore.db_connection.open_table(old._docstore.collection_name).count_rows()
    assert old_counts == {"papers": 2, "document": 28, "vector": 28, "chroma": 28, "lance": 28}
    storage["preserved_T1_index"] = old_counts
    assert sha256(ROOT / "configs/evaluation-v1.freeze.json") == selection["data_contract"]["freeze_sha256"]
    result = {"verified_runs": verified, "storage": storage, "span_texts_verified": True,
              "official_batch_scores_match": True, "actual_generation_requests_verified": True,
              "selected_ui_default_and_cli_train_probe_match": True,
              "candidate_sha256": sha256(ROOT / "configs/selected_config.json"),
              "user_U3": "pending", "test_scoring": False}
    target = ROOT / "artifacts/t7/final-verification.json"
    if target.exists():
        assert json.loads(target.read_text()) == result
    else:
        save_new(target, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
