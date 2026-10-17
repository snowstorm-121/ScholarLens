"""Recheck saved formal Test runs without calling retrieval or generation."""

import json
import math
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scholarlens.data import sha256
from scholarlens.dataset import load_jsonl, official_gold, rank_key, validate_dataset
from scholarlens.evaluate import recompute, save_new
from scholarlens.vendor.qasper_evaluator import evaluate, get_answers_and_evidence
from scripts.t7_verify import verify_prediction


def main():
    config_path = ROOT / "configs/selected_config.json"
    contract_path = ROOT / "configs/t8-test-contract.json"
    contract = json.loads(contract_path.read_text())
    config = json.loads(config_path.read_text())
    assert sha256(config_path) == contract["config_sha256"]
    for name, expected in contract["files_sha256"].items():
        assert sha256(ROOT / name) == expected, name
    validation = validate_dataset(config_path)
    assert validation["freeze_sha256"] == contract["files_sha256"][
        "data/qasper/v0.3/evaluation/v1/freeze.json"]
    papers = {p["paper_id"]: p for p in load_jsonl(ROOT / config["output_dir"] / "papers.jsonl")}
    output = {"config_sha256": sha256(config_path), "contract_sha256": sha256(contract_path),
              "freeze_sha256": validation["freeze_sha256"], "runs": {}}
    for experiment_id, batch in contract["batches"].items():
        folder = ROOT / "artifacts/evaluation" / experiment_id
        manifest = json.loads((folder / "manifest.json").read_text())
        assert manifest["split"] == "test" and manifest["stage"] == batch["stage"]
        assert manifest["method"] == batch["method"]
        assert manifest["test_run_contract_sha256"] == output["contract_sha256"]
        assert manifest["index"]["fingerprint"] == config["selection"]["index_descriptor"]["fingerprint"]
        assert all(sha256(ROOT / name) == value for name, value in manifest["code_sha256"].items())
        rows, summary = recompute(folder)
        assert summary == json.loads((folder / "summary.json").read_text())["summary"]
        assert len(rows) == (300 if batch["stage"] == "retrieval" else 100)
        for row in rows:
            verify_prediction(row, papers, config["generation"], batch["stage"])
        if batch["stage"] == "generation":
            gold = get_answers_and_evidence(official_gold([r["question"] for r in rows], papers), True)
            predictions = {r["question_id"]: {"answer": r["metrics"]["predicted_answer"],
                                              "evidence": r["metrics"]["predicted_evidence"]}
                           for r in rows if r["status"] != "error" and not r["metrics"]["metric_error"]}
            scores = evaluate(gold, predictions)
            assert math.isclose(scores["Answer F1"], summary["Answer F1"], abs_tol=1e-12)
            assert math.isclose(scores["Evidence F1"], summary["Evidence F1"], abs_tol=1e-12)
            assert sum(not r["answerable"] for r in rows) == 20
            assert (summary["unanswerable_correct_refusal"] + summary["unanswerable_wrong_answer"] +
                    summary["unanswerable_system_error"]) == 20
        seconds = sorted(row["seconds"] for row in rows)
        output["runs"][experiment_id] = {"manifest_sha256": sha256(folder / "manifest.json"),
            "questions": len(rows), "summary": summary, "p50_seconds": statistics.median(seconds),
            "p95_seconds_nearest_rank": seconds[math.ceil(.95 * len(seconds)) - 1]}
    generation = ROOT / "artifacts/evaluation/t8-v1-dense-generation/manifest.json"
    questions = json.loads(generation.read_text())["questions"]
    output["review_question_ids"] = [q["question_id"] for q in
        sorted((q for q in questions if q["answerable"]), key=lambda q: rank_key(q, 42))[:20]]
    target = ROOT / "artifacts/t8/verification.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        assert json.loads(target.read_text()) == output
    else:
        save_new(target, output)
    print(json.dumps({"verified_runs": list(output["runs"]), "review_count": 20,
                      "output": str(target)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
