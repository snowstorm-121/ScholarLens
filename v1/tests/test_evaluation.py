import sys
import unittest
from pathlib import Path


V1_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V1_ROOT))

from rag.evaluation import validate_questions


class QuestionValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.documents = {"doc-a": "Alpha evidence. Beta evidence."}
        self.valid_question = {
            "question_id": "dev-001",
            "split": "dev",
            "question_type": "single_document_fact",
            "question": "Which phrase appears after Alpha?",
            "answerable": True,
            "gold_evidence": [
                {
                    "doc_id": "doc-a",
                    "evidence_text": "Alpha evidence.",
                    "normalized_start": 0,
                    "normalized_end": 15,
                }
            ],
        }

    def test_accepts_complete_question_and_expected_counts(self) -> None:
        validate_questions(
            [self.valid_question],
            self.documents,
            expected_split_counts={"dev": 1, "test": 0},
            expected_type_counts={"single_document_fact": 1},
        )

    def test_rejects_duplicate_question_id(self) -> None:
        duplicate = dict(self.valid_question)

        with self.assertRaisesRegex(ValueError, "duplicate question_id"):
            validate_questions([self.valid_question, duplicate], self.documents)

    def test_rejects_evidence_for_unanswerable_question(self) -> None:
        question = dict(self.valid_question, question_type="unanswerable", answerable=False)

        with self.assertRaisesRegex(ValueError, "must not have gold evidence"):
            validate_questions([question], self.documents)

    def test_rejects_answerable_unanswerable_question(self) -> None:
        question = dict(self.valid_question, question_type="unanswerable")

        with self.assertRaisesRegex(ValueError, "must set answerable to false"):
            validate_questions([question], self.documents)

    def test_rejects_unknown_document(self) -> None:
        question = dict(self.valid_question)
        question["gold_evidence"] = [dict(self.valid_question["gold_evidence"][0], doc_id="doc-b")]

        with self.assertRaisesRegex(ValueError, "unknown doc_id"):
            validate_questions([question], self.documents)

    def test_rejects_mismatched_evidence_text(self) -> None:
        question = dict(self.valid_question)
        question["gold_evidence"] = [
            dict(self.valid_question["gold_evidence"][0], evidence_text="Beta evidence.")
        ]

        with self.assertRaisesRegex(ValueError, "does not match its normalized span"):
            validate_questions([question], self.documents)

    def test_rejects_cross_evidence_with_only_one_evidence_item(self) -> None:
        question = dict(self.valid_question, question_type="cross_evidence")

        with self.assertRaisesRegex(ValueError, "requires at least two evidence items"):
            validate_questions([question], self.documents)


if __name__ == "__main__":
    unittest.main()
