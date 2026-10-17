"""Small extensions to the existing FileSelector and chat reasoning interface."""

import html
import json
from urllib.parse import urlsplit

import gradio as gr
from ktem.index.file.ui import FileSelector
from ktem.reasoning.base import BaseReasoning
from ktem.main import App
from kotaemon.base import Document
from sqlalchemy import select
from sqlalchemy.orm import Session

from .framework import ScholarRetrieverPipeline, engine
from .indexing import ROOT
from .qa import answer


class ScholarApp(App):
    def initialize_indices(self):
        super().initialize_indices()
        # Display the active collection first; do not migrate, delete or reindex tables.
        self.index_manager.indices.sort(key=lambda i: not i.config.get(
            "FILE_INDEX_PIPELINE", "").endswith("ScholarIndexPipeline"))

    def ui(self):
        super().ui()
        page = self.chat_page
        page.quick_urls.parent.visible = False
        page.chat_panel.chatbot.placeholder = "先按标题关键词选择一篇论文，再提问并核对右侧证据。"
        page.chat_panel.text_input.placeholder = "询问当前论文的方法、数据集或实验设置（正式评测使用英文）"
        page.chat_control.cb_suggest_chat.visible = False
        page.use_mindmap_check.visible = False
        page.language.interactive = False
        page.model_type.interactive = False
        # Do not issue an extra, unaudited LLM call to name each new conversation.
        page.check_and_suggest_name_conv = lambda history: (gr.update(), False)


class PaperSelector(FileSelector):
    def __init__(self, app, index):
        self.is_scholar = index.config.get("FILE_INDEX_PIPELINE", "").endswith("ScholarIndexPipeline")
        super().__init__(app, index)

    def default(self):
        if not self.is_scholar:
            return super().default()
        return "select", [], "default" if not self._app.f_user_management else None

    def on_building_ui(self):
        if not self.is_scholar:
            return super().on_building_ui()
        mode, files, user_id = self.default()
        self.keyword = gr.Textbox(label="论文标题关键词", placeholder="输入英文标题关键词筛选论文")
        self.mode = gr.Radio(choices=[("当前论文", "select")], value=mode, visible=False)
        self.selector = gr.Dropdown(label="选择一篇论文", value=files, choices=[],
                                    multiselect=True, max_choices=1, filterable=True, interactive=True)
        self.selector_user_id = gr.State(user_id)
        self.selector_choices = gr.JSON(value=[], visible=False)

    def load_files(self, selected_files, user_id, keyword=""):
        if not self.is_scholar:
            return super().load_files(selected_files, user_id)
        source = self._index._resources["Source"]
        with Session(engine) as session:
            rows = session.execute(select(source).where(source.user == user_id)).scalars().all()
            choices = [(f"{r.note['title']} · {r.note['paper_id']}", r.id)
                       for r in rows if r.note.get("complete") and
                       keyword.casefold() in r.note.get("title", "").casefold()]
        choices.sort(key=lambda row: row[0].casefold())
        available = {row[1] for row in choices}
        selected = [cid for cid in (selected_files or []) if cid in available][:1]
        return gr.update(value=selected, choices=choices), choices

    def on_register_events(self):
        if not self.is_scholar:
            return super().on_register_events()
        self.keyword.change(lambda keyword, selected, uid: self.load_files(selected, uid, keyword),
                            inputs=[self.keyword, self.selector, self._app.user_id],
                            outputs=[self.selector, self.selector_choices])
        self.selector.change(lambda: "", inputs=[], outputs=[self._app.chat_page.info_panel])


