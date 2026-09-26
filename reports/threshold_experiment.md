# 实验：refuse_threshold 误配影响

阈值作用在 rerank **前**的分数；当前 embedding=ollama:bge-m3:1024，判据为向量余弦 `top_v_score`，校准值 0.55（语义 embedding 下应答题余弦最低 0.600 / 应拒题最高 0.495，见 docs/issue_diagnosis.md 问题五；hash 时代量纲不同，校准值 0.12，不可直接对比）。

- threshold=0.9: 应答题误拒 20/20，有效回答率 0.0%
- threshold=0.55: 应答题误拒 0/20，有效回答率 100.0%
