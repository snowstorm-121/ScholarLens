import json

import pytest

from scripts import t7_analyze as report


def test_generation_directory_label_cannot_override_actual_method(tmp_path, monkeypatch):
    folder = tmp_path / "artifacts/evaluation"
    initial = [folder / f"t7-1600-{m}-v2" for m in ("bm25", "dense", "hybrid")]
    initial.append(folder / "t7-2400-hybrid-v2")
    for path in initial:
        path.mkdir(parents=True)
        (path / "manifest.json").write_text(json.dumps({"code_sha256": {}}))
    wrong = folder / "t7-1600-dense-generation-v2"
    wrong.mkdir()
    (wrong / "manifest.json").write_text(json.dumps({"method": "hybrid", "stage": "generation", "split": "dev"}))
    monkeypatch.setattr(report, "ROOT", tmp_path)
    monkeypatch.setattr(report.sys, "argv", ["t7_analyze.py", "--phase", "report"])
    monkeypatch.setattr(report, "choose_chunking", lambda _: 1600)
    monkeypatch.setattr(report, "matrix", lambda: (initial, 1600))
    monkeypatch.setattr(report, "choose_method", lambda *args: "dense")
    monkeypatch.setattr(report, "selected_snapshot", lambda _: {"selection": {}})
    def unexpected_scoring(*args):
        raise AssertionError("Wrong-method batch must be rejected before scoring")
    monkeypatch.setattr(report, "recompute", unexpected_scoring)
    with pytest.raises(ValueError, match="method"):
        report.main()
