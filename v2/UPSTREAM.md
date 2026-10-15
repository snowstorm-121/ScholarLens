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
- T4–T9 indexed application adaptation and controlled experiments are not implemented.
