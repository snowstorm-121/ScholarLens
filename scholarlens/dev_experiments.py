"""Bounded T7 selection rules, comparison contracts and reproducible case exports."""

import copy
import json
from pathlib import Path

from .data import sha256
from .evaluate import digest, recompute, save_new


PRIORITY = ("EvidenceRecall@5", "AllEvidence@5", "MRR@10")
METHOD_TIES = {"dense": 2, "bm25": 1, "hybrid": 0}


def read_run(directory):
    directory = Path(directory)
    manifest = json.loads((directory / "manifest.json").read_text())
    rows, summary = recompute(directory)
    if manifest["split"] != "dev" or len(rows) != 200:
        raise ValueError("Selection requires the complete frozen 200-question Dev retrieval set")
    if manifest["stage"] != "retrieval" or summary["answerable"] != 160:
        raise ValueError("Wrong stage or answerable Dev denominator")
    if summary != json.loads((directory / "summary.json").read_text())["summary"]:
        raise ValueError("Stored summary differs from raw prediction recomputation")
    return {"directory": str(directory), "manifest": manifest, "summary": summary}


def comparison_contract(manifest):
    """Only collection name and prescribed chunk length may differ across runs."""
    config = copy.deepcopy(manifest["config"])
    config["index"].pop("name")
    config["index"].pop("chunk_size")
    return {"config": config, **{key: manifest[key] for key in (
        "question_set_sha256", "corpus_manifest_sha256", "freeze_sha256", "evaluator", "code_sha256", "runtime")}}


def checked_runs(directories):
    runs, expected = {}, None
    for directory in directories:
        run = read_run(directory)
        manifest = run["manifest"]
        current = comparison_contract(manifest)
        if expected is not None and current != expected:
            raise ValueError("Uncontrolled difference between Dev experiments")
        expected = current
        key = (manifest["config"]["index"]["chunk_size"], manifest["method"])
        if key[0] not in {1600, 2400} or key[1] not in METHOD_TIES:
            raise ValueError("Experiment outside the bounded T7 search space")
        if key in runs:
            raise ValueError("Duplicate configuration; do not pick the best retry")
        runs[key] = run
    return runs


def score(run):
    return tuple(run["summary"][key] for key in PRIORITY)


def choose_chunking(directories):
    runs = checked_runs(directories)
    for size in (1600, 2400):
        if (size, "hybrid") not in runs:
            raise ValueError("Both prescribed Hybrid chunk configurations are required")
    return max((1600, 2400), key=lambda size: (score(runs[size, "hybrid"]), size == 1600))


def choose_method(directories, chunk_size):
    runs = checked_runs(directories)
    if any((chunk_size, method) not in runs for method in METHOD_TIES):
        raise ValueError("All three methods on the chosen chunk set are required")
    return max(METHOD_TIES, key=lambda method: (score(runs[chunk_size, method]), METHOD_TIES[method]))


def selected_snapshot(directories):
    directories = list(directories)
    runs = checked_runs(directories)
    if any((1600, method) not in runs for method in METHOD_TIES):
        raise ValueError("All three 1600 baseline runs are required before final selection")
    chunk_size = choose_chunking(directories)
    method = choose_method(directories, chunk_size)
    run = runs[chunk_size, method]
    from .qa import PROMPT_VERSION, SYSTEM_PROMPT

    config = copy.deepcopy(run["manifest"]["config"])
    config["index"]["retrieval"]["method"] = method
    return {**config, "selection": {"chunk_size": chunk_size, "overlap": 200,
            "method": method, "priority": list(PRIORITY), "chunk_tie": "1600", "method_tie": "dense,bm25,hybrid",
            "metrics": {key: run["summary"][key] for key in PRIORITY},
            "runs": [str(Path(p)) for p in directories], "data_contract": comparison_contract(run["manifest"]),
            "system_prompt": SYSTEM_PROMPT, "prompt_version": PROMPT_VERSION,
            "prompt_sha256": digest(SYSTEM_PROMPT), "ready_for_test": False,
            "status": "retrieval_selected_pending_generation_and_user_U3"}}


def generation_cases(directory):
    """Export deterministic failure candidates, not automated semantic certification."""
    directory = Path(directory)
    manifest = json.loads((directory / "manifest.json").read_text())
    if manifest["split"] != "dev" or manifest["stage"] != "generation":
        raise ValueError("Error review is restricted to generation Dev")
    rows, summary = recompute(directory)
    if len(rows) != 50 or summary["answerable"] != 40:
        raise ValueError("Expected complete frozen generation Dev subset")
    result = []
    for row in rows:
        m, p = row["metrics"], row["prediction"] or {}
        if row["status"] == "error":
            kind = "runtime_error"
        elif row["status"] == "invalid_output":
            kind = "citation_or_protocol"
        elif row["answerable"] and m["Context EvidenceRecall"] < m["EvidenceRecall@5"]:
            kind = "context_budget"
        elif row["answerable"] and m["EvidenceRecall@5"] < 1:
            kind = "retrieval_incomplete"
        elif row["answerable"] and row["status"] == "insufficient_evidence":
            kind = "generation_refusal_with_complete_gold_context"
        elif not row["answerable"] and m["unanswerable_wrong_answer"]:
            kind = "unanswerable_answered"
        elif m["Answer F1"] < 1:
            kind = "answer_or_reference_review"
        else:
            kind = "success_boundary"
        result.append({"question_id": row["question_id"], "paper_id": row["question"]["paper_id"],
                       "question": row["question"]["question"], "provisional_category": kind,
                       "status": row["status"], "metrics": m, "prediction": p,
                       "references": row["question"]["references"],
                       "semantic_review": "pending", "source_sha256": sha256(
                           directory / "questions" / (row["question_id"] + ".json"))})
    return sorted(result, key=lambda row: (row["provisional_category"] == "success_boundary", row["question_id"]))


def write_selection(directories, output):
    snapshot = selected_snapshot(directories)
    save_new(output, snapshot)
    return snapshot
