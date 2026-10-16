"""Process isolation keeps active configuration tests from changing other tests."""

import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]


def run_process(code, config=None):
    env = os.environ.copy()
    env.pop("SCHOLAR_CONFIG", None)
    if config:
        env["SCHOLAR_CONFIG"] = str(config)
    # Upstream imports call nltk.download; these factory tests need no tokenizer data.
    code = "import nltk; nltk.download = lambda *args, **kwargs: True\n" + code
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env,
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.fixture
def alternative(tmp_path):
    config = json.loads((ROOT / "configs/local.json").read_text())
    config["output_dir"] = str(ROOT / config["output_dir"])
    config["index"]["chunk_size"] = 2400
    config["index"]["name"] = "active-config-unit-test"
    path = tmp_path / "configs/alternative.json"
    path.parent.mkdir()
    path.write_text(json.dumps(config))
    return path


def test_no_environment_keeps_local_default():
    run_process("""
from scholarlens.indexing import ROOT, active_config_path, index_context
assert active_config_path() == ROOT / 'configs/local.json'
assert index_context() == index_context(ROOT / 'configs/local.json')
""")


def test_saved_settings_missing_new_index_option_use_current_default(monkeypatch):
    import ktem.pages.settings as settings_page

    class SavedSession:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def exec(self, statement):
            return SimpleNamespace(all=lambda: [SimpleNamespace(setting={"old": "saved"})])

    monkeypatch.setattr(settings_page, "Session", lambda engine: SavedSession())
    page = SimpleNamespace(_settings_dict={"old": "default", "index.options.3.scholar_method": "dense"},
                           component_names=lambda: ["old", "index.options.3.scholar_method"])
    state, old, method = settings_page.SettingsPage.load_setting(page)
    assert state["old"] == old == "saved"
    assert state["index.options.3.scholar_method"] == method == "dense"


def test_new_process_uses_alternative_for_index_registration_and_qa(alternative):
    run_process("""
import json
import os
from pathlib import Path
from scholarlens.indexing import active_config_path, index_context
assert active_config_path() == Path(os.environ['SCHOLAR_CONFIG'])
assert index_context()[1]['index']['chunk_size'] == 2400
import flowsettings
assert flowsettings.KH_INDICES[-1]['name'] == 'active-config-unit-test'
from scholarlens import qa
config = json.loads(active_config_path().read_text())
# Stop at selection, before any retriever, tokenizer, or generator invocation.
for supplied in (None, config):
    result = qa.answer('', None, supplied, audit_dir=Path(os.environ['SCHOLAR_CONFIG']).parent / 'audit')
    assert result['config']['index']['chunk_size'] == 2400
    assert result['status'] == 'error'
""", alternative)


def test_explicit_other_index_rejected_before_application_creation(alternative):
    run_process("""
from scholarlens.indexing import ROOT
from scholarlens.framework import application_retriever
try:
    application_retriever(ROOT / 'configs/local.json', 'unused')
except ValueError as error:
    assert 'registered UI configuration' in str(error)
else:
    raise AssertionError('Mismatched configuration accepted')
import json
import os
from pathlib import Path
from scholarlens.qa import answer
baseline = json.loads((ROOT / 'configs/local.json').read_text())
result = answer('A question', 'unused', baseline,
                audit_dir=Path(os.environ['SCHOLAR_CONFIG']).parent / 'mismatch-audit')
assert result['status'] == 'error'
assert 'registered UI configuration' in result['error']['message']
""", alternative)


def test_environment_drift_after_settings_import_fails_closed(alternative):
    run_process("""
import os
import flowsettings
from scholarlens.indexing import ROOT, index_context
os.environ['SCHOLAR_CONFIG'] = str(ROOT / 'configs/local.json')
for requested in (None, ROOT / 'configs/local.json'):
    try:
        index_context(requested)
    except ValueError as error:
        assert 'start a new process' in str(error)
    else:
        raise AssertionError('Environment drift accepted')
""", alternative)


@pytest.mark.parametrize("method", ["dense", "bm25"])
def test_active_method_reaches_ui_default_pipeline(alternative, method):
    config = json.loads(alternative.read_text())
    config["index"]["retrieval"]["method"] = method
    alternative.write_text(json.dumps(config))
    run_process("""
from scholarlens.framework import ScholarRetrieverPipeline
from scholarlens.indexing import index_context
expected = index_context()[1]['index']['retrieval']['method']
spec = ScholarRetrieverPipeline.get_user_settings()['scholar_method']
assert spec['value'] == expected, (spec['value'], expected)
settings = {'scholar_method': spec['value']}
pipeline = ScholarRetrieverPipeline.get_pipeline(settings, {})
assert pipeline.method == expected
assert pipeline.scholar_settings == index_context()[1]['index']
override = 'bm25' if expected == 'dense' else 'dense'
assert ScholarRetrieverPipeline.get_pipeline({'scholar_method': override}, {}).method == override
""", alternative)
