import io
import json
import tarfile

import pytest

from scholarlens.data import (
    convert_paper, map_annotation, normalize, prepare, read_archive,
    sha256, unique_object, validate_spans,
)


def paper(text="A useful result."):
    return {"title": "Example", "abstract": "Summary.",
            "full_text": [{"section_name": "Results", "paragraphs": [text]}], "qas": []}


def annotation(evidence=None):
    return {"annotation_id": "a1", "answer": {
        "unanswerable": False, "extractive_spans": ["result"], "yes_no": None,
        "free_form_answer": "", "evidence": evidence or ["A useful result."],
    }}


def bundle(path, entries):
    with tarfile.open(path, "w:gz") as archive:
        for name, payload in entries:
            raw = json.dumps(payload).encode()
            member = tarfile.TarInfo(name)
            member.size = len(raw)
            archive.addfile(member, io.BytesIO(raw))


def test_normalization():
    assert normalize(" e\u0301\r\n\t result\u00a0 ") == "é result"


def test_spans_and_no_gold_in_corpus():
    raw = paper("A\r\n useful\tresult.")
    raw["qas"] = [{"question": "QA_SECRET", "answer": "GOLD_SECRET"}]
    exported, paragraphs = convert_paper("p1", raw, "train")
    reference = map_annotation(annotation(), paragraphs)
    assert reference["valid"]
    assert reference["gold_evidence"][0]["paragraph_id"] == "p1:s0:p0"
    validate_spans(exported, paragraphs, [reference])
    assert "QA_SECRET" not in json.dumps([exported, paragraphs])
    assert "GOLD_SECRET" not in json.dumps([exported, paragraphs])
    assert "qas" not in exported


def test_duplicate_text_is_ambiguous_not_first_match():
    raw = paper()
    raw["full_text"][0]["paragraphs"] *= 2
    _, paragraphs = convert_paper("p1", raw, "train")
    reference = map_annotation(annotation(), paragraphs)
    assert not reference["valid"]
    assert reference["errors"] == ["ambiguous_duplicate_paragraph"]


@pytest.mark.parametrize("body", [[], [{"section_name": "X", "paragraphs": [" \t"]}]])
def test_missing_body_raises(body):
    raw = paper()
    raw["full_text"] = body
    with pytest.raises(ValueError, match="body"):
        convert_paper("p1", raw, "train")


def test_missing_field_raises():
    raw = paper()
    del raw["abstract"]
    with pytest.raises(ValueError, match="Missing abstract"):
        convert_paper("p1", raw, "train")


@pytest.mark.parametrize("name", ["../outside.json", "/absolute.json", "a\\..\\x"])
def test_archive_path_traversal_rejected(tmp_path, name):
    path = tmp_path / "data.tgz"
    bundle(path, [(name, {})])
    with pytest.raises(ValueError, match="Unsafe archive path"):
        read_archive(path, sha256(path), {"train": name})
    assert not (tmp_path.parent / "outside.json").exists()


def test_archive_symlink_rejected(tmp_path):
    path = tmp_path / "data.tgz"
    with tarfile.open(path, "w:gz") as archive:
        member = tarfile.TarInfo("link")
        member.type = tarfile.SYMTYPE
        member.linkname = "/etc/passwd"
        archive.addfile(member)
    with pytest.raises(ValueError, match="Unsafe archive member type"):
        read_archive(path, sha256(path), {})


def test_archive_hash_mismatch_rejected(tmp_path):
    path = tmp_path / "data.tgz"
    bundle(path, [("train.json", {})])
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        read_archive(path, "0" * 64, {"train": "train.json"})


def test_duplicate_json_keys_and_archive_members_rejected(tmp_path):
    with pytest.raises(ValueError, match="Duplicate JSON key"):
        json.loads('{"p1":1,"p1":2}', object_pairs_hook=unique_object)
    path = tmp_path / "data.tgz"
    bundle(path, [("train.json", {}), ("train.json", {})])
    with pytest.raises(ValueError, match="Duplicate archive member"):
        read_archive(path, sha256(path), {"train": "train.json"})


def test_incomplete_group_is_not_silently_shortened():
    _, paragraphs = convert_paper("p1", paper(), "train")
    reference = map_annotation(annotation(["A useful result.", "Missing paragraph."]), paragraphs)
    assert not reference["valid"]
    assert reference["errors"] == ["evidence_not_found"]
    assert len(reference["answer"]["evidence"]) == 2


def test_float_evidence_is_not_treated_as_text():
    _, paragraphs = convert_paper("p1", paper(), "train")
    reference = map_annotation(annotation(["FLOAT SELECTED: Table 1"]), paragraphs)
    assert not reference["valid"]
    assert reference["errors"] == ["float_selected"]


def test_alternative_annotations_remain_separate():
    raw = paper()
    raw["full_text"][0]["paragraphs"].append("Another result.")
    exported, paragraphs = convert_paper("p1", raw, "dev")
    first = map_annotation(annotation(), paragraphs)
    second_raw = annotation(["Another result."])
    second_raw["annotation_id"] = "a2"
    second = map_annotation(second_raw, paragraphs)
    validate_spans(exported, paragraphs, [first, second])
    assert first["valid"] and second["valid"]
    assert first["gold_evidence"] != second["gold_evidence"]
    assert len(first["gold_evidence"]) == len(second["gold_evidence"]) == 1


