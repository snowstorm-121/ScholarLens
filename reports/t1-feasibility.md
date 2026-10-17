# T1 本机可行性验收记录

日期：2026-10-14。用途：确认现成 Kotaemon 应用可以在本机完成真实论文问答；不是正式检索/生成性能评测。

## 通过的闭环

- Mac：Apple M5 / 16GB，macOS 26.5.1，arm64。
- Python：项目独立 `.venv`，3.10.22；原有学习环境未安装新依赖。
- Kotaemon：固定上游 commit `9ad3e4e49aa35b8acddd235918a5d9753c1cfdf9`，保留许可证与源代码快照。
- 已验证运行时：Ollama 0.15.6，原生 Metal；仅绑定 `127.0.0.1:11434`。
- 最终生成模型：`qwen3:4b-instruct-2507-q4_K_M`，digest `0edcdef34593eac1aa2be9c7d06c432dcf81945adca5eca2f27662c18f168ba0`。
- 向量模型：`nomic-embed-text`，完整 768 维；UI/脚本使用同一文件集合与索引。
- 数据：QASPER train 中按 paper_id 排序的两篇论文，分别为 `1601.00901` 和 `1601.01705`；索引共 28 个文档 chunk、28 条向量记录。
- 检索：vector-only，Top-5，禁用 reranker、MMR、LLM 相关性打分；所有召回 chunk 的 file_id 均属于所选论文。
- 生成请求实测参数：temperature=0、seed=42、num_ctx=8192、num_predict=512、think=false。
- 网页：`http://127.0.0.1:7860/`，无公开分享；应用中仅注册本地模型。

问题：Which release of the VQA dataset do the authors use?

真实答案：The authors use the VQA 1.0 release 【1】.

引用对应原文：We use the VQA 1.0 release

引用落在本次实际检索 chunk `ecf7ec48-c368-4704-8052-449922e0d471` 中。脚本断言检查：答案非空、版本事实存在、引用被解析、引用映射回 context、论文作用域正确、请求确实传入 think=false。网页也显示答案与原文高亮。

第一次成功的 QA 调用约 14.71 秒；断连后恢复并重复同一检查约 16.77 秒。包含 Python 导入/应用初始化的完整脚本运行分别约 21.87 和 26.59 秒。只有两次烟测，不是平均延迟或 SLA；CLI 检查进程峰值 RSS 约 674MB，不包含独立 Ollama 服务的模型内存。

## 必须保留的失败与限制

1. 官方默认 `qwen3:4b` 在当前测试中继续产生长推理，512 和 2048 输出上限下都没有完成引用协议中的最终答案。原生 API、稳定版运行时对照和模板变体均未解决，因此最终采用官方仅支持非思考模式的 Instruct-2507 权重，不能声称只修改一个 flag 就修复。
2. 原始问题 “What benchmark datasets they use?” 没有召回 GeoQA 的直接证据。它属于未通过的多证据诊断，不计作成功案例。
3. 两个图片数量表述出现过度拒答：context 包含 “more than 200,000 images”，模型却认为缺少精确数字或下界。这些记录保留，说明一次版本事实题成功不能证明问答质量全面可靠。
4. 上游复杂引用 prompt 在小模型下未稳定产生协议输出；本地默认改为较短的同协议 prompt，复用原引用解析与高亮组件。
5. 停止本次 Ollama 服务后，网页明确显示“错误”，后端为 `APIConnectionError` / `RetryError`，没有生成新答案或回退 Mock。上游会重试，并留下 Thinking 占位；具体友好错误信息及占位清理仍由 T5 实现。
6. `uv pip check` 返回 1：`grpcio-tools==1.62.3` 的 WHEEL 元数据标签为 x86_64。实际 extension 为 universal x86_64/arm64，原生 `protoc --version` 成功。此警告未隐藏、未通过改写安装元数据消除。
7. HTML reader、默认 token 切分和引用 Page 1 标签均来自上游；T1 没有实现可靠 PDF 页码、QASPER 字符 span、task prefixes、三路 Hybrid 或正式题集。

## 文件与复现

