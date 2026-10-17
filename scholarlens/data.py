"""QASPER conversion only: no embeddings, retrieval or evaluation runs.

Corpus exports use an explicit field allowlist. QA annotations never become
index Documents. All character offsets are Python Unicode offsets, [start, end),
in the paper's normalized_text; paragraphs are joined by two newlines.
"""

import hashlib
import json
import re
import tarfile
import tempfile
import unicodedata
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath


NORMALIZATION = "nfc-whitespace-v1"


class MissingBodyError(ValueError):
    """Known source defect; batch conversion must report its quarantine."""


def normalize(text):
    """Normalize a single paragraph; document paragraph boundaries stay external."""
    if not isinstance(text, str):
        raise ValueError("Text must be a string")
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", text)).strip()


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key/ID: {key}")
        result[key] = value
    return result


def read_archive(path, expected_sha256, members):
    """Read only named JSON members in memory, never tar.extractall()."""
    if sha256(path) != expected_sha256:
        raise ValueError(f"SHA-256 mismatch: {path}")
    with tarfile.open(path) as archive:
        seen = set()
        for member in archive.getmembers():
            name = PurePosixPath(member.name)
            if name.is_absolute() or ".." in name.parts or "\\" in member.name:
                raise ValueError(f"Unsafe archive path: {member.name}")
            if not (member.isfile() or member.isdir()):
                raise ValueError(f"Unsafe archive member type: {member.name}")
            if member.name in seen:
                raise ValueError(f"Duplicate archive member: {member.name}")
            seen.add(member.name)
        result = {}
        for split, name in members.items():
            if name not in seen or not archive.getmember(name).isfile():
                raise ValueError(f"Missing JSON member: {name}")
            with archive.extractfile(name) as stream:
                result[split] = json.load(stream, object_pairs_hook=unique_object)
        return result


def fetch_source(source, root):
    path = root / source["local_path"]
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        partial = path.with_suffix(path.suffix + ".partial")
        with urllib.request.urlopen(source["url"], timeout=60) as response:
            with partial.open("wb") as stream:
                for block in iter(lambda: response.read(1024 * 1024), b""):
                    stream.write(block)
        if sha256(partial) != source["sha256"]:
            raise ValueError(f"Downloaded SHA-256 mismatch: {partial}")
        partial.replace(path)
    if sha256(path) != source["sha256"]:
        raise ValueError(f"SHA-256 mismatch: {path}")
    return path


def convert_paper(paper_id, raw, split):
    """Return allowlisted paper/paragraph objects, deliberately excluding qas."""
    for field in ("title", "abstract", "full_text", "qas"):
        if field not in raw:
            raise ValueError(f"Missing {field}: {paper_id}")
    if not normalize(raw["title"]):
        raise ValueError(f"Missing title: {paper_id}")
    sections = raw["full_text"]
    if not any(normalize(p) for section in sections for p in section["paragraphs"]):
        raise MissingBodyError(f"Empty body: {paper_id}")
    source_url = f"https://arxiv.org/abs/{paper_id}"
    paragraphs, parts = [], []
    position = 0
    blocks = [("abstract", "Abstract", -1, 0, raw["abstract"])]
    for section_index, section in enumerate(sections):
        blocks.extend((f"s{section_index}:p{i}", section["section_name"],
                       section_index, i, text)
                      for i, text in enumerate(section["paragraphs"]))
    for suffix, section, section_index, paragraph_index, original in blocks:
        text = normalize(original)
        if not text:
            continue
        if parts:
            position += 2
        paragraphs.append({
            "paper_id": paper_id, "paragraph_id": f"{paper_id}:{suffix}",
            "title": normalize(raw["title"]), "section": normalize(section or ""),
            "section_index": section_index, "paragraph_index": paragraph_index,
            "split": split, "text": text, "original_text": original,
            "start": position, "end": position + len(text), "source_url": source_url,
        })
        parts.append(text)
        position += len(text)
    text = "\n\n".join(parts)
    paper = {"paper_id": paper_id, "split": split, "title": normalize(raw["title"]),
             "abstract": normalize(raw["abstract"]), "normalized_text": text,
             "source_url": source_url, "section_count": len(sections),
             "paragraph_ids": [p["paragraph_id"] for p in paragraphs],
             "text_sha256": hashlib.sha256(text.encode()).hexdigest()}
    return paper, paragraphs


