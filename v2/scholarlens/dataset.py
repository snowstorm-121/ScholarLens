"""T3: deterministic sampling and immutable gold, without running a RAG system."""

import hashlib
import json
import re
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from .data import normalize, sha256, validate_spans, write_json, write_jsonl


RULES = {
    "version": "qasper-selection-v1",
    "conflicts": "exclude if ANY original annotations disagree on unanswerable",
    "references": "retain only entire valid references; never salvage partial evidence groups",
    "question_key": "paper_id + NFC/whitespace-normalized, casefolded question",
    "dedup": "among eligible duplicate questions keep the lowest seeded hash, then question_id",
    "ranking": "SHA256(str(seed) + '|' + question_id), then question_id",
    "shortfall": "take all eligible within split/class; no borrowing or synthetic fill",
    "generation": "same hash ranking within selected retrieval split/class",
    "review": "first N selected Dev questions by same hash; never sample Test for manual review",
}


def load_jsonl(path):
    with Path(path).open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def rank_key(question, seed=42):
    qid = question["question_id"]
    return hashlib.sha256(f"{seed}|{qid}".encode()).hexdigest(), qid


def filter_questions(rows, seed=42):
    """Filtering is independent of system scores; annotations are alternatives."""
    candidates, excluded, rejected_annotations = [], [], []
    ids = set()
    for row in rows:
        if row["split"] not in ("dev", "test"):
            continue
        qid = row["question_id"]
        if qid in ids:
            raise ValueError(f"Duplicate question_id: {qid}")
        ids.add(qid)
        refs = row["references"]
        for ref in refs:
            if not ref["valid"]:
                rejected_annotations.append({"question_id": qid, "split": row["split"],
                                             "annotation_id": ref["annotation_id"],
                                             "reasons": ref["errors"]})
        valid = [ref for ref in refs if ref["valid"] and not ref["errors"]]
        flags = {ref["answer"]["unanswerable"] for ref in refs}
        reason = None
        if len(flags) > 1:
            reason = "answerability_conflict"
        elif not normalize(row["question"]):
            reason = "empty_question"
        elif not valid:
            reason = "no_valid_reference"
        if reason:
            excluded.append({"question_id": qid, "paper_id": row["paper_id"],
                             "split": row["split"], "reason": reason})
            continue
        candidates.append({"question_id": qid, "paper_id": row["paper_id"],
                           "split": row["split"], "question": row["question"],
                           "answerable": not valid[0]["answer"]["unanswerable"],
                           "references": valid})
    unique, seen = [], set()
    for row in sorted(candidates, key=lambda q: rank_key(q, seed)):
        key = row["paper_id"], normalize(row["question"]).casefold()
        if key in seen:
            excluded.append({"question_id": row["question_id"], "paper_id": row["paper_id"],
                             "split": row["split"], "reason": "duplicate_normalized_question"})
        else:
            seen.add(key)
            unique.append(row)
    return unique, sorted(excluded, key=lambda r: (r["split"], r["question_id"])), rejected_annotations


def sample(rows, split, quotas, seed):
    chosen = []
    for name, answerable in (("answerable", True), ("unanswerable", False)):
        pool = [q for q in rows if q["split"] == split and q["answerable"] is answerable]
        chosen.extend(sorted(pool, key=lambda q: rank_key(q, seed))[:quotas[name]])
    return sorted(chosen, key=lambda q: rank_key(q, seed))


def official_gold(rows, papers):
    """Official evaluator's paper -> qas -> answers shape, original answer text."""
    result = {}
    for row in rows:
        paper_id = row["paper_id"]
        entry = result.setdefault(paper_id, {"title": papers[paper_id]["title"], "qas": []})
        entry["qas"].append({"question_id": row["question_id"], "question": row["question"],
                             "answers": [{"annotation_id": ref["annotation_id"],
                                          "answer": ref["answer"]}
                                         for ref in row["references"]]})
    return result


