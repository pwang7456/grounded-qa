# Embedding 对照实验（hash vs 语义模型）

- 语料：45 chunks；评测集：30 题（应答 20 / 应拒 10）
- 当前配置：`embedding.provider=ollama`，模型 `bge-m3`，维度 `1024`
- 复现：`python scripts/embedding_experiment.py`（结束自动恢复索引到当前配置）

## 1. 检索质量（同一评测集，只换 embedding）

| embedding | 配置 | ContextP@k | Recall | MRR | Top-1 |
|---|---|---|---|---|---|
| hash（词面 MD5 哈希袋，384 维） | vector-only | 0.842 | 0.900 | 0.850 | 0.800 |
| hash（词面 MD5 哈希袋，384 维） | hybrid | 0.967 | 1.000 | 0.975 | 0.950 |
| hash（词面 MD5 哈希袋，384 维） | hybrid+rerank | 0.975 | 1.000 | 0.975 | 0.950 |
| ollama:bge-m3（语义） | vector-only | 1.000 | 1.000 | 1.000 | 1.000 |
| ollama:bge-m3（语义） | hybrid | 1.000 | 1.000 | 1.000 | 1.000 |
| ollama:bge-m3（语义） | hybrid+rerank | 1.000 | 1.000 | 1.000 | 1.000 |

## 2. 低置信拒答门的量纲（为什么换 embedding 必须同时换判据）

hash 时代门禁用 hybrid 融合分（BM25 经 min-max 归一化后每题第一名恒为 1.0，绝对值只在与向量分同样词面口径下才有可比性）；语义 embedding 的向量余弦跨问题可比，门禁改用 `v_score`。

| embedding | 判据 | 相关资料最低分 | 无关问题最高分 | 可分阈值区间 |
|---|---|---|---|---|
| hash（词面 MD5 哈希袋，384 维） | hybrid 融合分 raw_score | 0.507（q05） | 0.558（i02） | 重叠（不可分） |
| ollama:bge-m3（语义） | 向量余弦 v_score | 0.6（q19） | 0.495（i03） | 0.505 ~ 0.59 |

## 3. 结论

- vector-only：Context Precision 0.842 → 1.000（+0.158）
- hybrid：Context Precision 0.967 → 1.000（+0.033）
- hybrid+rerank：Context Precision 0.975 → 1.000（+0.025）
- 门禁量纲：hash 融合分相关/无关区间 0.507 vs 0.558，语义余弦 0.6 vs 0.495；语义 embedding 下若仍沿用融合分门禁，无关问题最高分 0.495 会高于阈值，低置信拒答退化为例行公事（详见 docs/issue_diagnosis.md 问题四）。