def evidence_html(result):
    escape = lambda value: html.escape(str(value), quote=True)
    sections = [f"<h3>本次证据 · {escape(result['method'])}</h3>",
                f"<p>状态：{escape(result['status'])} · 实际上下文 {result.get('context_tokens', 0)} tokens · "
                f"{len(result['context_chunks'])} 个完整 chunk</p>"]
    if result["citation_errors"]:
        sections.append("<p><b>引用校验未通过：</b>" + escape(", ".join(result["citation_errors"])) + "</p>")
    paragraph_text = {}
    if result["paper_id"]:
        path = ROOT / "data/qasper/v0.3/paper_inputs" / f"{result['paper_id']}.qasper.json"
        if path.exists():
            paragraph_text = {p["paragraph_id"]: p["text"] for p in json.loads(path.read_text())["paragraphs"]}
    for row in result["context_chunks"]:
        meta = row["metadata"]
        url = meta["source_url"]
        source = (f'<a href="{escape(url)}" target="_blank" rel="noopener noreferrer">原论文来源</a>'
                  if urlsplit(url).scheme in {"http", "https"} else "来源链接无效")
        cited = [c for c in result["citations"] if c["valid"] and c["chunk_id"] == row["chunk_id"]]
        markers = " ".join(f'<span id="evidence-{c["number"]}">【{c["number"]}】</span>' for c in cited)
        sections.append(f"<details open><summary>{markers} {escape(meta['title'])}</summary>"
                        f"<p>{escape(meta['section'])} · {escape(meta['paragraph_id'])}<br>"
                        f"{escape(row['source_label'])} · rank {row['rank']} · "
                        f"{escape(row['method'])} score {row['score']:.8f}（非置信度）<br>"
                        f"字符 [{meta['start']}, {meta['end']}) · {source}</p>"
                        f"<b>实际送入模型的原文片段</b><pre style='white-space:pre-wrap'>{escape(row['text'])}</pre>")
        full = paragraph_text.get(meta["paragraph_id"])
        if full and full != row["text"]:
            sections.append("<details><summary>所属完整段落（查看用，不代表全部送入模型）</summary>"
                            f"<pre style='white-space:pre-wrap'>{escape(full)}</pre></details>")
        sections.append("</details>")
    if result["dropped"]:
        sections.append("<details><summary>未进入 context 的块</summary><pre>" + escape(json.dumps(
            [{"chunk_id": r["chunk_id"], "reason": r["reason"]} for r in result["dropped"]], indent=2)) + "</pre></details>")
    sections.append("<p>引用存在与精确定位不等于关键陈述已被证明；语义支持仍需核对。</p>"
                    "<details><summary>本次完整审计 JSON</summary><pre style='white-space:pre-wrap'>" +
                    escape(json.dumps(result, ensure_ascii=False, indent=2)) + "</pre></details>")
    return "".join(sections)


class ScholarQA(BaseReasoning):
    retrievers: list = []

    @classmethod
    def get_info(cls):
        # The pinned chat controls require the compatibility key 'simple'.
        return {"id": "simple", "name": "研知 ScholarLens", "description": "单篇论文证据问答与审计"}

    @classmethod
    def get_user_settings(cls):
        return {
            "llm": {"name": "固定本地 Qwen", "value": "", "component": "dropdown",
                    "choices": [("Qwen3 4B · 固定配置", "")]},
            "highlight_citation": {"name": "来源校验", "value": "inline", "component": "dropdown",
                                   "choices": [("校验后的引用", "inline")]},
        }

    @classmethod
    def get_pipeline(cls, user_settings, state, retrievers=None):
        return cls(retrievers=[r for r in (retrievers or []) if isinstance(r, ScholarRetrieverPipeline)])

    def stream(self, message, conv_id, history, **kwargs):
        selected = [r for r in self.retrievers if r.selected]
        paper_id, retriever, selection_error = None, None, None
        if len(selected) == 1 and len(selected[0].selected) == 1:
            retriever = selected[0]
            try:
                _, note = retriever.backend().source_for(file_id=retriever.selected[0])
                paper_id = note["paper_id"]
            except Exception as error:
                selection_error = error
        result = answer(message, paper_id, method=retriever.method if retriever else None,
                        retriever=retriever.retrieve if retriever else None, selection_error=selection_error)
        yield Document(channel="info", content=None)
        yield Document(channel="info", content=evidence_html(result))
        if result["status"] == "error":
            content = "请求失败（不是拒答）：" + html.escape(json.dumps(result["error"], ensure_ascii=False))
        elif result["status"] == "insufficient_evidence":
            content = "当前论文未提供充分证据。"
        else:
            content = html.escape(result["answer"])
            if result["status"] == "ok":
                for citation in result["citations"]:
                    number = citation["number"]
                    content = content.replace(f"【{number}】", f'<a href="#evidence-{number}">【{number}】</a>')
            else:
                content += "\n\n⚠️ 引用或输出格式校验未通过，请核对原文；不能视为可信回答。"
        yield Document(channel="chat", content="<pre style='white-space:pre-wrap'>" + content + "</pre>")
        return Document(text=result["answer"], metadata=result)
