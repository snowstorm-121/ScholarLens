# T9 本地演示记录

2026-10-16 在新启动的应用进程中，用 `configs/selected_config.json` 打开 `http://127.0.0.1:7860/`，完成了真实 UI 点击与模型调用：在 `ScholarLens QASPER 2400-200` 集合里按标题选择 `Learning to Compose Neural Networks for Question Answering · 1601.01705`，问 “Which release of the VQA dataset do the authors use?”；页面回答 “The authors use the VQA 1.0 release” 并显示引用。证据面板标识 `S425656c3ff93`，排名 1，原文段落 `1601.01705:s7:p1`，字符区间 `[22905,23544)`，来源 `arxiv.org/abs/1601.01705`，可看到 “We use the VQA 1.0 release”。当时审计面板显示 Dense、5 chunks、963 context tokens。

**视频状态：未完成。** 三次区域录屏试录实际抓到了非应用前台（一次为用户的其他 Chrome 页，后两次为 Codex），均立即删除、未发布，也不将其冒充演示视频。原因是录屏命令发出时前台窗口与浏览器自动化所控制的标签页不同；QuickTime 自动化没有取得稳定可验证的录制界面。为避免把无关页面录入交付物，停止试录。本文是操作记录，不是视频证据。

人工补录约 2 分钟时，先把 Chrome 的 ScholarLens 页面置于真正前台并只录该窗口，再按以下顺序操作，录后查看首尾画面：

1. 展示集合与标题筛选，只选上述一篇论文；说明此版不做跨论文检索。
2. 输入上述 VQA 问题，等待本地模型回答；打开引文，看段落 ID、来源和原句。
3. 用一条无答案问题演示 `[INSUFFICIENT_EVIDENCE]`，或打开 `t9-failures.md` 中保留的真实错误记录；不要为了视频伪造“正确拒答”。
4. 结束时展示配置与 `reports/test.md`，口头区分演示题与正式 Test 成绩。

如果补录或演示需要变更配置，应先确认没有把 Test 个例用作调参；演示不重新计算正式 Test。
