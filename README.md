# 研知 ScholarLens · Traceable RAG

面向 AI 论文阅读的个人科研文献助手：通过论文证据检索、本地模型问答与来源引用，帮助核对研究方法、实验设置和结论依据。

当前是开发中的个人原型，不是生产系统。正式检索与生成评测尚未完成，不承诺跨论文推理能力。

## 版本与进度

| 目录 | 内容 | 当前状态 |
|---|---|---|
| [v0](v0/README.md) | NumPy / BGE 检索与可追溯审计基础练习 | MockGenerator，不是真实 LLM 问答 |
| v1/ | 早期官方文档语料、规范化与标注练习 | 历史学习版本，不作为当前应用入口 |
| [v2](v2/README.scholar.md) | Kotaemon + QASPER + Ollama 的科研文献助手 | 当前开发主线 |

V2 已完成：

- T1：在 Apple M5 / 16GB 上跑通两篇论文的真实本地问答和原文引用，保存失败边界。
- T2：转换 1,584 篇可用 QASPER 论文、81,549 个段落，分离正文与问答标注并保留精确证据位置。
- 数据转换测试 27 项、V0 测试 11 项、V1 测试 10 项通过。

**数据转换不等于已经建库。** 网页目前仍使用 T1 的两篇 train 样例；全量索引、评测题集冻结与正式指标仍待完成。

## 从哪里开始

- [V2 启动与数据准备](v2/README.scholar.md)
- [T1 本机可行性报告](v2/reports/t1-feasibility.md)
- [T2 数据转换报告](v2/reports/t2-data.md)
- [上游来源与个人修改](v2/UPSTREAM.md)

V2 使用独立 Python 3.10 环境；本机已验证 Ollama 0.15.6、`qwen3:4b-instruct-2507-q4_K_M` 与 `nomic-embed-text`。
详细安装约束、依赖警告及烟测命令见 V2 说明，不将本机运行记录冒充跨平台安装保证。

## 数据、复现与许可证

论文与标注来自 [QASPER 官方数据集](https://huggingface.co/datasets/allenai/qasper)，获取地址和固定 SHA-256 在
[数据配置](v2/configs/local.json) 中。正文、答案/证据标签分开导出，后者不作为索引输入。
原始语料、转换全文、模型、环境、数据库、索引、密钥和本机运行日志不提交 Git；通过脚本在本地准备。

V2 复用固定版本的 [Kotaemon](https://github.com/Cinnamon/kotaemon)，保留其
[Apache-2.0 许可证](v2/LICENSE.txt)、上游文档与署名。QASPER 标注按数据卡的 CC BY 4.0 使用，保留论文原有权利。
本项目的贡献范围是场景适配、数据转换、证据位置与后续评测工程，不声称从零开发上游框架。
