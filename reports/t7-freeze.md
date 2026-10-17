# T7 最终配置冻结

2026-10-16，按已完成的 Dev 对照和 U3 复核冻结下一次正式评测使用的配置。冻结文件为 `configs/selected_config.json`，SHA-256：`e20e8a29e2e22274f6bd04d955427fdb4f01588e67c02fa7f5343703cc15a6cd`。状态为 `frozen_pending_T8_authorization`，`ready_for_test=false`；Test 评分入口仍锁定，尚未运行 Test。

| 固定项 | 值 |
|---|---|
| 检索 | 2400 字符、200 overlap、Dense；Top-5 进入问答 context |
| 向量模型 | `nomic-embed-text`，digest `8688dbc0926c1dfdc1b8b7489034e1fedb06f6ac66472dd2d7f0ed6d7d23ba29` |
| 生成模型 | `qwen3:4b-instruct-2507-q4_K_M`，digest `0edcdef34593eac1aa2be9c7d06c432dcf81945adca5eca2f27662c18f168ba0` |
| 生成参数 | temperature 0、seed 42、num_ctx 8192、num_predict 512、think false |
| Context | 最多 5 个 chunk、4500 tokens；证据不足输出 `[INSUFFICIENT_EVIDENCE]` |
| Prompt | `scholar-qa-v1`，SHA-256 `2fb79247a825aa38a7c2296d0f7d2e2e3d914e792b36d4561d75f2e9710481f3` |
| 数据与索引 | 题集冻结哈希 `5c94800e12c0b5b0b37afd17e93e0b23ea9593bbd12c35e6499e2b2878ea0d44`；索引指纹 `7cdc7972495576359456cbdb0c93afbdc7b04f5fbaed33dce7f44dfabe388c8e` |

配置内 `selection.data_contract.code_sha256` 固定了评测、检索、生成等项目源码的哈希；正式 Test 前须再次核对配置、题集、模型和代码，不因 Test 结果修改参数。旧 `artifacts/t7/final-verification.json` 是路径改动前的历史快照，予以保留；当前验收另存 `artifacts/t7/frozen-verification.json`。

当前验收复算了六组检索 Dev 和一组 50 题生成 Dev 的全部原始记录、官方批量分数、原文 span、实际 context/prompt/请求参数。真实索引计数为 1600/200 的 1,584 篇、82,491 块，2400/200 的 1,584 篇、81,670 块；旧演示索引 2 篇、28 块保留。所选配置的 UI 默认检索与 CLI 在同一 train 问题上的排名一致。本机 Ollama 返回的两个模型 digest 均与配置一致。

验收进程临时跳过 LlamaIndex 导入时重复调用的 `nltk.download("punkt_tab")`：该依赖检查旧的 `tokenizers/punkt` 路径，但实际需要的 `punkt_tab/english` 和 stopwords 已在其本地缓存中。绕过只作用于这次验收进程；未下载资源、未更改依赖包。运行方式：

```sh
SCHOLAR_CONFIG="$PWD/configs/selected_config.json" .venv/bin/python -c 'import nltk, runpy; nltk.download = lambda *args, **kwargs: True; runpy.run_path("scripts/t7_verify.py", run_name="__main__")'
```

所选配置的 Dev 检索 EvidenceRecall@5 为 0.649321、AllEvidence@5 为 0.6、MRR@10 为 0.472617。50 题生成 Dev 的 Answer F1 为 0.251667，包含 9 次截断和 13/40 次可回答题拒答。冻结是按预定选择规则保存评测条件，不表示问答质量已达标，也不构成 Test 授权。

`scripts/t7_analyze.py --phase report` 是历史候选报告生成步骤；冻结后重跑会因不可覆盖校验而拒绝改变 `selected_config.json`。当前七组 Dev 原始记录的复算和核验入口是上面的 `t7_verify.py` 命令。
