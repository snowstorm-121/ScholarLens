import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence


QUESTION_TYPES = {
    "single_document_fact",
    "cross_evidence",
    "unanswerable",
    "broad_or_misleading",
}
REQUIRED_QUESTION_FIELDS = {
    "question_id",
    "split",
    "question_type",
    "question",
    "answerable",
    "gold_evidence",
}
REQUIRED_EVIDENCE_FIELDS = {
    "doc_id",
    "evidence_text",
    "normalized_start",
    "normalized_end",
}


def load_questions(path: Path) -> list[dict[str, Any]]:
    """Load non-empty JSONL question records from ``path``."""
    questions = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        record = json.loads(line)
        if not isinstance(record, dict):
            raise ValueError(f"{path}:{line_number} must contain a JSON object")
        questions.append(record)
    return questions


def load_normalized_documents(directory: Path) -> dict[str, str]:
    """Return normalized text keyed by the document id encoded in each filename."""
    return {
        path.stem: path.read_text(encoding="utf-8")
        for path in sorted(directory.glob("*.txt"))
    }


def validate_questions(
    questions: Sequence[Mapping[str, Any]],
    normalized_documents: Mapping[str, str],
    *,
    expected_split_counts: Mapping[str, int] | None = None,
    expected_type_counts: Mapping[str, int] | None = None,
) -> None:
    """Raise ValueError when question records cannot be used for retrieval evaluation."""
    question_ids: set[str] = set()
    split_counts: Counter[str] = Counter()
    type_counts: Counter[str] = Counter()

    for index, question in enumerate(questions, start=1):
        missing_fields = REQUIRED_QUESTION_FIELDS - question.keys()
        if missing_fields:
            raise ValueError(f"question {index} is missing fields: {sorted(missing_fields)}")

        question_id = question["question_id"]
        if not isinstance(question_id, str) or not question_id:
            raise ValueError(f"question {index} has an invalid question_id")
        if question_id in question_ids:
            raise ValueError(f"duplicate question_id: {question_id}")
        question_ids.add(question_id)

        split = question["split"]
        if split not in {"dev", "test"}:
            raise ValueError(f"{question_id} has an invalid split: {split}")
        split_counts[split] += 1

        question_type = question["question_type"]
        if question_type not in QUESTION_TYPES:
            raise ValueError(f"{question_id} has an invalid question_type: {question_type}")
        type_counts[question_type] += 1

        if not isinstance(question["question"], str) or not question["question"].strip():
            raise ValueError(f"{question_id} must contain a non-empty question")
        if not isinstance(question["answerable"], bool):
            raise ValueError(f"{question_id} answerable must be a boolean")
        if question_type == "unanswerable" and question["answerable"]:
            raise ValueError(f"{question_id} unanswerable must set answerable to false")

        evidence_items = question["gold_evidence"]
        if not isinstance(evidence_items, list):
            raise ValueError(f"{question_id} gold_evidence must be a list")
        if not question["answerable"] and evidence_items:
            raise ValueError(f"{question_id} is unanswerable and must not have gold evidence")
        if question["answerable"] and not evidence_items:
            raise ValueError(f"{question_id} is answerable and must have gold evidence")
        if question_type == "cross_evidence" and len(evidence_items) < 2:
            raise ValueError(f"{question_id} cross_evidence requires at least two evidence items")

        for evidence_index, evidence in enumerate(evidence_items, start=1):
            _validate_evidence(question_id, evidence_index, evidence, normalized_documents)

    _validate_counts("split", split_counts, expected_split_counts)
    _validate_counts("question type", type_counts, expected_type_counts)


def _validate_evidence(
    question_id: str,
    evidence_index: int,
    evidence: Any,
    normalized_documents: Mapping[str, str],
) -> None:
    label = f"{question_id} evidence {evidence_index}"
    if not isinstance(evidence, Mapping):
        raise ValueError(f"{label} must be an object")

    missing_fields = REQUIRED_EVIDENCE_FIELDS - evidence.keys()
    if missing_fields:
        raise ValueError(f"{label} is missing fields: {sorted(missing_fields)}")

    doc_id = evidence["doc_id"]
    if not isinstance(doc_id, str) or doc_id not in normalized_documents:
        raise ValueError(f"{label} references an unknown doc_id: {doc_id}")

    evidence_text = evidence["evidence_text"]
    start = evidence["normalized_start"]
    end = evidence["normalized_end"]
    if not isinstance(evidence_text, str) or not evidence_text:
        raise ValueError(f"{label} must contain non-empty evidence_text")
    if isinstance(start, bool) or not isinstance(start, int):
        raise ValueError(f"{label} normalized_start must be an integer")
    if isinstance(end, bool) or not isinstance(end, int):
        raise ValueError(f"{label} normalized_end must be an integer")

    document = normalized_documents[doc_id]
    if not 0 <= start < end <= len(document):
        raise ValueError(f"{label} has an out-of-range normalized span")
    if document[start:end] != evidence_text:
        raise ValueError(f"{label} evidence_text does not match its normalized span")


def _validate_counts(
    label: str,
    actual_counts: Mapping[str, int],
    expected_counts: Mapping[str, int] | None,
) -> None:
    if expected_counts is None:
        return
    for value, expected_count in expected_counts.items():
        actual_count = actual_counts.get(value, 0)
        if actual_count != expected_count:
            raise ValueError(
                f"expected {expected_count} {label} records for {value}, got {actual_count}"
            )
