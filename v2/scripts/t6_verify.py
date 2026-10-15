"""Offline recomputation of the fixed five train smoke records; no model calls."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scholarlens.dataset import load_jsonl, official_gold
from scholarlens.evaluate import EVALUATOR, recompute, save_new
from scholarlens.metrics import retrieval_metrics
from scholarlens.vendor.qasper_evaluator import evaluate, get_answers_and_evidence


def main():
    config = json.loads((ROOT / "configs/local.json").read_text())
    corpus = ROOT / config["output_dir"]
    papers = {p["paper_id"]: p for p in load_jsonl(corpus / "papers.jsonl")}
    verified = {}
    ids = None
    for stage in ("retrieval", "generation"):
        folder = ROOT / "artifacts/evaluation" / f"t6-train-{stage}-v2-final"
        rows, summary = recompute(folder)
        stored = json.loads((folder / "summary.json").read_text())
        assert summary == stored["summary"] and len(rows) == 5
        manifest = json.loads((folder / "manifest.json").read_text())
        assert manifest["split"] == "train" and manifest["evaluator"] == EVALUATOR
        assert sum(r["answerable"] for r in rows) == 3
        actual_ids = [r["question_id"] for r in rows]
        assert ids is None or actual_ids == ids
        ids = actual_ids
        for row in rows:
            pred = row["prediction"]
            for chunk in pred.get("metric_retrieval_results", pred.get("retrieval_results", [])):
                meta = chunk["metadata"]
                assert meta["paper_id"] == row["question"]["paper_id"]
                assert papers[meta["paper_id"]]["normalized_text"][meta["start"]:meta["end"]] == chunk["text"]
        if stage == "generation":
            gold = get_answers_and_evidence(official_gold([r["question"] for r in rows], papers), True)
            predictions = {r["question_id"]: {"answer": r["metrics"]["predicted_answer"],
                                             "evidence": r["metrics"]["predicted_evidence"]}
                           for r in rows if r["status"] != "error" and not r["metrics"]["metric_error"]}
            scored = evaluate(gold, predictions)
            assert scored["Answer F1"] == summary["Answer F1"]
            assert scored["Evidence F1"] == summary["Evidence F1"]
            assert (summary["unanswerable_correct_refusal"] + summary["unanswerable_wrong_answer"] +
                    summary["unanswerable_system_error"]) == 2
            expected = {k: config["generation"][k] for k in ("temperature", "seed", "num_ctx", "num_predict")}
            for row in rows:
                wire = row["prediction"]["wire_request"]
                assert wire["options"] == expected and wire["think"] is False
                assert len(wire["messages"]) == 2
                assert row["prediction"]["context_tokens"] <= 4500
        verified[stage] = summary
    # Direct, visible manual-example acceptance from plan 8.1.
    question = {"answerable": True, "paper_id": "manual", "references": [{"gold_evidence": [
        {"paragraph_id": "A", "start": 0, "end": 10},
        {"paragraph_id": "B", "start": 20, "end": 30}]}]}
    chunks = [{"chunk_id": label, "metadata": {"paper_id": "manual", "paragraph_id": label,
                "start": start, "end": start + 10}} for label, start in (("A", 0), ("X", 40), ("B", 20))]
    manual = retrieval_metrics(question, chunks)
    assert manual["EvidenceRecall@1"] == .5 and manual["EvidenceRecall@3"] == 1
    assert manual["AllEvidence@5"] == manual["MRR@10"] == 1
    report = {"five_train_ids": ids, "recomputed_summaries": verified,
              "official_batch_scores_match": True, "span_texts_verified": True,
              "actual_requests_verified": True, "manual_example": manual,
              "dev_or_test_scoring": False, "user_manual_understanding": "pending"}
    path = ROOT / "artifacts/t6/verification-v2.json"
    if path.exists():
        assert json.loads(path.read_text()) == report
    else:
        save_new(path, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
