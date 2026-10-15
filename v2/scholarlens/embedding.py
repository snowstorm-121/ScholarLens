"""Local-only Nomic encoding with explicit task roles and no silent truncation."""

import numpy as np
import ollama


def task_input(text, role):
    prefix = {"document": "search_document: ", "query": "search_query: "}[role]
    other = "search_query:" if role == "document" else "search_document:"
    if text.lstrip().startswith(other):
        raise ValueError("Embedding task prefix belongs to the wrong role")
    while text.startswith(prefix):
        text = text[len(prefix):]
    return prefix + text


class NomicEncoder:
    def __init__(self, config, client=None):
        self.config = config
        self.client = client or ollama.Client(host="http://127.0.0.1:11434", timeout=180, trust_env=False)

    def verify_model(self):
        models = self.client.list().models
        actual = next((m for m in models if m.model in (self.config["model"], self.config["model"] + ":latest")), None)
        if actual is None or actual.digest != self.config["model_digest"]:
            raise ValueError("Nomic model digest differs from index configuration")
        return actual.digest

    def encode(self, texts, role):
        if not texts:
            return np.empty((0, self.config["dimensions"]), dtype=np.float32)
        payload = [task_input(text, role) for text in texts]
        response = self.client.embed(model=self.config["model"], input=payload,
                                     truncate=False, keep_alive="30m")
        vectors = np.asarray(response.embeddings, dtype=np.float32)
        if vectors.shape != (len(texts), self.config["dimensions"]) or not np.isfinite(vectors).all():
            raise ValueError("Embedding shape/dtype/finite-value check failed")
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        if np.any(norms < 1e-8):
            raise ValueError("Zero embedding")
        return vectors / norms
