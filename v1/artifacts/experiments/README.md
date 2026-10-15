# 实验产物约定

每次实验创建独立目录，避免覆盖历史结果：

```text
YYYYMMDDTHHMMSS_<retriever>_cs<chunk_size>_ov<overlap>/
```

例如：`20260908T160500_hybrid_cs500_ov80/`。

每个实验目录固定包含：

- `experiment_config.json`：`experiment_id`、语料哈希、问题集哈希、模型、检索方法、`top_k`、随机种子、切分参数、代码版本和环境信息。
- `results.json`：`experiment_id`、指标、逐题排名和运行时间。

比较切分实验时，语料哈希、问题集哈希、模型、检索方法、`top_k`、随机种子、代码版本和环境必须相同；只允许 `chunk_size` 与 `overlap` 改变。