- 上游与个人改动：`UPSTREAM.md`。
- 启动与烟测：`README.scholar.md`、`scripts/start_ollama.sh`、`scripts/start_app.sh`、`scripts/t1_smoke.py`。
- 环境：`artifacts/t1/environment.json`、`artifacts/t1/requirements.lock.txt`、上游 `uv.lock`。
- 环境锁 SHA-256：`2011832c0c36c0864142e0a09bf3787d3519f95366b650be97808264cf4709c9`。
- 原始发布包 SHA-256：`a28fdf966db827bcee3d873107d6b6669864fb7ca8fbf73a192f5e39191bdb5a`。
- 成功调用及实际 prompt/context/响应：`artifacts/t1/smoke-before-disconnect.json`、`smoke.json`。
- 失败输出：同目录 `smoke-first-empty.json`、`smoke-2048-truncated.json`、`smoke-instruct-overrefusal.json`、`smoke-instruct-bound-refusal.json`、`smoke-short-prompt-refusal.json`。
- 页面证明：`ui-success.jpg`、`ui-disconnected.jpg`；断连后端日志保留在 `disconnect-backend.log`。
- 初次错误配置产生的 SQLite 文件保留为 `ktem_app_data/user_data/sql.db.failed-initialization`；本次生成的父仓库 `.theflow` 记录移至 `artifacts/t1/theflow-initial`，没有删除用户文件。

原始全文、模型、数据库和运行记录 Git-ignored；报告/代码可公开。旧模型和两个运行时都保留在本地。原有 v0/v1 及其他未提交内容未由本任务修改；未提交或推送 Git。

回归检查：原 V0 的 11 个 unittest 全部通过；新增脚本编译及两个启动脚本语法检查通过。依赖检查仍有上述一项警告，不能合称“所有检查均无问题”。

## 对计划的明确修正

当前固定生成型号更新为官方 Qwen3 4B Instruct-2507，运行时固定 0.15.6。后续 Dev/Test 在该实际配置上开始，不能将不同模型的成绩当作控制变量实验。T2–T9 仍待执行。

模型选择依据：[Qwen 官方模型卡](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507)、[Ollama 官方量化条目](https://ollama.com/library/qwen3:4b-instruct-2507-q4_K_M)。

## 同日迁移：改用 Ollama 桌面应用

根据用户要求，将运行方式由项目内 CLI 改为官方桌面应用，不改变模型或 RAG 配置。

- 安装位置：`/Applications/Ollama.app`；版本仍为 `0.15.6`。
- 官方安装包：`https://github.com/ollama/ollama/releases/download/v0.15.6/Ollama-darwin.zip`。
- 安装包 SHA-256：`d0944b02a2ee5cb67fa0fa5744aafa6bb58b494c9a87e3635cb10fd90cc526a5`；与官方发布元数据一致。
- 安装后的 `codesign --verify --deep --strict` 与 `spctl --assess --type execute` 均通过；未绕过 macOS 安全检查。
- 模型使用 APFS 克隆复制到 `/Users/yyy/.ollama/models`，原 `.tools/models` 保留为备份；无模型重新下载。
- 已停止原项目内服务，端口 `127.0.0.1:11434` 由桌面应用的 `Contents/Resources/ollama serve` 提供。
- 桌面界面已选中 `qwen3:4b-instruct-2507-q4_K_M`，API 模型列表中的 digest 与迁移前一致。
- 重新运行 `scripts/t1_smoke.py` 通过全部断言：召回 5 个 chunk，答案为 `The authors use the VQA 1.0 release 【1】.`，引用匹配实际 context；本次 QA 约 23.18 秒。
- RAG 网页返回 HTTP 200；`start_ollama.sh` 改为打开桌面应用，不再另起 CLI 服务；环境快照脚本改用应用内 CLI。
- `launchctl` 的 local-only / 单并行设置仅对当前登录会话有效。桌面应用可能提示更新，正式实验前需复核运行版本。

旧 CLI、旧模型和临时安装包暂未删除；未提交或推送 Git。

## 同日磁盘清理（用户确认后）

以下记录更新上文迁移时的备份状态：已删除项目内 `.tools/ollama`、
`.tools/ollama-stable`、`.tools/models`，以及 T1 的 Ollama/Kotaemon 临时安装包与
桌面版解压目录。使用桌面版 `ollama rm qwen3:4b` 删除未使用的原始模型；
`uv cache clean` 清理 2.8 GiB 安装缓存。删除不经过废纸篓，软件与模型可重新下载。

保留桌面应用、Qwen Instruct-2507、Nomic、独立 `.venv`、原文、索引、全部实验记录
以及 uv/Python 运行程序；未清理原有 Hugging Face 缓存或无关项目。

清理前后 `df -k` 可用空间分别为 351174188 KiB 和 355709620 KiB，
增加 4535432 KiB（约 4.33 GiB）。APFS 克隆共享数据块，因此不按目录显示大小相加估算。

清理后重新运行 `scripts/t1_smoke.py`，退出码为 0：召回 5 个 chunk，
答案仍为 `The authors use the VQA 1.0 release 【1】.`，引用与 context 检查通过，
QA 约 16.73 秒。按完成前验证要求检查后再交付；未提交或推送 Git。
