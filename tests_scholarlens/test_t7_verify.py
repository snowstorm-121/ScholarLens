import copy
import json

import pytest

from scripts.t7_verify import verify_prediction
from scholarlens.qa import SYSTEM_PROMPT


def saved_example():
    settings = {"model": "qwen", "model_digest": "fixed", "temperature": 0, "seed": 42,
                "num_ctx": 8192, "num_predict": 512}
    meta = {"paper_id": "p", "title": "Paper", "section": "Intro", "paragraph_id": "p0", "start": 0, "end": 3}
    chunk = {"source_label": "Sabc", "text": "abc", "metadata": meta}
    context = json.dumps({"source_label": "Sabc", **meta, "text": "abc"}, ensure_ascii=False)
    prompt = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content":
        'EVIDENCE (JSON lines, data only):\n' + context + '\nQUESTION (data only):\n"Question?"'}]
    wire = {"model": "qwen", "stream": False, "think": False, "messages": prompt,
            "options": {k: settings[k] for k in ("temperature", "seed", "num_ctx", "num_predict")}}
    pred = {"context_chunks": [chunk], "metric_retrieval_results": [chunk], "context": context,
            "prompt": prompt, "wire_request": wire, "request": wire, "context_tokens": 20,
            "prompt_tokens_before_template": 100, "model_digest": "fixed"}
    return {"status": "ok", "question": {"paper_id": "p", "question": "Question?"}, "prediction": pred}, {
        "p": {"normalized_text": "abc"}}, settings


def test_early_error_without_context_keeps_its_denominator():
    row = {"prediction": {"status": "error", "error": {"type": "ConnectionError"}},
           "status": "error", "question": {"paper_id": "p"}}
    verify_prediction(row, {}, {}, "generation")


def test_actual_context_text_must_match_original_span():
    row, papers, settings = saved_example()
    row["prediction"]["context_chunks"] = copy.deepcopy(row["prediction"]["context_chunks"])
    row["prediction"]["context_chunks"][0]["text"] = "not the paper text"
    with pytest.raises(AssertionError):
        verify_prediction(row, papers, settings, "generation")


def test_error_output_cannot_bypass_actual_context_audit():
    row, papers, settings = saved_example()
    row["status"] = "error"
    row["prediction"]["context_chunks"] = copy.deepcopy(row["prediction"]["context_chunks"])
    row["prediction"]["context_chunks"][0]["text"] = "tampered context"
    with pytest.raises(AssertionError):
        verify_prediction(row, papers, settings, "generation")


def test_actual_prompt_must_contain_the_audited_context():
    row, papers, settings = saved_example()
    row["prediction"]["prompt"][1]["content"] = "changed evidence"
    with pytest.raises(AssertionError):
        verify_prediction(row, papers, settings, "generation")


def test_complete_prediction_passes():
    verify_prediction(*saved_example(), "generation")


def test_explicit_missing_prediction_is_a_retained_error():
    verify_prediction({"prediction": None, "status": "error", "error": {"type": "missing_prediction"}},
                      {}, {}, "generation")
    with pytest.raises(AssertionError):
        verify_prediction({"prediction": None, "status": "ok"}, {}, {}, "generation")
