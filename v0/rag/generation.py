"""Define replaceable answer generation interfaces."""


class MockGenerator:
    def generate(self, prompt: str, sources: list[dict]) -> str:
        labels = ", ".join(item["chunk_id"] for item in sources)
        return f"[mock] 未调用语言模型；可用来源：{labels}"
