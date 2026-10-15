"""Bridge think=False to the native SDK used by pinned langchain-ollama 0.1.3."""

from functools import partial

from kotaemon.llms import LCOllamaChat


class LocalOllamaChat(LCOllamaChat):
    def __init__(self, **params):
        super().__init__(**params)
        # This pinned LangChain adapter predates its public reasoning option.
        # Native ollama 0.6.0 supports think; enforce it at both SDK call sites.
        self._obj._client.chat = partial(self._obj._client.chat, think=False)
        self._obj._async_client.chat = partial(self._obj._async_client.chat, think=False)
