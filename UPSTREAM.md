# 来源与复用范围

ScholarLens 基于 [Kotaemon](https://github.com/Cinnamon/kotaemon) 的源码快照二次开发，固定提交为 `9ad3e4e49aa35b8acddd235918a5d9753c1cfdf9`。上游许可证保留在 [LICENSE.txt](LICENSE.txt)。

| 来源 | 复用内容 | 本项目新增或适配 |
| --- | --- | --- |
| Kotaemon / Ktem | Gradio 应用、文件集合、SQL 文件身份表、LanceDB/Chroma 存储及部分问答组件 | QASPER 论文选择、论文范围检索、证据面板、本地模型适配 |
| QASPER | 论文正文、问题、参考答案和证据标注 | 正文与标注分离、原文位置映射、题集筛选和固定划分 |
| QASPER 官方 evaluator | 答案与证据 F1 评分代码 | 本地预测格式适配、异常预测处理、逐题记录与复算 |
| Ollama / Qwen3 / Nomic | 本地模型推理及向量生成 | 请求配置、上下文预算、引用约束与调用审计 |

新增数据、检索、问答与评测代码主要在 `scholarlens/`。官方 evaluator 固定为 [allenai/qasper-led-baseline](https://github.com/allenai/qasper-led-baseline) 的提交 `e996b6c7b1b5f95d9308a74e3586416c6e780df1`，原文件、来源与许可证保留在 `scholarlens/vendor/`。

项目开发与排障使用了 AI 辅助，不将复用组件或模型能力表述为从零自研。部分 Dev 标注语义检查也使用了辅助审查，不属于独立人工 gold 审核；具体方法与疑点见[审查记录](reports/t3-review.md)。

实验配置、统计口径和结果见[正式 Test 报告](reports/test.md)。历史报告保留原记录，不用后续文档修订替换当时的实验事实。
