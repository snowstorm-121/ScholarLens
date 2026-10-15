"""GGUF-backed local token accounting and whole-chunk context assembly."""

import importlib.metadata
import json

import httpx


class QwenTokenCounter:
    _cache = {}

    def __init__(self, settings, http_client=None):
        key = (settings["model"], settings["model_digest"])
        if http_client is None and key in self._cache:
            self._tokenizer, self.metadata = self._cache[key]
            return
        if http_client is None:
            with httpx.Client(base_url="http://127.0.0.1:11434",
                              timeout=settings["timeout"], trust_env=False) as client:
                self._load(settings, client)
            self._cache[key] = (self._tokenizer, self.metadata)
        else:
            self._load(settings, http_client)

    def _load(self, settings, client):
        response = client.get("/api/tags")
        response.raise_for_status()
        matches = [m for m in response.json()["models"]
                   if settings["model"] in (m.get("name"), m.get("model"))]
        if len(matches) != 1 or matches[0]["digest"] != settings["model_digest"]:
            raise ValueError("Ollama model alias/digest mismatch")
        response = client.post("/api/show", json={"model": settings["model"], "verbose": True})
        response.raise_for_status()
        info = response.json()["model_info"]
        tokens = info["tokenizer.ggml.tokens"]
        kinds = info["tokenizer.ggml.token_type"]
        merges = info["tokenizer.ggml.merges"]
        if (info.get("tokenizer.ggml.pre") != "qwen2"
                or info.get("tokenizer.ggml.model") != "gpt2"
                or info.get("tokenizer.ggml.add_bos_token") is not False
                or len(tokens) != len(kinds) or len(set(tokens)) != len(tokens)):
            raise ValueError("Unsupported GGUF tokenizer metadata")
        from tokenizers import AddedToken
        from transformers import Qwen2TokenizerFast
        from transformers.convert_slow_tokenizer import Qwen2Converter

        backend = Qwen2Converter(None).converted(
            vocab={token: i for i, token in enumerate(tokens)},
            merges=[tuple(merge.split(" ")) for merge in merges])
        # GGUF's qwen2 preprocessor does not normalize Unicode to NFC.
        backend.normalizer = None
        backend.add_special_tokens([
            AddedToken(token, normalized=False, special=True)
            for token, kind in zip(tokens, kinds) if kind in (3, 4)])
        self._tokenizer = Qwen2TokenizerFast(
            tokenizer_object=backend,
            eos_token=tokens[info["tokenizer.ggml.eos_token_id"]])
        self.metadata = {
            "model": settings["model"], "model_digest": settings["model_digest"],
            "vocab_count": len(tokens), "merges_count": len(merges),
            "preprocess": "gguf-qwen2", "normalization": "none",
            "transformers_version": importlib.metadata.version("transformers"),
            "tokenizers_version": importlib.metadata.version("tokenizers"),
        }

    def encode(self, text):
        return self._tokenizer.encode(text, add_special_tokens=False)

    def count(self, text):
        return len(self.encode(text))


def build_context(rows, counter, max_chunks=5, token_budget=4500):
    if max_chunks < 1 or token_budget < 0:
        raise ValueError("Invalid context limits")
    rows = list(rows)
    labels = {}
    for row in rows:
        cid = row["chunk_id"]
        label = "S" + cid[:12]
        if label in labels:
            raise ValueError("Duplicate chunk ID or source label collision")
        labels[label] = cid
    chunks, dropped, lines = [], [], []
    fields = ("paper_id", "title", "section", "paragraph_id", "start", "end")
    for row in rows:
        label = "S" + row["chunk_id"][:12]
        enriched = {**row, "source_label": label}
        if len(chunks) >= max_chunks:
            dropped.append({**enriched, "reason": "max_chunks"})
            continue
        block = {"source_label": label,
                 **{key: row["metadata"][key] for key in fields}, "text": row["text"]}
        line = json.dumps(block, ensure_ascii=False)
        if counter.count("\n".join([*lines, line])) > token_budget:
            dropped.append({**enriched, "reason": "token_budget"})
            continue
        lines.append(line)
        chunks.append(enriched)
    context = "\n".join(lines)
    return {"context": context, "chunks": chunks, "dropped": dropped,
            "tokens": counter.count(context), "tokenizer": counter.metadata}
