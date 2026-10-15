"""Local smoke-test defaults; application behavior remains upstream Kotaemon."""

from ktem.index.file.pipelines import DocumentRetrievalPipeline
from ktem.reasoning.simple import FullQAPipeline


LOCAL_CITATION_PROMPT = """Answer the QUESTION using only the CONTEXT.
Use the paper's reported wording: a range or inequality is a valid answer.
Quote a short supporting span using its exact start/end phrases.
Return ONLY this protocol, with no comments, Markdown headings or analysis:
CITATION LIST
CITATION【1】
START_PHRASE: exact words beginning the supporting span
END_PHRASE: exact words ending the supporting span
FINAL ANSWER
A concise answer followed by 【1】.
If there is no support, omit the citation entry and state that evidence is insufficient.

CONTEXT:
{context}

QUESTION: {question}
"""


class LocalRetrievalPipeline(DocumentRetrievalPipeline):
    @classmethod
    def get_user_settings(cls):
        settings = super().get_user_settings()
        for key, value in {
            "use_reranking": False,
            "use_llm_reranking": False,
            "retrieval_mode": "vector",
            "num_retrieval": 5,
            "mmr": False,
        }.items():
            settings[key]["value"] = value
        return settings


class LocalQAPipeline(FullQAPipeline):
    @classmethod
    def get_pipeline(cls, settings, states, retrievers):
        pipeline = super().get_pipeline(settings, states, retrievers)
        pipeline.answering_pipeline.qa_citation_template = LOCAL_CITATION_PROMPT
        return pipeline

    @classmethod
    def get_user_settings(cls):
        settings = super().get_user_settings()
        settings["highlight_citation"]["value"] = "inline"
        settings["n_last_interactions"]["value"] = 0
        settings["trigger_context"]["value"] = 100000
        return settings