def validate_questions(rows, papers, paragraphs):
    qids, aids = set(), set()
    for row in rows:
        qid, pid = row["question_id"], row["paper_id"]
        if qid in qids:
            raise ValueError(f"Duplicate question_id: {qid}")
        qids.add(qid)
        if pid not in papers or papers[pid]["split"] != row["split"]:
            raise ValueError(f"Missing/wrong-split paper: {pid}")
        if not row["references"]:
            raise ValueError(f"No references: {qid}")
        for ref in row["references"]:
            if ref["annotation_id"] in aids:
                raise ValueError("Duplicate annotation_id")
            aids.add(ref["annotation_id"])
            if not ref["valid"] or ref["errors"] or type(row["answerable"]) is not bool:
                raise ValueError(f"Invalid reference/question: {qid}")
            if ref["answer"]["unanswerable"] is row["answerable"]:
                raise ValueError("Answerability mismatch")
            gold = ref["gold_evidence"]
            original = ref["answer"]["evidence"]
            if row["answerable"]:
                if not gold or len(gold) != len(original):
                    raise ValueError("Incomplete evidence group")
                for evidence, text in zip(gold, original):
                    block = paragraphs.get(evidence["paragraph_id"])
                    if (block is None or block["paper_id"] != pid
                            or normalize(text) != evidence["evidence_text"]
                            or evidence["original_evidence_text"] != text
                            or "FLOAT SELECTED" in text):
                        raise ValueError("Invalid evidence mapping")
                    validate_spans(papers[pid], [block], [{**ref, "gold_evidence": [evidence]}])
            elif gold or original:
                raise ValueError("Unanswerable must have empty evidence")


def context(config_path):
    path = Path(config_path).resolve()
    root = path.parent.parent
    config = json.loads(path.read_text())
    settings = config["evaluation"]
    if not re.fullmatch(r"v[1-9][0-9]*", settings["version"]):
        raise ValueError("Evaluation version must be v1, v2, ...")
    if type(settings["seed"]) is not int or type(settings["dev_review_count"]) is not int or settings["dev_review_count"] < 0:
        raise ValueError("Invalid seed/review count")
    for stage in ("retrieval", "generation"):
        for split in ("dev", "test"):
            quota = settings[stage][split]
            if set(quota) != {"answerable", "unanswerable"} or any(
                    type(n) is not int or n < 0 for n in quota.values()):
                raise ValueError("Invalid quotas")
    for split in ("dev", "test"):
        if any(settings["generation"][split][key] > settings["retrieval"][split][key]
               for key in ("answerable", "unanswerable")):
            raise ValueError("Generation quotas exceed retrieval quotas")
    corpus = root / config["output_dir"]
    manifest_path = corpus / "corpus_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    for name, digest in manifest["outputs"].items():
        if sha256(corpus / name) != digest:
            raise ValueError(f"Corpus artifact changed: {name}")
    paper_rows = load_jsonl(corpus / "papers.jsonl")
    paragraph_rows = load_jsonl(corpus / "paragraphs.jsonl")
    papers = {p["paper_id"]: p for p in paper_rows}
    paragraphs = {p["paragraph_id"]: p for p in paragraph_rows}
    if len(papers) != len(paper_rows) or len(paragraphs) != len(paragraph_rows):
        raise ValueError("Duplicate/cross-split paper or paragraph ID")
    dev = {p for p, row in papers.items() if row["split"] == "dev"}
    test = {p for p, row in papers.items() if row["split"] == "test"}
    if dev & test:
        raise ValueError("Dev/Test paper overlap")
    return root, config, corpus, papers, paragraphs


def fingerprint(config, corpus):
    relevant = {k: config[k] for k in ("dataset_version", "normalization", "evaluation")}
    encoded = json.dumps(relevant, sort_keys=True, ensure_ascii=False).encode()
    return {"corpus_manifest_sha256": sha256(corpus / "corpus_manifest.json"),
            "settings_sha256": hashlib.sha256(encoded).hexdigest(),
            "code_sha256": {name: sha256(Path(__file__).with_name(name))
                            for name in ("dataset.py", "data.py")}}


def counts(rows):
    return {"total": len(rows), "answerable": sum(q["answerable"] for q in rows),
            "unanswerable": sum(not q["answerable"] for q in rows)}


