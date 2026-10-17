"""Use the registered UI indexing adapter; resume by stable IDs, never silently reindex."""

import json
import time

from .data import write_json, write_jsonl
from .embedding import NomicEncoder
from .indexing import export_paper_inputs, index_context


def build_index(config_path, limit=None):
    from ktem.main import App

    root, config, corpus, descriptor = index_context(config_path)
    settings = config["index"]
    NomicEncoder(settings["embedding"]).verify_model()
    paths = export_paper_inputs(corpus)
    if limit is not None:
        if limit < 1:
            raise ValueError("Index limit must be positive")
        paths = paths[:limit]
    app = App()
    index = next(i for i in app.index_manager.indices if i.name == settings["name"])
    pipeline = index.get_indexing_pipeline(app.default_settings.flatten(), "default")
    if pipeline.fingerprint != descriptor["fingerprint"]:
        raise ValueError("CLI and UI configurations differ")
    output = root / "data/indexes" / descriptor["fingerprint"]
    output.mkdir(parents=True, exist_ok=True)
    record = output / "fingerprint.json"
    if record.exists() and json.loads(record.read_text()) != descriptor:
        raise ValueError("Index fingerprint artifact mismatch")
    write_json(record, descriptor)
    start = time.monotonic()
    mapping, total = [], 0
    for number, path in enumerate(paths, 1):
        try:
            events = pipeline.stream([path], reindex=False)
            while True:
                try:
                    next(events)
                except StopIteration as done:
                    file_ids, errors, docs = done.value
                    break
            if any(errors) or not all(file_ids):
                raise RuntimeError(f"Index failed: {path.name}: {errors}")
            total += len(docs)
            mapping.append({"paper_id": docs[0].metadata["paper_id"], "file_id": file_ids[0],
                            "chunk_ids": [d.doc_id for d in docs]})
            progress = {"status": "building", "papers": number, "target_papers": len(paths),
                        "chunks": total, "last_paper": path.name, "seconds": time.monotonic() - start}
            write_json(output / "progress.json", progress)
            if number <= 2 or number % 25 == 0:
                print(json.dumps(progress), flush=True)
        except Exception as error:
            write_json(output / "progress.json", {"status": "error", "paper": path.name,
                                                  "error": str(error), "completed_papers": number - 1})
            raise
    write_jsonl(output / "paper_file_chunks.jsonl", mapping)
    summary = {"status": "ready" if limit is None else "partial", "papers": len(paths),
               "chunks": total, "index_id": index.id, "fingerprint": descriptor["fingerprint"],
               "seconds": time.monotonic() - start, "secondary_splitter": None,
               "extra_reranking": False, "query_rewriting": False, "model_scoring": False}
    write_json(output / "manifest.json", summary)
    write_json(output / "progress.json", summary)
    print(json.dumps(summary), flush=True)
    return summary