def test_substring_not_accepted_as_whole_paragraph():
    _, paragraphs = convert_paper("p1", paper(), "train")
    reference = map_annotation(annotation(["useful result"]), paragraphs)
    assert reference["errors"] == ["evidence_not_found"]


def test_multiple_evidence_paragraphs_preserved_together():
    raw = paper()
    raw["full_text"][0]["paragraphs"].append("Another result.")
    exported, paragraphs = convert_paper("p1", raw, "train")
    reference = map_annotation(annotation(["A useful result.", "Another result."]), paragraphs)
    assert reference["valid"] and len(reference["gold_evidence"]) == 2
    validate_spans(exported, paragraphs, [reference])


def test_unanswerable_and_yes_no_false():
    _, paragraphs = convert_paper("p1", paper(), "train")
    raw = annotation()
    raw["answer"].update(unanswerable=True, evidence=[])
    reference = map_annotation(raw, paragraphs)
    assert reference["valid"] and reference["gold_evidence"] == []
    raw = annotation()
    raw["answer"].update(extractive_spans=[], yes_no=False)
    assert map_annotation(raw, paragraphs)["valid"]


def test_bad_span_rejected():
    exported, paragraphs = convert_paper("p1", paper(), "train")
    reference = map_annotation(annotation(), paragraphs)
    reference["gold_evidence"][0]["end"] -= 1
    with pytest.raises(ValueError, match="Evidence span mismatch"):
        validate_spans(exported, paragraphs, [reference])


def make_config(tmp_path, datasets):
    (tmp_path / "configs").mkdir()
    source = tmp_path / "source.tgz"
    bundle(source, [(f"{split}.json", papers) for split, papers in datasets.items()])
    config = tmp_path / "configs/local.json"
    config.write_text(json.dumps({"normalization": "nfc-whitespace-v1", "dataset_version": "fixture",
                                 "output_dir": "data/fixture", "sources": [{
                                     "url": "https://invalid.example/not-needed",
                                     "local_path": "source.tgz", "sha256": sha256(source),
                                     "members": {split: f"{split}.json" for split in datasets}}]}))
    return config


def test_prepare_idempotent_no_qa_leak(tmp_path):
    raw = paper()
    raw["qas"] = [{"question_id": "q1", "question": "QA_SECRET", "answers": [annotation()]}]
    config = make_config(tmp_path, {"train": {"p1": raw}})
    first = prepare(config)
    second = prepare(config)
    assert first["output_hashes"] == second["output_hashes"]
    out = tmp_path / "data/fixture"
    assert len((out / "papers.jsonl").read_text().splitlines()) == 1
    for name in ("papers.jsonl", "paragraphs.jsonl"):
        assert "QA_SECRET" not in (out / name).read_text()
    manifest = json.loads((out / "corpus_manifest.json").read_text())
    assert set(manifest["index_inputs"]) == {"papers.jsonl", "paragraphs.jsonl"}


def test_duplicate_paper_across_splits_rejected(tmp_path):
    config = make_config(tmp_path, {"train": {"p1": paper()}, "test": {"p1": paper()}})
    with pytest.raises(ValueError, match="Duplicate/cross-split"):
        prepare(config)
    assert not (tmp_path / "data/fixture/papers.jsonl").exists()


@pytest.mark.parametrize("kind", ["question", "annotation"])
def test_duplicate_question_or_annotation_id_rejected(tmp_path, kind):
    first, second = paper(), paper()
    first["qas"] = [{"question_id": "q1", "question": "Question", "answers": [annotation()]}]
    other = annotation()
    if kind == "question":
        other["annotation_id"] = "a2"
    second["qas"] = [{"question_id": "q1" if kind == "question" else "q2",
                      "question": "Other", "answers": [other]}]
    config = make_config(tmp_path, {"train": {"p1": first, "p2": second}})
    with pytest.raises(ValueError, match=f"Duplicate {kind} ID"):
        prepare(config)


def test_prepare_rejects_changed_source_without_downloading(tmp_path):
    config = make_config(tmp_path, {"train": {"p1": paper()}})
    with (tmp_path / "source.tgz").open("ab") as stream:
        stream.write(b"changed")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        prepare(config)


def test_missing_archive_json_rejected(tmp_path):
    path = tmp_path / "data.tgz"
    bundle(path, [("README.md", "not executed")])
    with pytest.raises(ValueError, match="Missing JSON member"):
        read_archive(path, sha256(path), {"train": "missing.json"})


def test_missing_body_explicitly_quarantined(tmp_path):
    missing = paper()
    missing["full_text"] = []
    config = make_config(tmp_path, {"train": {"p1": missing, "p2": paper()}})
    result = prepare(config)
    assert result["split_counts"]["train"]["empty_body"] == 1
    assert result["split_counts"]["train"]["papers"] == 1
    rejected = json.loads((tmp_path / "data/fixture/rejected_papers.jsonl").read_text())
    assert rejected["paper_id"] == "p1" and rejected["reason"] == "missing_body"


def test_changed_artifact_not_overwritten(tmp_path):
    config = make_config(tmp_path, {"train": {"p1": paper()}})
    prepare(config)
    target = tmp_path / "data/fixture/papers.jsonl"
    target.write_text("changed\n")
    with pytest.raises(ValueError, match="Existing artifact changed"):
        prepare(config)
    assert target.read_text() == "changed\n"