def build_dataset(config_path):
    root, config, corpus, papers, paragraphs = context(config_path)
    settings = config["evaluation"]
    seed = settings["seed"]
    rows = load_jsonl(corpus / "questions.raw.jsonl")
    eligible, excluded, rejected_refs = filter_questions(rows, seed)
    # Validate eligible data too, not just conveniently selected questions.
    validate_questions(eligible, papers, paragraphs)
    selected, generated = {}, {}
    for split in ("dev", "test"):
        selected[split] = sample(eligible, split, settings["retrieval"][split], seed)
        generated[split] = sample(selected[split], split, settings["generation"][split], seed)
    all_selected = selected["dev"] + selected["test"]
    review = sorted(selected["dev"], key=lambda q: rank_key(q, seed))[:settings["dev_review_count"]]
    selected_ids = {q["question_id"] for q in all_selected}
    report = {"eligible": {s: counts([q for q in eligible if q["split"] == s])
                           for s in ("dev", "test")},
              "retrieval": {s: counts(qs) for s, qs in selected.items()},
              "generation": {s: counts(qs) for s, qs in generated.items()},
              "requested": {k: settings[k] for k in ("retrieval", "generation")},
              "exclusion_reasons": dict(Counter(f"{r['split']}:{r['reason']}" for r in excluded)),
              "invalid_annotations": len(rejected_refs),
              "eligible_not_sampled": len(eligible) - len(all_selected),
              "dev_review_count": len(review), "human_review": "pending",
              "model_calls": 0, "system_scores_used": False}
    out = corpus / "evaluation" / settings["version"]
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="dataset-", dir=out.parent) as temp:
        stage = Path(temp)
        for split in ("dev", "test"):
            write_jsonl(stage / f"questions.{split}.jsonl", selected[split])
            write_json(stage / f"generation.{split}.ids.json", [q["question_id"] for q in generated[split]])
            write_json(stage / f"gold.retrieval.{split}.json", official_gold(selected[split], papers))
            write_json(stage / f"gold.generation.{split}.json", official_gold(generated[split], papers))
        write_json(stage / "review.dev.ids.json", [q["question_id"] for q in review])
        write_jsonl(stage / "excluded.questions.jsonl", excluded)
        write_jsonl(stage / "excluded.annotations.jsonl", rejected_refs)
        write_jsonl(stage / "eligible.not_sampled.jsonl", [
            {"question_id": q["question_id"], "split": q["split"]}
            for q in eligible if q["question_id"] not in selected_ids])
        write_json(stage / "selection_report.json", report)
        freeze = {"version": settings["version"], "rules": RULES, "settings": settings,
                  "input": fingerprint(config, corpus),
                  "review_status_at_freeze": "pending_user_review",
                  "selections": {s: [{"question_id": q["question_id"], "paper_id": q["paper_id"],
                                      "answerable": q["answerable"],
                                      "annotation_ids": [r["annotation_id"] for r in q["references"]]}
                                     for q in qs] for s, qs in selected.items()},
                  "generation_ids": {s: [q["question_id"] for q in qs] for s, qs in generated.items()},
                  "files": {p.name: sha256(p) for p in sorted(stage.iterdir())}}
        existing = out / "freeze.json"
        if existing.exists():
            old = json.loads(existing.read_text())
            if {k: v for k, v in old.items() if k != "frozen_at_utc"} != freeze:
                raise ValueError("Frozen dataset changed: create a new evaluation version")
            freeze["frozen_at_utc"] = old["frozen_at_utc"]
        else:
            freeze["frozen_at_utc"] = datetime.now(timezone.utc).isoformat()
        write_json(stage / "freeze.json", freeze)
        out.mkdir(exist_ok=True)
        for path in stage.iterdir():
            if (out / path.name).exists() and sha256(out / path.name) != sha256(path):
                raise ValueError(f"Frozen artifact changed: {path.name}")
        for path in stage.iterdir():
            if not (out / path.name).exists():
                path.replace(out / path.name)
    # Only IDs/hashes/rules go into the public snapshot; full text and gold remain ignored.
    public = root / "configs" / f"evaluation-{settings['version']}.freeze.json"
    if public.exists() and sha256(public) != sha256(out / "freeze.json"):
        raise ValueError("Public freeze differs; not overwriting")
    if not public.exists():
        write_json(public, freeze)
    create_review(root, review, papers, settings["version"])
    return {"output_dir": str(out), **report, "freeze_sha256": sha256(out / "freeze.json")}


