# 上游来源与项目改动

ScholarLens 复用 [Kotaemon](https://github.com/Cinnamon/kotaemon) 的应用框架，固定上游提交为 `9ad3e4e49aa35b8acddd235918a5d9753c1cfdf9`（2026-10-14 导入源码快照）。上游许可证保留在 [LICENSE.txt](LICENSE.txt)。未使用的 Docker/Fly、SSO 和文档构建文件没有纳入本仓库；本地启动入口为 `app.py` 和 `scripts/start_app.sh`。

## 复用与改动边界

- **复用：** Gradio 应用、文件集合、SQL 文件身份表、LanceDB/Chroma 存储，以及部分模型和问答引用组件。
- **论文数据：** `scholarlens/data.py`、`scholarlens/dataset.py` 处理 QASPER 正文与标注分离、段落位置、哈希校验和评测集冻结。
- **检索与问答：** `scholarlens/indexing.py`、`scholarlens/retrieval.py`、`scholarlens/qa.py` 等实现可定位的切分、论文范围内 BM25/Dense/RRF 排名、上下文预算、Ollama 调用和引用审计。部分本地配置和适配仍依赖上游组件。
- **评测：** `scholarlens/metrics.py`、`scholarlens/evaluate.py` 记录逐题指标、运行配置和离线复算。官方 QASPER evaluator 来自 [allenai/qasper-led-baseline](https://github.com/allenai/qasper-led-baseline) 提交 `e996b6c7b1b5f95d9308a74e3586416c6e780df1`，其来源、许可证和哈希保留在 `scholarlens/vendor/`。

## 验证边界

部分工程实现和报告由助手协作完成，不代表所有模块均由项目作者独立手写。30 道 Dev 题的语义检查由助手按委托完成，不是独立人工 gold 审查；标注风险见 [T3 审查记录](reports/t3-review.md)。冻结 Test 的配置、分母和结果见 [Test 报告](reports/test.md)。技术结果与排障记录保留在 [reports/](reports/)。
