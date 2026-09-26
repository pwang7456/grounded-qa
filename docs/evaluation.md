# 评测方法与指标定义

一键评测：`python eval.py`（无需先启动服务，直接进程内跑全流水线；评测自动关闭缓存，保证可复现）。
评测集：`eval/questions.jsonl`，20 个应答题（中英双语、覆盖 6 个知识文件含 PDF 与 OCR 页）+ 10 个应拒答题（越界 o01-o05 / 注入 i01-i04 / 低置信 l01）。

## 1. 检索指标（三配置对比：vector / hybrid / hybrid+rerank）

- **Context Precision@k**（RAGAS 排名加权定义）：`top_k=8, return_k=3`，题内 `CP = Σ_i [v_i·precision@i] / |relevant|`，其中第 i 位命中金标（`gold_contains` 关键句精确匹配）记 `v_i=1`。相关段排名越靠前得分越高，避免「固定 3 段中只允许 1 段相关」造成的天花板。**目标 ≥ 0.70**。
- **Recall / MRR / Top-1**：金标句覆盖率、首个相关段排名倒数、Top-1 即相关的题目占比。用于选择默认配置与解释「为什么 hybrid」。
- Embedding：`config.json` 的 `embedding.provider`（`ollama` = 本机 bge-m3 语义向量，零 token 费用，默认 / `zhipu` = 云端智谱 embedding-3 语义向量 / `hash` = 离线确定性袋词向量兜底）。更换 embedding 后必须重跑 `ingest.py`（collection 指纹校验防脏查）与评测：语义向量相比 hash 的三配置对比见 `reports/embedding_experiment.md`（`python scripts/embedding_experiment.py` 复现）与 `docs/issue_diagnosis.md` 问题四/问题五。

## 2. 生成指标（默认配置 hybrid+rerank 下测）

| 指标 | 定义 | 目标 |
|---|---|---|
| Faithfulness | 答案事实 token（剔除「根据公司制度：」「（来源：…）」「如需进一步确认请联系 HR」等系统模板短语后，汉字逐字 + 英文词）被 3 段检索资料覆盖的比例，0~1。拒答题不计。**目标 ≥ 0.85**。已知盲区（数字张冠李戴不扣分）由 Numeric Grounded 补足 | ≥ 0.85 |
| Numeric Grounded | 答案中所有数字（剔除模板短语后）必须出现在检索资料中（bool）。词面覆盖抓不住「15 天说成 25 天」——25 恰好在语料里时覆盖率不掉；制度问答数字错误最危险，单列硬校验。只打日志标记与纳入合规分，不触发拒答 | 记录口径，纳入 Compliance |
| Answer Compliance | 逐题 6 项规则得分均值：未误拒、faithfulness≥0.6、无未脱敏 PII（手机/身份证/邮箱正则）、长度 8~400 字、无 CoT 残留（Thinking/步骤N）、数字接地（numeric_grounded） | ≥ 0.90 |
| Style Consistency | 逐题 6 项风格特征与规范答案风格的符合率均值：简洁(≤200 字)、单段落、带来源（含「来源」字样）、以句号或来源标注收尾、语言与提问匹配、无思考过程 | ≥ 0.85 |
| Refusal Appropriateness | 应拒答集合上「实际拒答」的准确率 + 应答题未被误拒 | ≥ 0.90 |

> 说明：生成指标基于 `config.json` 当前激活预设的真实模型输出（无本地兜底改写）；同一评测集可切换 `llm.active` 横评不同模型，`eval.py` 无需改动。提示词对照组实验见 `reports/prompt_experiment.md`。
> **拒答阈值口径**：`refuse_threshold` 始终作用于 **rerank 前**的分数，rerank 只负责排序不参与判定——同一阈值在 rerank 开/关下量纲一致。**判据随 embedding 类型分流**：语义 embedding（`ollama`/`zhipu`）比较向量余弦（日志 `top_v_score`），因为 hybrid 融合分里的 BM25 项经 min-max 归一化后每题第一名恒为 1.0，只表达相对排名；`hash` 比较 rerank 前融合分（日志 `top_raw_score`）。阈值随 embedding 分布校准：语义 0.55（应答题余弦最低 0.600 / 应拒题最高 0.495，校准数据见问题五），hash 0.12。

## 3. 性能与成本

- 压测：`python scripts/load_test.py 60 8`（8 并发 ≥ 要求 5），统计 p50/p95、≤10s 完成率、缓存命中率 → `reports/load_test.csv`。当前实测：60/60 成功、p50 23ms / p95 4175ms、≤10s 完成率 1.0、RPS 7.65。
- 运维报表：`python scripts/ops_report.py [N]` 从 `logs/rag.jsonl` 聚合 p50/p95、token 用量（含每 1000 次调用估算）、缓存命中、拒答率、答案合规率。给 N 时只统计最后 N 条（当前代码/配置口径那段日志），默认全量。
- Token 成本口径：`token_usage.total_tokens` 均值 × 1000 = 每 1000 次调用 token 量。当前实测（`zhipu glm-5.3-flash` + 本机 bge-m3，`reports/ops_report.md` 取最后 96 条请求 / 73 次真实调用）：**588.7 token/次**（prompt 462.6 + completion 126.2），窗口内含 1/3 缓存命中折算 **44.8 万 token / 1000 次**（冷启动约 58.9 万）。历史对照（`deepseek-flash`，embedding 升级前 78 次调用）：528.2 token/次、14.0 万 token/1000 次 ≈ ¥0.22（牌价输入 ¥1/M、输出 ¥4/M，工作日高峰 2×）。切换模型只改 `config.json` 的 `llm.active`（内置 deepseek / zhipu 预设），重跑本报表即按新模型计价。模型选型理由见 README §7。

## 4. 诊断复现（before/after ≥10% 提升）

五个问题的复现步骤与数据见 `docs/issue_diagnosis.md`：拒答阈值误配（`scripts/threshold_experiment.py`）、提示词约束对生成质量的影响（`scripts/prompt_experiment.py`）、多轮改写稀释（HTTP 实测 + 日志回放）、embedding 换语义（`docs/issue_diagnosis.md` 问题四）、低置信门禁随 embedding 分流 + 本地 bge-m3（`scripts/embedding_experiment.py`），均基于 `logs/rag.jsonl` 与脚本实测复现。