def create_review(root, rows, papers, version):
    """Create a user worksheet outside the immutable dataset. Never mark it reviewed."""
    path = root / "artifacts" / "t3" / version / "dev-review.md"
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Dev 人工核验（待用户完成）", "",
             "核对题意、参考答案和每组完整证据。不同组可替代，同组内证据共同需要。",
             "无答案仅表示该论文中不可回答，不代表现实中不存在答案。",
             "此文件不含模型预测；勾选不自动修改冻结题集。", ""]
    for i, row in enumerate(rows, 1):
        lines += [f"## {i}. {row['question_id']}", "",
                  f"论文：{papers[row['paper_id']]['title']}（{row['paper_id']}）",
                  f"问题：{row['question']}", f"可回答：{row['answerable']}", ""]
        for ref in row["references"]:
            lines += [f"参考组：{ref['annotation_id']}",
                      "答案：" + json.dumps(ref["answer"], ensure_ascii=False), ""]
            for evidence in ref["gold_evidence"]:
                lines += [f"证据：{evidence['paragraph_id']} [{evidence['start']}, {evidence['end']})",
                          evidence["evidence_text"], ""]
        lines += ["- [ ] 用户已核对（结论与疑点：待填写）", ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def validate_dataset(config_path):
    root, config, corpus, papers, paragraphs = context(config_path)
    settings = config["evaluation"]
    out = corpus / "evaluation" / settings["version"]
    freeze = json.loads((out / "freeze.json").read_text())
    if freeze["input"] != fingerprint(config, corpus) or freeze["rules"] != RULES:
        raise ValueError("Frozen inputs/rules/code changed")
    public = root / "configs" / f"evaluation-{settings['version']}.freeze.json"
    if sha256(public) != sha256(out / "freeze.json"):
        raise ValueError("Public/local freeze mismatch")
    for name, digest in freeze["files"].items():
        if sha256(out / name) != digest:
            raise ValueError(f"Frozen artifact changed: {name}")
    selections = {s: load_jsonl(out / f"questions.{s}.jsonl") for s in ("dev", "test")}
    validate_questions(selections["dev"] + selections["test"], papers, paragraphs)
    dev_papers = {q["paper_id"] for q in selections["dev"]}
    test_papers = {q["paper_id"] for q in selections["test"]}
    if dev_papers & test_papers:
        raise ValueError("Dev/Test paper overlap")
    for split, rows in selections.items():
        expected = freeze["selections"][split]
        actual = [{"question_id": q["question_id"], "paper_id": q["paper_id"],
                   "answerable": q["answerable"],
                   "annotation_ids": [r["annotation_id"] for r in q["references"]]} for q in rows]
        if actual != expected or any(q["split"] != split for q in rows):
            raise ValueError("Selection split/ID mismatch")
        ids = json.loads((out / f"generation.{split}.ids.json").read_text())
        by_id = {q["question_id"]: q for q in rows}
        if len(ids) != len(set(ids)) or not set(ids) <= by_id.keys():
            raise ValueError("Generation IDs must be a unique subset")
        if ids != freeze["generation_ids"][split]:
            raise ValueError("Generation IDs mismatch")
        for stage, subset in (("retrieval", rows), ("generation", [by_id[qid] for qid in ids])):
            gold = json.loads((out / f"gold.{stage}.{split}.json").read_text())
            if gold != official_gold(subset, papers):
                raise ValueError("Official gold/selected references mismatch")
    return {"status": "structural_validation_passed", "version": settings["version"],
            "retrieval": {s: counts(qs) for s, qs in selections.items()},
            "human_review": "pending_user_review_not_automatically_certified",
            "freeze_sha256": sha256(out / "freeze.json"), "model_calls": 0}
