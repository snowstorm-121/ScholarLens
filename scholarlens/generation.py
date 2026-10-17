"""Preserve the native response using the existing local model component."""

import json

from filelock import FileLock, Timeout
from t1_ollama import LocalOllamaChat

from .indexing import ROOT


class LocalGenerator:
    def __init__(self, settings, client=None, lock_path=None):
        self.settings = settings
        self.wire_request = None
        self.lock_path = lock_path or ROOT / "artifacts/qa/generation.lock"

        def capture(request):
            if request.url.path == "/api/chat":
                self.wire_request = json.loads(request.content)

        if client is None:
            component = LocalOllamaChat(
                base_url="http://127.0.0.1:11434", model=settings["model"],
                **{key: settings[key] for key in ("temperature", "seed", "num_ctx", "num_predict")},
                client_kwargs={"timeout": settings["timeout"], "trust_env": False,
                               "event_hooks": {"request": [capture]}})
            client = component._obj._client
        self.client = client
        self.request = None
        http = getattr(client, "_client", None)
        self.transport = {"generation_concurrency": 1}
        if http is not None:
            self.transport.update(host=str(http.base_url), timeout=str(http.timeout), trust_env=http.trust_env)
        else:
            self.transport["type"] = "injected_test_client"

    def generate(self, messages):
        self.request = {"model": self.settings["model"], "messages": messages,
                        "stream": False, "think": False,
                        "options": {key: self.settings[key] for key in
                                    ("temperature", "seed", "num_ctx", "num_predict")}}
        models = self.client.list().models
        actual = next((m.digest for m in models if m.model == self.settings["model"]), None)
        if actual != self.settings["model_digest"]:
            raise ValueError("Generation model digest mismatch or model not installed")
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with FileLock(str(self.lock_path), timeout=self.settings["timeout"]):
                response = self.client.chat(**self.request)
        except Timeout as error:
            raise TimeoutError("Timed out waiting for the local generation slot") from error
        return response if isinstance(response, dict) else response.model_dump(mode="json")
