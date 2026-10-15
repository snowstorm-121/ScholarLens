import hashlib
import json
from copy import deepcopy

import pytest

from scholarlens.data import convert_paper, map_annotation, prepare
from scholarlens.dataset import (
    build_dataset, filter_questions, official_gold, rank_key, sample,
    validate_dataset, validate_questions,
)
from tests_scholarlens.test_data import annotation, make_config, paper


def question(qid="q1", split="dev", answerable=True):
    pid = f"{split}-paper"
    document, paragraphs = convert_paper(pid, paper(), split)
    raw = annotation()
    raw["annotation_id"] = f"a-{qid}"
    if not answerable:
        raw["answer"].update(unanswerable=True, evidence=[], extractive_spans=[])
    reference = map_annotation(raw, paragraphs)
    row = {"question_id": qid, "paper_id": pid, "split": split,
           "question": "What is the result?", "references": [reference]}
    return row, document, paragraphs


def fixture_config(tmp_path):
    datasets = {}
    for split in ("dev", "test"):
        datasets[split] = {}
        for i in range(4):
            qid = f"{split}-q{i}"
            raw = paper()
            answer = annotation()
            answer["annotation_id"] = f"a-{qid}"
            if i >= 2:
                answer["answer"].update(unanswerable=True, evidence=[], extractive_spans=[])
            raw["qas"] = [{"question_id": qid, "question": f"Question {i}?", "answers": [answer]}]
            datasets[split][f"{split}-p{i}"] = raw
    path = make_config(tmp_path, datasets)
    config = json.loads(path.read_text())
    quotas = {split: {"answerable": 2, "unanswerable": 1} for split in datasets}
    config["evaluation"] = {"version": "v1", "seed": 42, "retrieval": quotas,
                            "generation": {s: {"answerable": 1, "unanswerable": 1}
                                           for s in datasets}, "dev_review_count": 2}
    path.write_text(json.dumps(config))
    prepare(path)
    return path


def test_hash_ranking_is_the_specified_formula():
    row, _, _ = question()
    assert rank_key(row) == (hashlib.sha256(b"42|q1").hexdigest(), "q1")


def test_valid_reference_retained_when_other_reference_invalid():
    row, _, _ = question()
    bad = deepcopy(row["references"][0])
    bad.update(annotation_id="bad", valid=False, errors=["float_selected"])
    row["references"].append(bad)
    selected, excluded, refs = filter_questions([row])
    assert len(selected) == 1 and not excluded
    assert [r["annotation_id"] for r in selected[0]["references"]] == ["a-q1"]
    assert refs[0]["reasons"] == ["float_selected"]


@pytest.mark.parametrize("invalid_conflicting_ref", [False, True])
def test_any_answerability_conflict_excludes_question(invalid_conflicting_ref):
    row, _, _ = question()
    other = deepcopy(row["references"][0])
    other["annotation_id"] = "other"
    other["answer"]["unanswerable"] = True
    if invalid_conflicting_ref:
        other.update(valid=False, errors=["unanswerable_with_evidence"])
    row["references"].append(other)
    selected, excluded, _ = filter_questions([row])
    assert not selected and excluded[0]["reason"] == "answerability_conflict"


def test_all_invalid_references_exclude_not_salvage():
    row, _, _ = question()
    row["references"][0].update(valid=False, errors=["evidence_not_found"])
    selected, excluded, _ = filter_questions([row])
    assert not selected and excluded[0]["reason"] == "no_valid_reference"


def test_dedup_normalizes_case_and_space_deterministically():
    first, _, _ = question("one")
    second, _, _ = question("two")
    second["question"] = " WHAT\tIS THE RESULT? "
    a = filter_questions([first, second])
    b = filter_questions([second, first])
    assert a == b
    assert a[0][0]["question_id"] == min([first, second], key=rank_key)["question_id"]
    assert a[1][0]["reason"] == "duplicate_normalized_question"


def test_same_question_in_different_papers_is_not_duplicate():
    first, _, _ = question("one")
    second, _, _ = question("two")
    second["paper_id"] = "other-paper"
    assert len(filter_questions([first, second])[0]) == 2


def test_duplicate_question_id_raises():
    row, _, _ = question()
    with pytest.raises(ValueError, match="Duplicate question_id"):
        filter_questions([row, row])


def test_train_is_not_sampled_and_empty_question_rejected():
    train, _, _ = question(split="train")
    empty, _, _ = question()
    empty["question"] = "\t "
    selected, excluded, _ = filter_questions([train, empty])
    assert not selected and len(excluded) == 1
    assert excluded[0]["reason"] == "empty_question"


def test_shortfall_does_not_borrow_from_other_split_or_class():
    one, _, _ = question("one")
    two, _, _ = question("two", split="test")
    rows, _, _ = filter_questions([one, two])
    chosen = sample(rows, "dev", {"answerable": 100, "unanswerable": 100}, 42)
    assert [q["question_id"] for q in chosen] == ["one"]