def map_annotation(annotation, paragraphs):
    """A failed member invalidates the entire reference, not just that member."""
    answer = annotation["answer"]
    if type(answer["unanswerable"]) is not bool:
        raise ValueError("unanswerable must be boolean")
    result = {"annotation_id": annotation["annotation_id"], "answer": answer,
              "gold_evidence": [], "errors": []}
    if answer["unanswerable"]:
        if answer["evidence"]:
            result["errors"].append("unanswerable_with_evidence")
    else:
        if not answer["evidence"]:
            result["errors"].append("empty_evidence_group")
        if not (answer["extractive_spans"] or normalize(answer["free_form_answer"])
                or type(answer["yes_no"]) is bool):
            result["errors"].append("missing_reference_answer")
        by_text = {}
        for paragraph in paragraphs:
            by_text.setdefault(paragraph["text"], []).append(paragraph)
        for evidence in answer["evidence"]:
            text = normalize(evidence)
            if "FLOAT SELECTED" in text:
                result["errors"].append("float_selected")
                continue
            matches = by_text.get(text, [])
            if len(matches) != 1:
                result["errors"].append("evidence_not_found" if not matches
                                        else "ambiguous_duplicate_paragraph")
                continue
            paragraph = matches[0]
            result["gold_evidence"].append({
                "paper_id": paragraph["paper_id"],
                "paragraph_id": paragraph["paragraph_id"],
                "start": paragraph["start"], "end": paragraph["end"],
                "evidence_text": text, "original_evidence_text": evidence,
            })
    result["valid"] = not result["errors"]
    # Partial mappings remain diagnostic only, never masquerade as a valid group.
    return result


