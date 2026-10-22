# 本地运行

以下命令均在仓库根目录执行。参考环境为 Apple M5 / 16 GB、Python 3.10.22、Ollama 0.15.6；其他环境尚未逐一验证。

## 已有环境：启动应用

先打开 Ollama 应用，再运行：

```sh
SCHOLAR_CONFIG="$PWD/configs/selected_config.json" bash scripts/start_app.sh
```

访问 `http://127.0.0.1:7860/`，选择 **ScholarLens QASPER 2400-200** 集合，并选定一篇论文。Ollama 或应用已经运行时，复用现有服务，不要重复占用端口。

## 新环境：依赖与模型

```sh
git clone https://github.com/snowstorm-121/ScholarLens.git
cd ScholarLens
uv sync --python 3.10 --frozen --no-dev
```

需要预先安装 uv 和 Ollama。依赖安装可能联网下载解释器和包，仓库不包含虚拟环境、模型权重、论文原始数据或索引。

启动 Ollama 后检查服务与模型：

```sh
curl -sS http://127.0.0.1:11434/api/version
ollama list
```

缺少模型时，再单独下载：

```sh
ollama pull nomic-embed-text
ollama pull qwen3:4b-instruct-2507-q4_K_M
```

模型下载会占用网络、磁盘与内存；已有相同模型可复用。原始 `qwen3:4b` 与这里使用的非思考模型不是同一个配置，不能只改标签后沿用原实验结论。

## 数据准备与建库

```sh
.venv/bin/python -m scholarlens.cli prepare --config configs/local.json
.venv/bin/python -m scholarlens.cli freeze --config configs/local.json
.venv/bin/python -m scholarlens.cli validate --config configs/local.json
```

`prepare` 在本地缺少原始归档时下载公开 QASPER 数据并校验哈希；正文与问答标注分别导出。`freeze` 按固定规则生成题集，`validate` 核对冻结信息。输入或输出不匹配时应检查原因，不要删除冻结记录绕过验证。

使用最终选定配置建立索引：

```sh
SCHOLAR_CONFIG="$PWD/configs/selected_config.json" \
  .venv/bin/python -m scholarlens.cli index --config configs/selected_config.json
```

完整建库会调用本地 embedding 模型，耗时和磁盘占用取决于设备及已有缓存。向量库只导入论文正文，不导入评测问题、答案或 gold 证据。索引恢复依赖稳定 ID 与配置指纹，不会静默覆盖不同来源的产物。

## 查询与原文核对

```sh
SCHOLAR_CONFIG="$PWD/configs/selected_config.json" \
  .venv/bin/python -m scholarlens.cli retrieve \
  --config configs/selected_config.json --paper-id 1601.01705 \
  --query "Which release of the VQA dataset do the authors use?" --method dense --k 5
```

将 `retrieve` 替换为 `ask` 并去掉 `--k 5`，可进一步调用本地生成模型。应用和 CLI 必须使用相同的 `SCHOLAR_CONFIG` 与 `--config`，避免比较不同集合的结果。

网页中可搜索 `Compose Neural Networks` 并选择上述论文。查看引用对应的原文、实际上下文和回答，不把流畅回答当作正确性证明。

## 常见问题

| 现象 | 检查方向 |
| --- | --- |
| 无法连接模型 | 检查 Ollama 是否启动、11434 端口与完整模型标签；不要同时启动桌面服务和 `ollama serve` |
| 找不到集合或配置不一致 | 确认已建库，网页选中 2400-200 集合，启动环境变量与 CLI 参数一致 |
| 数据哈希或冻结校验失败 | 核对原始数据、配置和已生成文件；新实验另行版本化，不覆盖既有实验记录 |
| 回答截断或错误拒答 | 检查实际检索证据、context、响应及停止原因，参见[失败案例](../../reports/t9-failures.md) |
| 依赖检查出现 grpcio-tools 警告 | 参考环境中该 wheel 元数据标为 x86_64，但扩展为 universal 且原生检查成功；保留警告，不宣称依赖检查完全通过 |
| 导入时缺少 NLTK 资源 | 检查本地 NLTK 缓存及网络访问；不要用空资源文件掩盖缺失 |

## 验证边界

确定性回归入口：

```sh
.venv/bin/python -m pytest tests_scholarlens -q
```

安装、建库、查询和完整 Test 评测是不同步骤。重新运行 Test 需要匹配冻结配置、数据及执行契约，不是运行网页后就自动复现原成绩。已有结果见[正式报告](../../reports/test.md)，实现细节见[技术说明](TECHNICAL.md)。历史报告中的阶段编号仅用于追溯当时的配置与产物。