def test_official_gold_preserves_original_text_and_alternative_groups():
    row, document, _ = question()
    selected, _, _ = filter_questions([row])
    other = deepcopy(selected[0]["references"][0])
    other["annotation_id"] = "alternative"
    other["answer"]["evidence"] = ["A\nuseful\tresult."]
    selected[0]["references"].append(other)
    gold = official_gold(selected, {document["paper_id"]: document})
    answers = gold[row["paper_id"]]["qas"][0]["answers"]
    assert len(answers) == 2
    assert answers[1]["answer"]["evidence"] == ["A\nuseful\tresult."]


@pytest.mark.parametrize("mutation", ["wrong_paper", "wrong_span", "partial", "float"])
def test_invalid_evidence_or_incomplete_group_rejected(mutation):
    row, document, paragraphs = question()
    selected, _, _ = filter_questions([row])
    ref = selected[0]["references"][0]
    if mutation == "wrong_paper":
        ref["gold_evidence"][0]["paper_id"] = "other"
    elif mutation == "wrong_span":
        ref["gold_evidence"][0]["end"] -= 1
    elif mutation == "partial":
        ref["answer"]["evidence"].append("Missing")
    else:
        ref["answer"]["evidence"][0] = "FLOAT SELECTED"
    with pytest.raises(ValueError):
        validate_questions(selected, {document["paper_id"]: document},
                           {p["paragraph_id"]: p for p in paragraphs})


def test_build_validate_repeat_and_user_notes_not_overwritten(tmp_path):
    config = fixture_config(tmp_path)
    first = build_dataset(config)
    worksheet = tmp_path / "artifacts/t3/v1/dev-review.md"
    original = worksheet.read_text()
    assert original.count("- [ ]") == 2 and "test-q" not in original
    worksheet.write_text(original + "\nUser note: pending verification\n")
    assert build_dataset(config) == first
    assert worksheet.read_text().endswith("User note: pending verification\n")
    result = validate_dataset(config)
    assert result["retrieval"]["dev"] == {"total": 3, "answerable": 2, "unanswerable": 1}
    assert result["model_calls"] == 0
    assert "pending" in result["human_review"]
    out = tmp_path / "data/fixture/evaluation/v1"
    freeze = json.loads((out / "freeze.json").read_text())
    for split in ("dev", "test"):
        ids = freeze["generation_ids"][split]
        assert len(ids) == 2
        assert set(ids) <= {r["question_id"] for r in freeze["selections"][split]}
    public = tmp_path / "configs/evaluation-v1.freeze.json"
    assert "What is" not in public.read_text()


def test_edited_frozen_artifact_detected_never_overwritten(tmp_path):
    config = fixture_config(tmp_path)
    build_dataset(config)
    target = tmp_path / "data/fixture/evaluation/v1/questions.test.jsonl"
    target.write_text("changed\n")
    with pytest.raises(ValueError, match="Frozen artifact changed"):
        validate_dataset(config)
    with pytest.raises(ValueError, match="Frozen artifact changed"):
        build_dataset(config)
    assert target.read_text() == "changed\n"


def test_changed_settings_require_new_version(tmp_path):
    config = fixture_config(tmp_path)
    build_dataset(config)
    settings = json.loads(config.read_text())
    settings["evaluation"]["seed"] = 43
    config.write_text(json.dumps(settings))
    with pytest.raises(ValueError, match="Frozen inputs"):
        validate_dataset(config)
    with pytest.raises(ValueError, match="Frozen dataset changed"):
        build_dataset(config)


def test_new_version_does_not_touch_previous_freeze(tmp_path):
    config = fixture_config(tmp_path)
    build_dataset(config)
    old = (tmp_path / "data/fixture/evaluation/v1/freeze.json").read_bytes()
    settings = json.loads(config.read_text())
    settings["evaluation"]["version"] = "v2"
    config.write_text(json.dumps(settings))
    build_dataset(config)
    assert (tmp_path / "data/fixture/evaluation/v1/freeze.json").read_bytes() == old
    assert (tmp_path / "artifacts/t3/v2/dev-review.md").exists()


def test_corpus_change_and_public_freeze_change_detected(tmp_path):
    config = fixture_config(tmp_path)
    build_dataset(config)
    public = tmp_path / "configs/evaluation-v1.freeze.json"
    original = public.read_text()
    public.write_text("{}")
    with pytest.raises(ValueError, match="Public/local freeze mismatch"):
        validate_dataset(config)
    public.write_text(original)
    (tmp_path / "data/fixture/paragraphs.jsonl").write_text("changed\n")
    with pytest.raises(ValueError, match="Corpus artifact changed"):
        validate_dataset(config)


def test_official_gold_has_exact_selected_questions(tmp_path):
    config = fixture_config(tmp_path)
    build_dataset(config)
    out = tmp_path / "data/fixture/evaluation/v1"
    freeze = json.loads((out / "freeze.json").read_text())
    for split in ("dev", "test"):
        for stage in ("retrieval", "generation"):
            gold = json.loads((out / f"gold.{stage}.{split}.json").read_text())
            actual = {q["question_id"] for p in gold.values() for q in p["qas"]}
            expected = (set(freeze["generation_ids"][split]) if stage == "generation" else
                        {q["question_id"] for q in freeze["selections"][split]})
            assert actual == expected
