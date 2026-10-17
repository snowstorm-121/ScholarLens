"""Shared-pipeline evaluation, immutable per-question records and recomputable summaries."""

import hashlib
import importlib.metadata
import json
import os
import platform
import re
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from filelock import FileLock

from .data import sha256
from .dataset import context, load_jsonl, rank_key, validate_dataset
from .indexing import ROOT, index_context
from .metrics import aggregate, context_metrics, generation_metrics, retrieval_metrics


EVALUATOR = {
    "repository": "https://github.com/allenai/qasper-led-baseline",
    "commit": "e996b6c7b1b5f95d9308a74e3586416c6e780df1",
    "sha256": "781aba7cd8e524bef4f0a1b4bf3504e5b02cb1d8d5bf32a8f0a89dfa83e86bfe",
}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def save_new(path, value):
    publish_new(path, json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def publish_new(path, text):
    """Publish a complete record atomically without replacing first results."""
    path = Path(path)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                     prefix=".partial-", delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
            os.link(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


def select_questions(config_path, split, stage, limit=None, *, test_authorized=False):
    if split == "test" and not test_authorized:
        raise ValueError("Test scoring is locked until T8 final configuration approval")
    if split not in {"train", "dev", "test"}:
        raise ValueError("Unknown evaluation split")
    if stage not in {"retrieval", "generation"}:
        raise ValueError("Unknown evaluation stage")
    if limit is not None and (type(limit) is not int or limit < 1):
        raise ValueError("limit must be a positive integer")
    validation = validate_dataset(config_path)
    root, config, corpus, papers, paragraphs = context(config_path)
    if split == "train":
        candidates = []
        for row in load_jsonl(corpus / "questions.raw.jsonl"):
            if row["split"] != "train" or not row["question"].strip():
                continue
            flags = {ref["answer"]["unanswerable"] for ref in row["references"]}
            valid = [r for r in row["references"] if r["valid"] and not r["errors"]]
            if len(flags) == 1 and valid:
                candidates.append({**row, "answerable": not valid[0]["answer"]["unanswerable"],
                                   "references": valid})
        # Fixed smoke composition, chosen before predictions; never select by model success.
        candidates.sort(key=lambda q: rank_key(q, config["evaluation"]["seed"]))
        rows = ([q for q in candidates if q["answerable"]][:3] +
                [q for q in candidates if not q["answerable"]][:2])
        if len(rows) != 5:
            raise ValueError("Train smoke requires three answerable and two unanswerable questions")
    else:
        folder = corpus / "evaluation" / config["evaluation"]["version"]
        rows = load_jsonl(folder / f"questions.{split}.jsonl")
        if stage == "generation":
            ids = set(json.loads((folder / f"generation.{split}.ids.json").read_text()))
            rows = [q for q in rows if q["question_id"] in ids]
    rows = rows[:limit] if limit is not None else rows
    if len({q["question_id"] for q in rows}) != len(rows):
        raise ValueError("Duplicate evaluation question IDs")
    return root, config, corpus, papers, paragraphs, validation, rows


class RetrievedOnce:
    """Replay the same real Top-10 prefix to QA, which needs only the Top-5 context input."""
    def __init__(self, rows, trace, fingerprint):
        self.rows, self.trace, self.fingerprint = rows, trace, fingerprint

    def retrieve(self, query, paper_id, method, k, *, trace=None):
        if k > 10:
            raise ValueError("Replay cannot provide deeper retrieval")
        if any(r["metadata"]["paper_id"] != paper_id for r in self.rows):
            raise ValueError("Foreign paper in shared retrieval")
        if trace is not None:
            trace.update(self.trace)
        return self.rows[:k]


def runtime_snapshot():
    import httpx

    result = {"python": sys.version, "platform": platform.platform(), "packages": {}}
    for name in ("ollama", "transformers", "tokenizers", "chromadb", "langchain-text-splitters", "rank-bm25"):
        result["packages"][name] = importlib.metadata.version(name)
    try:
        with httpx.Client(trust_env=False, timeout=5) as client:
            response = client.get("http://127.0.0.1:11434/api/version")
            response.raise_for_status()
            result["ollama_runtime"] = response.json()["version"]
    except (httpx.HTTPError, KeyError) as error:
        result["ollama_runtime_error"] = str(error)
    return result


def score_question(question, prediction, stage, paragraphs):
    prediction = prediction or {}
    # Measure observed upstream evidence even if a later model call failed.
    metrics = retrieval_metrics(question, prediction.get(
        "metric_retrieval_results", prediction.get("retrieval_results", [])))
    if stage == "generation":
        metrics.update(context_metrics(question, prediction.get("context_chunks", [])))
        metrics.update(generation_metrics(question, prediction, paragraphs))
    return metrics


def markdown(summary, experiment_id):
    lines = ["# ScholarLens evaluation", "", f"Experiment: `{experiment_id}`", "",
             "Span coverage metrics are project-defined, not official QASPER leaderboard metrics.",
             "Official paragraph Evidence F1 is separate from actual-context span coverage.", "",
             "| Metric | Value |", "|---|---:|"]
    for key, value in summary.items():
        if not isinstance(value, (dict, list)):
            display = "N/A" if value is None else str(value)
            lines.append(f"| {key} | {display} |")
    return "\n".join(lines) + "\n"


def validate_test_contract(config_path, contract_path, stage, method, experiment_id, limit):
    if not contract_path or not experiment_id or limit is not None:
        raise ValueError("Test requires a pre-registered contract, experiment_id, and no limit")
    contract = json.loads(Path(contract_path).read_text())
    batch = contract.get("batches", {}).get(experiment_id)
    if batch != {"stage": stage, "method": method}:
        raise ValueError("Test batch does not match pre-registered stage/method")
    if sha256(config_path) != contract["config_sha256"]:
        raise ValueError("Frozen Test config hash changed")
    for relative, expected in contract["files_sha256"].items():
        if sha256(ROOT / relative) != expected:
            raise ValueError(f"Frozen Test file hash changed: {relative}")
    return sha256(contract_path)


def evaluate(config_path, *, split="train", stage="retrieval", method="hybrid", limit=None,
             experiment_id=None, resume=False, retriever_factory=None, answer_fn=None, runtime=None,
             test_contract=None):
    if method not in {"bm25", "dense", "hybrid"}:
        raise ValueError("Unknown retrieval method")
    contract_sha = validate_test_contract(config_path, test_contract, stage, method,
                                          experiment_id, limit) if split == "test" else None
    selected = (select_questions(config_path, split, stage, limit, test_authorized=True)
                if split == "test" else select_questions(config_path, split, stage, limit))
    root, config, corpus, papers, paragraphs, validation, questions = selected
    evaluator_path = Path(__file__).parent / "vendor/qasper_evaluator.py"
    if sha256(evaluator_path) != EVALUATOR["sha256"]:
        raise ValueError("Official evaluator changed")
    _, _, _, descriptor = index_context(config_path)
    experiment_id = experiment_id or f"t6-{split}-{stage}-{uuid.uuid4().hex}"
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,100}", experiment_id):
        raise ValueError("Unsafe experiment_id")
    directory = root / "artifacts/evaluation" / experiment_id
    directory.mkdir(parents=True, exist_ok=True)
    # Only a single writer per experiment; no implicit retry of an existing answer.
    with FileLock(str(directory / "run.lock"), timeout=0):
        core = {"split": split, "stage": stage, "method": method, "config": config,
                "question_ids": [q["question_id"] for q in questions], "questions": questions,
                "question_set_sha256": digest(questions), "evaluator": EVALUATOR,
                "corpus_manifest_sha256": sha256(corpus / "corpus_manifest.json"),
                "freeze_sha256": validation["freeze_sha256"], "index": descriptor,
                "runtime": runtime if runtime is not None else runtime_snapshot(),
                **({"test_run_contract_sha256": contract_sha} if contract_sha else {}),
                "code_sha256": {str(p.relative_to(ROOT)): sha256(p)
                                for p in sorted((ROOT / "scholarlens").rglob("*.py"))}}
        manifest_path = directory / "manifest.json"
        if manifest_path.exists():
            if not resume:
                raise ValueError("Experiment already exists; use --resume, never overwrite first results")
            manifest = json.loads(manifest_path.read_text())
            if manifest["contract"] != digest(core):
                raise ValueError("Resume configuration/data/code changed; use a new experiment")
        else:
            if resume:
                raise ValueError("Cannot resume an experiment without its manifest")
            manifest = {**core, "experiment_id": experiment_id, "contract": digest(core),
                        "created_at_utc": datetime.now(timezone.utc).isoformat()}
            save_new(manifest_path, manifest)
        results = directory / "questions"
        results.mkdir(exist_ok=True)
        if retriever_factory is None:
            from .framework import application_retriever
            retriever_factory = application_retriever
        if answer_fn is None and stage == "generation":
            from .qa import answer
            answer_fn = answer
        for question in questions:
            path = results / (question["question_id"] + ".json")
            if path.exists():
                continue
            start = time.monotonic()
            prediction = None
            try:
                pipeline = retriever_factory(config_path, question["paper_id"], method)
                trace = {}
                ranked = pipeline.retrieve(question["question"], question["paper_id"], method, 10, trace=trace)
                if stage == "generation":
                    replay = RetrievedOnce(ranked, trace, pipeline.fingerprint)
                    prediction = answer_fn(question["question"], question["paper_id"], config,
                                           method=method, retriever=replay.retrieve)
                    prediction["metric_retrieval_results"] = ranked
                else:
                    prediction = {"status": "ok", "retrieval_results": ranked, "rankings": trace,
                                  "index_fingerprint": pipeline.fingerprint, "error": None}
                metrics = score_question(question, prediction, stage, paragraphs)
            except Exception as error:
                prediction = {"status": "error", "error": {"type": type(error).__name__, "message": str(error)},
                              "partial_prediction": prediction}
                metrics = score_question(question, prediction, stage, paragraphs)
            row = {"question_id": question["question_id"], "question": question,
                   "answerable": question["answerable"], "status": prediction["status"],
                   "error": prediction.get("error"), "seconds": time.monotonic() - start,
                   "prediction": prediction, "metrics": metrics,
                   "scoring_paragraphs": {c["paragraph_id"]: paragraphs[c["paragraph_id"]]
                                          for c in prediction.get("citations", [])
                                          if c.get("paragraph_id") in paragraphs}}
            save_new(path, row)
            print(json.dumps({"question_id": row["question_id"], "status": row["status"],
                              "seconds": row["seconds"]}), flush=True)
        rows, summary = recompute(directory)
        report = {"experiment_id": experiment_id, "stage": stage, "split": split,
                  "summary": summary, "question_results": [str(p) for p in sorted(results.glob("*.json"))]}
        report_path = directory / "summary.json"
        if report_path.exists():
            if json.loads(report_path.read_text()) != report:
                raise ValueError("Existing summary differs; no silent overwrite")
        else:
            save_new(report_path, report)
        markdown_path = directory / "summary.md"
        expected_markdown = markdown(summary, experiment_id)
        if markdown_path.exists():
            if markdown_path.read_text() != expected_markdown:
                raise ValueError("Existing Markdown differs; no silent overwrite")
        else:
            publish_new(markdown_path, expected_markdown)
        return {**report, "output_dir": str(directory)}


def recompute(directory):
    """Re-score saved raw predictions; missing rows stay in the expected denominator."""
    directory = Path(directory)
    manifest = json.loads((directory / "manifest.json").read_text())
    rows = []
    for question in manifest["questions"]:
        path = directory / "questions" / (question["question_id"] + ".json")
        row = json.loads(path.read_text()) if path.exists() else {
            "question": question, "question_id": question["question_id"],
            "answerable": question["answerable"], "status": "error", "error": {"type": "missing_prediction"},
            "seconds": 0, "prediction": None}
        if row["question"] != question:
            raise ValueError("Stored result differs from expected question")
        row["metrics"] = score_question(question, row.get("prediction"), manifest["stage"],
                                        row.get("scoring_paragraphs", {}))
        rows.append(row)
    return rows, aggregate(rows, manifest["stage"])
