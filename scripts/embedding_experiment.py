"""实验：embedding 对检索质量与拒答阈能量纲的影响（词面 hash vs 语义模型）。

同一语料、同一评测集，只换 embedding 函数（`store.get_embedding_function`），对比：
1) 三档检索配置的 Context Precision / Recall / MRR / Top-1；
2) 低置信拒答门在两种量纲下的可分性（相关资料 vs 无关问题的分数区间）。

用法：python scripts/embedding_experiment.py
输出：reports/embedding_experiment.md（结束时会把索引恢复成 config.json 里配置的 embedding）
"""
import json
import os
import statistics
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

import eval as eval_mod  # noqa: E402
import ingest  # noqa: E402
import pipeline  # noqa: E402
import retrieve  # noqa: E402
import store  # noqa: E402

MODES = eval_mod.MODES
SEMANTIC_PROVIDERS = ("ollama", "zhipu")


def build_chunks():
    chunks = []
    for name in sorted(os.listdir(ingest.DATA_DIR)):
        path = os.path.join(ingest.DATA_DIR, name)
        if not os.path.isfile(path) or not name.lower().endswith((".txt", ".pdf", ".md")):
            continue
        text = ingest.read_file(path)
        if text.strip():
            chunks.extend(store.chunk_text(text, name, ocr=ingest.is_ocr(name)))
    return chunks


def use_provider(ecfg_override):
    """切换 embedding 实现并重建索引（monkeypatch 配置读取，不改 config.json）。"""
    store._embedding_cfg = lambda: dict(ecfg_override)
    store._ef = None
    store._ef_sig = None
    store.invalidate_cache()


def gate_stats(questions, cfg, provider):
    """低置信门的分数分布：pipeline 在 hash 下用融合分、语义 embedding 下用向量余弦。"""
    semantic = provider in SEMANTIC_PROVIDERS
    answered, refused = [], []
    for q in questions:
        hits = retrieve.search_chunks(
            q["q"], cfg["retrieval_mode"], int(cfg["top_k"]), int(cfg["return_k"]),
            bool(cfg["rerank_enabled"]))
        if not hits:
            score = 0.0
        elif semantic:
            score = max(h.get("v_score") or 0.0 for h in hits)
        else:
            score = max(h.get("raw_score", h["score"]) for h in hits)
        (answered if q["expect"] == "answer" else refused).append((score, q["id"]))
    lo = min(s for s, _ in answered) if answered else 0.0
    hi = max(s for s, _ in refused) if refused else 0.0
    # 可分阈值区间：(无关最高分, 相关最低分]，取中点为建议阈值
    band = (round(hi + 0.01, 3), round(lo - 0.01, 3)) if lo > hi else None
    return {
        "min_answer": round(lo, 3), "max_refuse": round(hi, 3),
        "separable": lo > hi, "band": band,
        "worst_answer": min(answered)[1] if answered else "",
        "best_refuse": max(refused)[1] if refused else "",
    }


def main():
    cfg = dict(pipeline.load_config())
    cfg["cache_enabled"] = False
    final_ecfg = dict(cfg.get("embedding") or {"provider": "hash"})
    questions = eval_mod.load_questions()
    chunks = build_chunks()

    variants = [{"provider": "hash", "label": "hash（词面 MD5 哈希袋，384 维）"}]
    if final_ecfg.get("provider") != "hash":
        variants.append(dict(final_ecfg, label=f"{final_ecfg['provider']}:{final_ecfg.get('model')}（语义）"))

    results = []
    for v in variants:
        use_provider(v)
        print(f"[embedding A/B] {v['label']} 重建索引 {store.rebuild_index(chunks)} chunks ...", flush=True)
        retrieval = {name: eval_mod.eval_retrieval(questions, mode, rr, cfg)
                     for name, mode, rr in MODES}
        gates = gate_stats(questions, cfg, v["provider"])
        results.append((v, retrieval, gates))
        print(f"  CP={retrieval[MODES[-1][0]]['context_precision']:.3f} "
              f"Top1={retrieval[MODES[-1][0]]['top1_accuracy']:.3f} "
              f"门限可分={gates['separable']} band={gates['band']}", flush=True)

    # 恢复成 config.json 配置的 embedding，并重建索引
    use_provider(final_ecfg)
    store.rebuild_index(chunks)

    lines = ["# Embedding 对照实验（hash vs 语义模型）", "",
             f"- 语料：{len(chunks)} chunks；评测集：{len(questions)} 题"
             f"（应答 {sum(1 for q in questions if q['expect']=='answer')} / 应拒 {sum(1 for q in questions if q['expect']=='refuse')}）",
             f"- 当前配置：`embedding.provider={final_ecfg.get('provider')}`，"
             f"模型 `{final_ecfg.get('model')}`，维度 `{final_ecfg.get('dimensions')}`",
             "- 复现：`python scripts/embedding_experiment.py`（结束自动恢复索引到当前配置）",
             "", "## 1. 检索质量（同一评测集，只换 embedding）", "",
             "| embedding | 配置 | ContextP@k | Recall | MRR | Top-1 |", "|---|---|---|---|---|---|"]
    for v, retrieval, _ in results:
        for name, _, _ in MODES:
            r = retrieval[name]
            lines.append(f"| {v['label']} | {name} | {r['context_precision']:.3f} | "
                         f"{r['recall']:.3f} | {r['mrr']:.3f} | {r['top1_accuracy']:.3f} |")

    lines += ["", "## 2. 低置信拒答门的量纲（为什么换 embedding 必须同时换判据）", "",
              "hash 时代门禁用 hybrid 融合分（BM25 经 min-max 归一化后每题第一名恒为 1.0，"
              "绝对值只在与向量分同样词面口径下才有可比性）；语义 embedding 的向量余弦"
              "跨问题可比，门禁改用 `v_score`。", "",
              "| embedding | 判据 | 相关资料最低分 | 无关问题最高分 | 可分阈值区间 |", "|---|---|---|---|---|"]
    for v, _, g in results:
        judge = "向量余弦 v_score" if v["provider"] in SEMANTIC_PROVIDERS else "hybrid 融合分 raw_score"
        band = f"{g['band'][0]} ~ {g['band'][1]}" if g["band"] else "重叠（不可分）"
        lines.append(f"| {v['label']} | {judge} | {g['min_answer']}（{g['worst_answer']}） | "
                     f"{g['max_refuse']}（{g['best_refuse']}） | {band} |")

    lines += ["", "## 3. 结论", ""]
    base_r, new_r = results[0][1], results[-1][1]
    for name, _, _ in MODES:
        d = new_r[name]["context_precision"] - base_r[name]["context_precision"]
        lines.append(f"- {name}：Context Precision {base_r[name]['context_precision']:.3f} → "
                     f"{new_r[name]['context_precision']:.3f}（{d:+.3f}）")
    g0, g1 = results[0][2], results[-1][2]
    lines += [f"- 门禁量纲：hash 融合分相关/无关区间 {g0['min_answer']} vs {g0['max_refuse']}，"
              f"语义余弦 {g1['min_answer']} vs {g1['max_refuse']}；"
              f"语义 embedding 下若仍沿用融合分门禁，无关问题最高分 {g1['max_refuse']} 会高于阈值，"
              f"低置信拒答退化为例行公事（详见 docs/issue_diagnosis.md 问题四）。"]

    out = os.path.join(BASE, "reports", "embedding_experiment.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
