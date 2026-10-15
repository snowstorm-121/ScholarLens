# ScholarLens — T1 local feasibility

This source snapshot reuses [Kotaemon](https://github.com/Cinnamon/kotaemon).
See `UPSTREAM.md` and the retained `LICENSE.txt`. The T1 application uses upstream indexing,
vector retrieval, Gradio and citation QA. QASPER evaluation and controlled Hybrid are later tasks.

## Start on this Mac

Open **Ollama** from Applications first. The desktop app manages the model server;
do not also run `ollama serve`. Alternatively, this launcher opens the same app:

```sh
bash scripts/start_ollama.sh
```

Then start the RAG application in a terminal from this directory:

```sh
bash scripts/start_app.sh
```

Open http://127.0.0.1:7860/. Both services use this machine only.
If a service is already running, reuse it instead of launching a duplicate on the same port.
Ollama 0.15.6 is installed at `/Applications/Ollama.app`. Models are in
`/Users/yyy/.ollama/models`, cloned from the original project-local store without downloading again.
Unused project-local Ollama runtimes/model backups and installation archives were removed
after desktop migration. `uv` remains project-local; its installation cache was cleaned.
The launcher sets local-only and single-parallel environment variables for this login session;
those `launchctl` settings do not persist after reboot. The RAG app only uses local models.
The desktop app may offer updates; record any runtime change before running experiments.
The application has an independent `.venv` with Python 3.10.22.

## Repeat the smoke check

```sh
.venv/bin/python scripts/t1_smoke.py --index-only
.venv/bin/python scripts/t1_smoke.py
```

The first command imports/reuses two public QASPER train papers and asserts that retrieved
chunks belong to the selected paper. The second calls the same upstream QA components and
writes `artifacts/t1/smoke.json`. These are feasibility checks, not Dev/Test performance scores.

In the Chat tab, choose **Search In File(s)** and `1601.01705.html`, then ask:

> Which release of the VQA dataset do the authors use?

The supporting sentence is "We use the VQA 1.0 release". The original multi-evidence
benchmark question and image-count questions are retained as failed diagnostics.
Check the actual answer and source panel rather than assuming a response proves correctness.

## Configuration and limits

The tested runtime is Ollama 0.15.6. The final model is
`qwen3:4b-instruct-2507-q4_K_M`, the official non-thinking Qwen3 4B variant.
The original `qwen3:4b` produced long reasoning and empty/truncated answers.
A runtime comparison and an experimental template change did not solve that behavior.
The unused original Qwen weights were removed; failed diagnostics remain local.

`flowsettings.py` exposes only native local Qwen and Nomic resources. `t1_components.py`
sets vector-only retrieval, disables reranking and LLM relevance scoring, and enables inline
citations and supplies a concise prompt compatible with the upstream citation parser.
`t1_ollama.py` bridges `think=False` into the native SDK because the pinned old
LangChain wrapper does not expose it. That flag alone did not disable reasoning in the
original model; the final model is specifically non-thinking. Upstream defaults are
otherwise retained for this smoke check; paragraph spans and task prefixes are T4 work.

The successful configuration is locked by upstream `uv.lock`. If installation through the
current proxy stalls, the tested command changes proxy settings only for that process:

```sh
HTTPS_PROXY= HTTP_PROXY= ALL_PROXY= https_proxy= http_proxy= all_proxy= \
UV_HTTP_TIMEOUT=180 UV_CONCURRENT_DOWNLOADS=8 \
.tools/uv/bin/uv sync --python 3.10 --frozen --no-dev
```

Known packaging warning: `uv pip check` flags `grpcio-tools==1.62.3` because its WHEEL
metadata says x86_64. The shipped extension is universal x86_64/arm64 and its native
`protoc --version` check succeeds on this arm64 Mac. Preserve this warning in the T1 report;
do not describe the dependency check as clean or edit installed metadata to hide it.

Raw papers, application databases, tools/models and run logs are Git-ignored. No Test
questions or labels were imported. No Git commit or push is part of T1.

Acceptance record: `reports/t1-feasibility.md`.

## T2: prepare QASPER corpus and evidence positions

```sh
.venv/bin/python -m scholarlens.cli prepare --config configs/local.json
.venv/bin/python -m pytest tests_scholarlens/test_data.py -q
```

See `reports/t2-data.md`. Conversion exports 1,584 usable papers separately from
questions/annotations; one empty-body train paper and its three questions are quarantined.
Stable paragraph IDs and normalized Unicode character spans are independent of chunks.
The cached official archives and exported corpus are Git-ignored. Changed hashes fail closed;
repeat conversions do not append records or silently overwrite changed output.

This does not build embeddings or change the UI corpus: the web app still uses the two T1
papers until T4/T5. T3 evaluation sampling/freezing and Test scoring have not run.
