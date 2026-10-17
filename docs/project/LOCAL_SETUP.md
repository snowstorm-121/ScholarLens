# ScholarLens — local operation and verification

ScholarLens is a local assistant for checking claims and experimental details in AI papers.
Select one paper, ask a question, then inspect the answer's source paragraph and audit trail.
It is a paper-scoped research prototype, not a cross-paper review agent or production service.

This source snapshot reuses [Kotaemon](https://github.com/Cinnamon/kotaemon).
See [UPSTREAM.md](../../UPSTREAM.md) and the retained [LICENSE.txt](../../LICENSE.txt). The T1 application uses upstream indexing,
vector retrieval, Gradio and citation QA. The project adds QASPER data/evaluation preparation
and a paper-scoped BM25/Dense/RRF indexing and retrieval adapter, with a reproducible evaluation runner.

## Start on this Mac

Run the shell commands in this guide from the repository root unless noted otherwise.

Open **Ollama** from Applications first. The desktop app manages the model server;
do not also run `ollama serve`. Alternatively, this launcher opens the same app:

```sh
bash scripts/start_ollama.sh
```

Then start the selected, formally evaluated RAG configuration in a terminal from the repository root:

```sh
SCHOLAR_CONFIG="$PWD/configs/selected_config.json" bash scripts/start_app.sh
```

Open http://127.0.0.1:7860/. Both services use this machine only.
If a service is already running, reuse it instead of launching a duplicate on the same port.
Ollama 0.15.6 is installed at `/Applications/Ollama.app`. Models are in
`~/.ollama/models`, cloned from the original project-local store without downloading again.
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
otherwise retained for this historical smoke check. The separate T4 collection uses paragraph
spans and explicit task prefixes; it does not silently replace this historical index.

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

T2 conversion alone did not build embeddings. T4 now indexes all 1,584 usable papers into
82,491 chunks in a separate collection. T3 sampling/freezing and the user-delegated assistant review are complete;
independent human review was not performed, and reference risks remain documented.
Formal Test scoring is complete; see the T8 results below. The earlier T2/T3/T7 sections
retain their historical development context.

## T3: freeze and validate evaluation data

```sh
.venv/bin/python -m scholarlens.cli freeze --config configs/local.json
.venv/bin/python -m scholarlens.cli validate --config configs/local.json
.venv/bin/python -m pytest tests_scholarlens -q
```

Retrieval Dev/Test contain 200/300 questions. Generation subsets contain 50/100
questions already included in those sets. No model scores were used for selection.
Full questions/gold stay in the ignored data directory; public IDs/hashes/rules are
in `configs/evaluation-v1.freeze.json`. Changed inputs or outputs require a new version.
The original user worksheet at `artifacts/t3/v1/dev-review.md` is not marked as human-reviewed.
The delegated assistant review is separately recorded in `artifacts/t3/v1/assistant-review.json`
and `reports/t3-review.md`. See `reports/t3-dataset.md` for exact filters and limitations.

## T4: one shared indexing/retrieval adapter

```sh
.venv/bin/python -m scholarlens.cli index --config configs/local.json
.venv/bin/python scripts/t4_verify.py
.venv/bin/python -m scholarlens.cli retrieve --config configs/local.json \
  --paper-id 1601.01705 --query "Which release of the VQA dataset do the authors use?" --method hybrid --k 5
```

The registered collection is **ScholarLens QASPER 1600-200**, separate from the T1 HTML samples.
Use the title keyword filter and select exactly one paper from this collection.
Use the retrieval setting `ScholarLens retrieval` to choose BM25, Dense or RRF Hybrid.
Do not select all papers: joint cross-paper retrieval is outside this version's scope.

`index` resumes by stable IDs; it does not silently replace changed source files or fingerprints.
`--limit 2` is an optional train-only pilot, not a full-build acceptance result.
Both UI and CLI use the registered pipeline and existing SQL identity tables, LanceDB and Chroma.
The CLI rejects settings that differ from the currently registered UI configuration; it does not
silently substitute default settings. Change the active configuration and collection explicitly
for future experiments. Keep frozen question/answer exports out of index inputs.

See `reports/t4-indexing.md` for invariants, U1/U2 calculations, regression tests and acceptance results.
Local generated index mappings and runtime verification are Git-ignored under `data/indexes/`
and `artifacts/t4/`. Do not run simultaneous indexing processes or launch duplicate web servers.

## T5: shared real QA and evidence UI

The active page now uses ScholarQA. Search titles in the ScholarLens collection, select one
paper, ask a question, and click its citation to inspect the actual evidence and audit JSON.
The old T1 collection remains stored, but the new QA accepts only the ScholarLens collection;
historical T1 smoke scripts exercise legacy components, not this active pipeline.

```sh
.venv/bin/python -m scholarlens.cli ask --config configs/local.json \
  --paper-id 1601.01705 --query "Which release of the VQA dataset do the authors use?" --method hybrid
.venv/bin/python -m pytest tests_scholarlens -q
.venv/bin/python scripts/t5_verify.py
```

The verification script needs previously saved T5 smoke artifacts and the existing local models.
Shared `qa.answer()` enforces whole-block 4500-token/5-chunk budgets and exact citation membership.
Generation settings live in `configs/local.json`; actual wire requests are captured, and failures
are not converted to refusals or Mock output. Generation is serialized across local processes.
121 tests pass. Three Dev demos are not a benchmark: one multi-evidence case misses part of gold;
a synthetic injection case answers the fact but fails the strict output protocol. No Test scoring.
This sentence describes T5 only; formal T8 Test results are reported below.
See `reports/t5-qa.md` and `reports/t5-interview-log.md` for retained failures and limitations.

## T6: reproducible metric/runner acceptance

```sh
.venv/bin/python -m scholarlens.cli evaluate --config configs/local.json \
  --split train --stage retrieval --method hybrid
.venv/bin/python -m scholarlens.cli evaluate --config configs/local.json \
  --split train --stage generation --method hybrid
.venv/bin/python scripts/t6_verify.py
```

The last command needs the recorded final T6 smoke artifacts and makes no model calls.
Train always uses the fixed three-answerable/two-unanswerable smoke set, selected before predictions.
At T6, Dev interfaces were ready but comparisons had not run, and Test was still locked.
T7 and T8 later completed those stages; see below.
Use `--experiment-id NAME --resume` only with identical code/config/data/runtime; saved failures are not retried.
Reports include immutable per-question predictions, actual context and independent original-paragraph
Evidence F1 adaptation. Missing/failed answers keep their denominator and zero official F1; a later model
failure does not erase successfully observed retrieval/context coverage. Empty citation rates are N/A.
150 tests pass; actual five-question results have failures and are not quality benchmarks.
Read `reports/t6-evaluation.md`, `reports/t6-interview-log.md`, and `scholarlens/vendor/README.md`.

## T7: bounded Dev comparisons

Status: six Dev retrieval runs and one 50-question generation run completed and recomputed;
the 2400/200 Dense configuration was frozen pending T8 authorization at that time.
T8 was subsequently authorized and run once; U3 was completed by the assistant at the user's request.
This is not a quality-certified final release; see `reports/t7-freeze.md`.
Independent snapshots are `configs/dev-1600.json` and `configs/dev-2400.json`.
Set `SCHOLAR_CONFIG` before starting a **new process**, using the same path as `--config`:

```sh
SCHOLAR_CONFIG="$PWD/configs/dev-2400.json" .venv/bin/python -m scholarlens.cli index \
  --config configs/dev-2400.json
SCHOLAR_CONFIG="$PWD/configs/dev-2400.json" .venv/bin/python -m scholarlens.cli evaluate \
  --config configs/dev-2400.json --split dev --stage retrieval --method hybrid \
  --experiment-id YOUR_NEW_EXPERIMENT_ID
```

Do not run these commands concurrently with an active index build or reuse an existing experiment ID.
The no-environment-variable path remains `configs/local.json`; it is not silently replaced.
Changing the environment after imports is rejected, and editing an active configuration file during
an experiment is not supported. A selection snapshot is not authorization to score Test.

T7 Dense reads stored vectors with Chroma's native paper/file metadata filter and computes exact
squared-L2 scores within that paper. It does not perform whole-library ANN retrieval.
This fixed a filtered HNSW full-enumeration failure; all old `t7-1600-*-v1` batches are retained but
invalidated, and selection uses only consistently rerun `*-v2` batches.

The Dev analysis phases `scripts/t7_analyze.py --phase chunk`, `--phase select`, and
`--phase report` created the historical selection. After freezing, `--phase report` deliberately
rejects overwriting `configs/selected_config.json`; it is not the replay command. For the current
configuration, run the verification below with Ollama available. LlamaIndex's local cache already
contains `punkt_tab`, so this process skips its redundant import-time download call:

```sh
SCHOLAR_CONFIG="$PWD/configs/selected_config.json" .venv/bin/python -c 'import nltk, runpy; nltk.download = lambda *args, **kwargs: True; runpy.run_path("scripts/t7_verify.py", run_name="__main__")'
```

This recomputes all saved Dev rows and official batch scores, audits source spans and actual model
context/requests, checks native stores, and compares the selected UI default with CLI on one train
retrieval probe (local embedding only, no generated answer or Test scoring). See
`reports/t7-freeze.md` and `reports/t7-interview-log.md` for the freeze and troubleshooting record.

All 1,584 papers are present in each collection: 82,491 chunks at 1600/200 and 81,670 at 2400/200.
The selected Dev EvidenceRecall@5 is 0.649321, AllEvidence@5 is 0.6, and MRR@10 is 0.472617.
Generation has 9/50 truncation errors, 13/40 answerable refusals, and only 24/30 traced citations;
the whole-set Answer F1 of 0.251667 is not a semantic correctness guarantee.
See `reports/dev-retrieval.md`, `reports/dev-generation.md`, `reports/dev-errors.md`, and `reports/t7-u3.md`.
To launch the candidate explicitly, use `SCHOLAR_CONFIG="$PWD/configs/selected_config.json" bash scripts/start_app.sh`
in a fresh process. The ordinary launcher still uses unchanged `configs/local.json` (1600/Hybrid).

## T8/T9: formal result and job-search handoff

QASPER v0.3 supplied 1,584 usable paper bodies. Questions and gold evidence were exported
separately from index inputs. Retrieval Dev/Test contain 200/300 frozen questions; generation
uses 50/100-question subsets. Assistant-assisted review is not independent human annotation.
See `reports/t3-dataset.md`, `reports/t3-review.md`, and `configs/evaluation-v1.freeze.json`.

The pipeline is: normalized paper paragraphs → position-preserving chunks → Nomic vectors
and BM25 index → paper-scoped BM25/Dense/RRF retrieval → Top-5 context → local Qwen answer
→ exact-quote citation check and audit. `scholarlens/` implements the project-specific data,
retrieval and evaluation path; the Gradio application, storage and model integrations reuse
upstream components. The selected 2400/200 Dense configuration was chosen on Dev, then
held fixed for Test. The six-row chunk/method comparison is in `reports/dev-retrieval.md`.

Under identical 2400/200 Test conditions, BM25/Dense/Hybrid EvidenceRecall@5 was
0.4654/0.6290/0.5901, respectively, on 240 answerable questions. The local 100-question
generation subset scored Answer F1 0.3347 and Evidence F1 0.3790; 9 calls truncated,
22/80 answerable questions were incorrectly refused, and 17/20 unanswerable questions
were correctly refused. These are sample-specific results, not guarantees. Exact denominators,
limits and saved-run locations are in `reports/test.md`.

For a live demonstration, filter the **ScholarLens QASPER 2400-200** collection by title,
select only `Learning to Compose Neural Networks for Question Answering · 1601.01705`,
ask “Which release of the VQA dataset do the authors use?”, and inspect the citation
panel. A fresh-process check answered VQA 1.0 and linked paragraph `1601.01705:s7:p1`.
The selected paper restriction matters: selecting all papers is not a supported cross-paper
evaluation. Use `reports/t9-demo.md` for the demo status and steps, `reports/t9-failures.md`
for three distinct failure modes, and `reports/t9-interview.md` for an honest 60-second
description and resume bullet.

Raw archives, full text, indexes, model files and run artifacts are intentionally ignored
by Git. This machine has the prepared corpus and models; a new machine must acquire and
verify the archives listed in `configs/selected_config.json` before indexing. Reproduction
commands and the verifier are in the T2–T8 sections above. This README does not claim a
one-command cross-platform installation or a fresh full re-evaluation.