def validate_spans(paper, paragraphs, annotations):
    by_id = {p["paragraph_id"]: p for p in paragraphs}
    for paragraph in paragraphs:
        if paper["normalized_text"][paragraph["start"]:paragraph["end"]] != paragraph["text"]:
            raise ValueError(f"Paragraph span mismatch: {paragraph['paragraph_id']}")
    for annotation in annotations:
        for evidence in annotation["gold_evidence"]:
            paragraph = by_id[evidence["paragraph_id"]]
            if (evidence["paper_id"] != paper["paper_id"]
                    or evidence["start"] != paragraph["start"]
                    or evidence["end"] != paragraph["end"]
                    or paper["normalized_text"][evidence["start"]:evidence["end"]]
                    != evidence["evidence_text"]):
                raise ValueError("Evidence span mismatch")


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def write_jsonl(path, rows):
    with path.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def prepare(config_path, sample_train=None):
    config_path = Path(config_path).resolve()
    root = config_path.parent.parent
    config = json.loads(config_path.read_text())
    if config["normalization"] != NORMALIZATION:
        raise ValueError("Unsupported normalization version")
    datasets, sources = {}, []
    for source in config["sources"]:
        path = fetch_source(source, root)
        loaded = read_archive(path, source["sha256"], source["members"])
        if datasets.keys() & loaded.keys():
            raise ValueError("Duplicate split")
        datasets.update(loaded)
        sources.append({**source, "bytes": path.stat().st_size})
    out = root / config["output_dir"]
    if sample_train is not None:
        if sample_train <= 0:
            raise ValueError("sample_train must be positive")
        datasets = {"train": {k: datasets["train"][k]
                              for k in sorted(datasets["train"])[:sample_train]}}
        out = out / f"preview-train-{sample_train}"
    out.parent.mkdir(parents=True, exist_ok=True)
    papers, paragraphs, questions, issues, rejected = [], [], [], [], []
    paper_ids, question_ids, annotation_ids = set(), set(), set()
    counts = {}
    for split in sorted(datasets):
        counts[split] = Counter(papers=0, sections=0, paragraphs=0, questions=0,
                                annotations=0, valid_annotations=0,
                                empty_body=0, excluded_questions=0, duplicate_ids=0, parse_failures=0)
        for paper_id, raw in sorted(datasets[split].items()):
            if paper_id in paper_ids:
                raise ValueError(f"Duplicate/cross-split paper ID: {paper_id}")
            paper_ids.add(paper_id)
            try:
                paper, blocks = convert_paper(paper_id, raw, split)
            except MissingBodyError:
                rejected.append({"paper_id": paper_id, "split": split,
                                 "reason": "missing_body", "excluded_questions": len(raw["qas"])})
                counts[split].update(empty_body=1, excluded_questions=len(raw["qas"]))
                continue
            papers.append(paper)
            paragraphs.extend(blocks)
            counts[split].update(papers=1, sections=paper["section_count"], paragraphs=len(blocks))
            for qa in raw["qas"]:
                qid = qa["question_id"]
                if qid in question_ids:
                    raise ValueError(f"Duplicate question ID: {qid}")
                question_ids.add(qid)
                refs = []
                for annotation in qa["answers"]:
                    aid = annotation["annotation_id"]
                    if aid in annotation_ids:
                        raise ValueError(f"Duplicate annotation ID: {aid}")
                    annotation_ids.add(aid)
                    ref = map_annotation(annotation, blocks)
                    refs.append(ref)
                    counts[split].update(annotations=1, valid_annotations=int(ref["valid"]))
                    if ref["errors"]:
                        issues.append({"split": split, "paper_id": paper_id,
                                       "question_id": qid, "annotation_id": aid,
                                       "reasons": ref["errors"]})
                validate_spans(paper, blocks, refs)
                questions.append({"paper_id": paper_id, "question_id": qid,
                                  "split": split, "question": qa["question"],
                                  "references": refs})
                counts[split].update(questions=1)
    reason_counts = Counter(reason for issue in issues for reason in set(issue["reasons"]))
    report = {"split_counts": counts, "issue_annotations": len(issues),
              "rejected_papers": rejected,
              "reason_counts": reason_counts, "sampling_or_evaluation_run": False,
              "span_unit": "Unicode characters in normalized_text, [start,end)",
              "paragraph_count_includes_abstract": True,
              "empty_paragraphs": "omitted without renumbering source positions"}
    with tempfile.TemporaryDirectory(prefix="qasper-convert-", dir=out.parent) as temp:
        stage = Path(temp)
        write_jsonl(stage / "papers.jsonl", papers)
        write_jsonl(stage / "paragraphs.jsonl", paragraphs)
        write_jsonl(stage / "questions.raw.jsonl", questions)
        write_jsonl(stage / "mapping_issues.jsonl", issues)
        write_jsonl(stage / "rejected_papers.jsonl", rejected)
        write_json(stage / "conversion_report.json", report)
        outputs = {p.name: sha256(p) for p in sorted(stage.iterdir())}
        manifest = {"dataset_version": config["dataset_version"],
                    "normalization": NORMALIZATION, "sources": sources,
                    "license": "QASPER annotations: CC BY 4.0; retain original paper rights",
                    "attribution": "Dasigi et al. (2021), QASPER, Allen Institute for AI",
                    "source_catalog": "https://huggingface.co/datasets/allenai/qasper/blob/main/qasper.py",
                    "hash_trust": "locally pinned official downloads; not publisher-signed checksums",
                    "index_inputs": ["papers.jsonl", "paragraphs.jsonl"],
                    "excluded_from_index": ["questions.raw.jsonl", "mapping_issues.jsonl",
                                            "rejected_papers.jsonl"],
                    "outputs": outputs}
        existing = out / "corpus_manifest.json"
        if existing.exists():
            previous = json.loads(existing.read_text())
            if {k: v for k, v in previous.items() if k != "acquired_at_utc"} != manifest:
                raise ValueError("Existing corpus changed: use a new version/output directory")
            manifest["acquired_at_utc"] = previous["acquired_at_utc"]
        else:
            manifest["acquired_at_utc"] = datetime.now(timezone.utc).isoformat()
        write_json(stage / "corpus_manifest.json", manifest)
        out.mkdir(parents=True, exist_ok=True)
        for path in sorted(stage.iterdir()):
            target = out / path.name
            if target.exists() and sha256(target) != sha256(path):
                raise ValueError(f"Existing artifact changed: {target}")
        for path in sorted(stage.iterdir()):
            if not (out / path.name).exists():
                path.replace(out / path.name)
    return {"output_dir": str(out), **report, "output_hashes": outputs}
