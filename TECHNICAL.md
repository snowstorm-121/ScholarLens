# ScholarLens：实现与复核

项目入口、场景和正式成绩见[仓库首页](README.md)。这里记录实际数据流、运行入口和可核对边界。它是**选定论文范围内**的本地 RAG，不是跨论文综述系统。

## 系统如何工作

1. `scholarlens/data.py` 从固定 SHA-256 的 QASPER v0.3 发布包转换 1,584 篇可用论文。正文与问题/答案/证据标注分开；段落记录 `paper_id`、稳定 `paragraph_id` 和规范化字符半开区间。
2. `scholarlens/indexing.py` 在段落内切分，保持 chunk 到原段落的位置映射；`embedding.py` 用 `nomic-embed-text` 的文档/查询前缀生成 768 维向量。FileIndex 的身份表、LanceDB 原文和 Chroma 向量存储沿用上游框架。
3. `retrieval.py` 在用户选定论文内计算 BM25、Dense 或 `1/(60+rank)` RRF。Dense 从 Chroma 按论文/文件过滤读取已存向量后精确打分，**不是**全库 ANN 搜索。UI 与 CLI 使用同一注册适配层。
4. `context.py` 以真实 Qwen tokenizer 限制最多 5 个完整 chunk、4500 context tokens；`qa.py`、`generation.py` 请求本地 Ollama，保留实际 prompt/响应，检查引用是否来自该 context 并能定位原文。模型错误、拒答和无效引用分开记录。
5. `dataset.py`、`metrics.py`、`evaluate.py` 分别处理冻结题集、完整 gold span 覆盖及官方 QASPER F1 适配、不可覆盖的逐题评测记录。gold 不绑定某次切分生成的 chunk ID。

相关代码主要在 `scholarlens/`；网页入口为 `app.py`/`scholarlens/ui.py`。上游复用与个人改动边界见 [UPSTREAM.md](UPSTREAM.md)，许可证见 [LICENSE.txt](LICENSE.txt)。

## 本机运行

已验证环境为 Apple M5/16GB、Python 3.10.22、Ollama 0.15.6，模型 `nomic-embed-text` 与 `qwen3:4b-instruct-2507-q4_K_M`。本机已有完整语料和索引；新机器需要网络、磁盘空间，并重新获取校验数据、安装锁定依赖、建库。详细约束、依赖警告与历史排障见 [本地运行指南](LOCAL_SETUP.md)，以下不是跨平台一键安装保证。

在已经准备好 `.venv`、模型和索引的仓库根目录：

```sh
# 先打开 Ollama 桌面应用，然后在新终端进程使用正式选定配置
SCHOLAR_CONFIG="$PWD/configs/selected_config.json" bash scripts/start_app.sh
```

打开 `http://127.0.0.1:7860/`，选择 **ScholarLens QASPER 2400-200** 集合，并且只选一篇论文。普通 `bash scripts/start_app.sh` 沿用历史 `configs/local.json` 的 1600/Hybrid 配置，**不会**自动切到正式选定配置。不要同时开启两个占用 7860 端口的实例。

数据与索引重建入口（需要先安装依赖并允许获取官方发布包与模型）：

```sh
.venv/bin/python -m scholarlens.cli prepare --config configs/local.json
.venv/bin/python -m scholarlens.cli freeze --config configs/local.json
SCHOLAR_CONFIG="$PWD/configs/selected_config.json" .venv/bin/python -m scholarlens.cli index --config configs/selected_config.json
```

`prepare` 校验下载文件哈希；发现内容变化会停止，不会默默接受新版本。原始包和处理后的全文、评测题、模型、数据库、索引与逐题运行产物均被 Git 忽略。不要把 Test 题/答案导入检索索引。

## 实验设计与结果

- 检索 Dev/Test：200/300 题，其中可回答题 160/240；生成子集：50/100 题，其中可回答题 40/80。按预定规则仅用 Dev 选择 `2400/200 + Dense`，随后使用独立预注册 Test 契约进行一次正式评测。T7 冻结文件内历史 `ready_for_test=false` 保留，不把它改写成新状态。
- 两种切分（1600/200、2400/200）×三路方法的 Dev 对照见 [Dev 检索](reports/dev-retrieval.md)；Test 在同一 2400/200 索引上比较，BM25/Dense/Hybrid EvidenceRecall@5 分别为 0.4654/0.6290/0.5901。完整指标、生成 Answer F1 0.3347、9 次输出截断和分母见 [正式 Test](reports/test.md)。
- [三类失败案例](reports/t9-failures.md)分别展示检索未召回、正确证据排第 6 被 Top-5 context 排除，以及 Top-1 已有证据但生成拒答。不能把三者都归咎于模型，也不能看过 Test 后修改本版参数再沿用首次结果。

原始逐题 JSON 在本机忽略目录 `artifacts/evaluation/`；公开报告给出批次、哈希和汇总。`scripts/t8_verify.py` 在本机原始产物存在时离线复算四批 Test，不重新调用模型。30 道 Dev 问题的语义检查由助手按委托完成，**不是独立人类审核全部 gold**。结果只代表该小规模、单机、单论文范围条件，不代表线上服务质量。

## 验证与文档

```sh
.venv/bin/python -m pytest -q tests_scholarlens
.venv/bin/python scripts/t8_verify.py  # 需要本机保留的正式运行产物
```

当前本机项目回归测试为 **187 passed**，T8 离线复算通过。运行与问题处理记录见 [T1–T4](reports/t1-t4-interview-log.md)、[T5](reports/t5-interview-log.md)、[T6](reports/t6-interview-log.md)、[T7](reports/t7-interview-log.md)、[T8](reports/t8-interview-log.md) 和 [T9](reports/t9-interview-log.md)。[演示记录](reports/t9-demo.md)明确标明视频未完成，不能以文字记录代替视频。

数据来自 [QASPER](https://huggingface.co/datasets/allenai/qasper)；标注许可、论文权利、Kotaemon 上游版本和保留的版权信息见 [来源清单](UPSTREAM.md)。
