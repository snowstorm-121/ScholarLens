import re
from html.parser import HTMLParser


IGNORED_TAGS = {"script", "style"}
BLOCK_TAGS = {"article", "br", "div", "h1", "h2", "h3", "h4", "li", "p", "section"}


class MainTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_main = False
        self.content_tag: str | None = None
        self.ignored_depth = 0
        self.pre_depth = 0
        self.segments: list[tuple[str, bool]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "main" or (tag == "article" and dict(attrs).get("role") == "main"):
            self.in_main = True
            self.content_tag = tag
            return
        if not self.in_main:
            return
        if tag in IGNORED_TAGS:
            self.ignored_depth += 1
        elif self.ignored_depth == 0 and tag == "pre":
            self.pre_depth += 1
            self.segments.append(("\n", False))
        elif self.ignored_depth == 0 and tag in BLOCK_TAGS:
            self.segments.append(("\n", False))

    def handle_endtag(self, tag: str) -> None:
        if tag == self.content_tag:
            self.in_main = False
            self.content_tag = None
            return
        if not self.in_main:
            return
        if tag in IGNORED_TAGS and self.ignored_depth:
            self.ignored_depth -= 1
        elif self.ignored_depth == 0 and tag == "pre":
            self.pre_depth -= 1
            self.segments.append(("\n", False))
        elif self.ignored_depth == 0 and tag in BLOCK_TAGS:
            self.segments.append(("\n", False))

    def handle_data(self, data: str) -> None:
        if self.in_main and self.ignored_depth == 0:
            self.segments.append((data, self.pre_depth > 0))


def normalize_text(segments: list[tuple[str, bool]]) -> str:
    parts: list[str] = []
    plain_text = []

    def flush_plain_text() -> None:
        text = "".join(plain_text).replace("\r\n", "\n").replace("\r", "\n")
        plain_text.clear()
        lines = [re.sub(r"[ \t\f\v]+", " ", line).strip() for line in text.split("\n")]
        compact_lines: list[str] = []
        for line in lines:
            if line or (compact_lines and compact_lines[-1]):
                compact_lines.append(line)
        normalized = "\n".join(compact_lines).strip()
        if normalized:
            parts.append(normalized)

    for text, is_code in segments:
        if is_code:
            flush_plain_text()
            code = text.replace("\r\n", "\n").replace("\r", "\n").strip("\n")
            if code:
                parts.append(code)
        else:
            plain_text.append(text)
    flush_plain_text()
    return "\n\n".join(parts) + "\n"


def extract_normalized_text(html: str) -> str:
    parser = MainTextParser()
    parser.feed(html)
    parser.close()
    if not parser.in_main and not parser.segments:
        raise ValueError("HTML document does not contain a non-empty content element")
    return normalize_text(parser.segments)


def build_chunks(
    doc_id: str,
    text: str,
    *,
    chunk_size: int,
    overlap: int,
) -> list[dict]:
    if chunk_size <= 0 or overlap < 0 or overlap >= chunk_size:
        raise ValueError("chunk_size must be positive and overlap must be smaller")

    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(
            {
                "chunk_id": f"{doc_id}-{len(chunks) + 1:04d}",
                "doc_id": doc_id,
                "chunk_index": len(chunks) + 1,
                "text": text[start:end],
                "normalized_start": start,
                "normalized_end": end,
            }
        )
        if end == len(text):
            break
        start = end - overlap
    return chunks
