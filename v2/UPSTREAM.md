# Upstream source and T1 adaptation

- Project: https://github.com/Cinnamon/kotaemon
- Commit: `9ad3e4e49aa35b8acddd235918a5d9753c1cfdf9`
- Imported: 2026-10-14, source archive without a nested `.git`.
- License: preserved in `LICENSE.txt`; upstream attribution remains.
- Reused: Gradio application, file collections, indexing/retrieval, model adapters and QA/citation components.
- T1 changes: local-only configuration, default retrieval settings, concise inline-citation prompt and legacy SDK parameter bridge; project-local tools and independent Python environment.
- Tested model: official `qwen3:4b-instruct-2507-q4_K_M`; original `qwen3:4b` did not complete the constrained QA output reliably in these diagnostics.
- T2 changes: `scholarlens/data.py`, `scholarlens/cli.py`, `configs/local.json` and `tests_scholarlens/` add QASPER corpus/annotation separation, stable paragraph spans, archive/hash validation and deterministic conversion. See `reports/t2-data.md`.
- T3 changes: `scholarlens/dataset.py` adds deterministic filtering/sampling, official-format gold exports, immutable freeze snapshots and structural validation. User-delegated assistant semantic review covers 30 Dev questions, not independent human verification; reference risks are documented. See `reports/t3-dataset.md` and `reports/t3-review.md`.
- T4 additions: `scholarlens/indexing.py`, `embedding.py`, `framework.py`, `build_index.py` and `retrieval.py` implement a QASPER reader and shared FileIndex adapters, paragraph-preserving chunks, role-prefixed Nomic embeddings, stable identity/resumption, paper-scoped BM25/Dense and deterministic RRF. LanceDB/Chroma and SQL file identity tables remain upstream components. See `reports/t4-indexing.md` for verification status.
- T5 additions: shared ScholarQA/CLI answer pipeline, Qwen tokenizer-based whole-block budgets, native Ollama request/response audits, strict context/exact-quote citation checks, error/refusal separation and thin title/evidence UI extensions. Existing application, model and citation components remain reused. Three Dev demos and retained failures are documented in `reports/t5-qa.md`; user oral review remains pending.
- T6 additions: full-span evidence coverage metrics, shared-pipeline train/Dev runner, atomic immutable records, runtime-bound resume and offline recomputation. Official QASPER evaluator is vendored unchanged from allenai/qasper-led-baseline commit `e996b6c7b1b5f95d9308a74e3586416c6e780df1`, with Apache license/source/hash in `scholarlens/vendor/`. Batch factory initializes the registered selector without rendering unrelated Help pages. Only five train smoke questions were run; user manual understanding remains pending.
- T7–T9 formal controlled experiments and final materials are not implemented; Test scoring remains locked.
