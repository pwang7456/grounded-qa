"""一键评测：三档检索对比 + 生成质量指标 → reports/。

用法：python eval.py
指标定义见 docs/evaluation.md。
"""
import csv
import json
import os
import re
import statistics
import time

import llm
import pipeline
import retrieve
import store

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
QUESTIONS = os.path.join(BASE_DIR, "eval", "questions.jsonl")
REPORTS = os.path.join(BASE_DIR, "reports")

MODES = [
    ("vector-only", "vector", False),
    ("hybrid", "hybrid", False),
    ("hybrid+rerank", "hybrid", True),
]

PII_RE = re.compile(r"\b1[3-9]\d{9}\b|\b\d{17}[\dXx]\b|[\w.+-]+@[\w-]+\.[\w.]+")
COT_RE = re.compile(r"thinking|分析过程|步骤\s*\d", re.I)


def load_questions():
    with open(QUESTIONS, "r", encoding="utf-8") as f:
        return [json.loads(ln) for ln in f if ln.strip()]


def is_relevant(hit, gold_contains):
    return any(g in hit["text"] for g in gold_contains)


def eval_retrieval(questions, mode, rerank, cfg):
    """RAGAS 风格 Context Precision：相关项出现在越靠前，precision@i 贡献越大。
    CP(q) = Σ_i [v_i * precision@i] / |relevant|，v_i=第 i 位是否相关。"""
    ans_qs = [q for q in questions if q["expect"] == "answer"]
    cps, recalls, mrrs, top1 = [], [], [], 0
    for q in ans_qs:
        hits = retrieve.search_chunks(
            q["q"], mode, int(cfg["top_k"]), int(cfg["return_k"]), rerank)
        rel = [is_relevant(h, q["gold_contains"]) for h in hits]
        if hits:
            n_rel = sum(rel)
            cp = 0.0
            seen = 0
            for i, r in enumerate(rel):
                if r:
                    seen += 1
                    cp += seen / (i + 1)
            cps.append(cp / n_rel if n_rel else 0.0)
            top1 += 1 if rel[0] else 0
        found = {g for h, r in zip(hits, rel) if r for g in q["gold_contains"] if g in h["text"]}
        recalls.append(len(found) / len(q["gold_contains"]))
        rr = 0.0
        for i, r in enumerate(rel):
            if r:
                rr = 1.0 / (i + 1)
                break
        mrrs.append(rr)
    n = max(len(ans_qs), 1)
    return {
        "context_precision": round(statistics.mean(cps), 4) if cps else 0,
        "recall": round(statistics.mean(recalls), 4) if recalls else 0,
        "mrr": round(statistics.mean(mrrs), 4) if mrrs else 0,
        "top1_accuracy": round(top1 / n, 4),
        "n": len(ans_qs),
    }


def style_features(answer, q):
    zh = q["lang"] == "zh"
    cjk = len(re.findall(r"[一-鿿]", answer))
    latin_words = len(re.findall(r"[A-Za-z]+", answer))
    return {
        "concise": len(answer) <= 200,
        "single_para": "\n" not in answer.strip(),
        "grounded": "来源" in answer,
        "clean_close": answer.rstrip().endswith(("。", ".", "）", ")")),
        "lang_match": (cjk * 2 >= latin_words) if zh else (latin_words >= 3 or cjk * 2 < latin_words),
        "no_cot": not COT_RE.search(answer),
    }


def eval_answers(questions, cfg):
    ans_qs = [q for q in questions if q["expect"] == "answer"]
    ref_qs = [q for q in questions if q["expect"] == "refuse"]
    faiths, compliances, styles = [], [], []
    refusal_ok, refusal_n = 0, 0
    latencies = []
    for q in ans_qs:
        resp = pipeline.answer_question(
            {"q": q["q"], "session_id": f"eval-{q['id']}"}, cfg)
        a = resp.get("answer", "")
        f = resp.get("faithfulness") or 0.0
        faiths.append(f)
        latencies.append(resp.get("latency_ms", 0))
        checks = [
            not resp["refused"],
            f >= 0.6,
            not PII_RE.search(a),
            8 <= len(a) <= 400,
            not COT_RE.search(a),
            resp.get("numeric_grounded", True),
        ]
        compliances.append(sum(checks) / len(checks))
        feats = style_features(a, q)
        styles.append(sum(feats.values()) / len(feats))
        q["_sample"] = {"answer": a, "faithfulness": f, "style": feats,
                        "num_grounded": resp.get("numeric_grounded")}
    for q in ref_qs:
        resp = pipeline.answer_question(
            {"q": q["q"], "session_id": f"eval-{q['id']}"}, cfg)
        refusal_n += 1
        if resp["refused"]:
            refusal_ok += 1
    return {
        "faithfulness": round(statistics.mean(faiths), 4) if faiths else 0,
        "answer_compliance": round(statistics.mean(compliances), 4) if compliances else 0,
        "style_consistency": round(statistics.mean(styles), 4) if styles else 0,
        "refusal_appropriateness": round(refusal_ok / refusal_n, 4) if refusal_n else 0,
        "avg_latency_ms": round(statistics.mean(latencies), 1) if latencies else 0,
        "n_answer": len(ans_qs),
        "n_refuse": refusal_n,
    }


def main():
    t0 = time.time()
    os.makedirs(REPORTS, exist_ok=True)
    if not store.index_ready():
        raise SystemExit("index not ready; run ingest.py first")
    questions = load_questions()
    cfg = pipeline.load_config()
    cfg = dict(cfg)
    cfg["cache_enabled"] = False  # 评测不污染线上缓存、结果可复现

    retrieval = {}
    for name, mode, rerank in MODES:
        retrieval[name] = eval_retrieval(questions, mode, rerank, cfg)
    answers = eval_answers(questions, cfg)

    targets = {
        "Faithfulness": (answers["faithfulness"], 0.85),
        "Context Precision (best mode)": (
            max(retrieval[m[0]]["context_precision"] for m in MODES), 0.70),
        "Answer Compliance": (answers["answer_compliance"], 0.90),
        "Refusal Appropriateness": (answers["refusal_appropriateness"], 0.90),
        "Style Consistency": (answers["style_consistency"], 0.85),
    }

    with open(os.path.join(REPORTS, "eval_metrics.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["section", "name", "metric", "value"])
        for name, r in retrieval.items():
            for k in ("context_precision", "recall", "mrr", "top1_accuracy"):
                w.writerow(["retrieval", name, k, r[k]])
        for k, v in answers.items():
            w.writerow(["answers", "default-mode", k, v])

    lines = ["# 评测报告 Evaluation Report", "",
             f"- 生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')}  用时 {time.time()-t0:.1f}s",
             f"- 题目：{len(questions)}（问答 {answers['n_answer']} / 应拒答 {answers['n_refuse']}）",
             f"- LLM provider：{llm.active_name()}  模型：{llm.model_name()}",
             f"- Embedding：{store.embedding_signature()}  refuse_threshold：{cfg['refuse_threshold']}",
             "", "## 1. 检索三配置对比（Context Precision / Recall / MRR / Top-1）", "",
             "| 配置 | ContextP@k | Recall | MRR | Top-1 命中 |", "|---|---|---|---|---|"]
    for name, _, _ in MODES:
        r = retrieval[name]
        lines.append(f"| {name} | {r['context_precision']:.3f} | {r['recall']:.3f} | {r['mrr']:.3f} | {r['top1_accuracy']:.3f} |")
    lines += ["", "## 2. 生成质量指标 vs 目标", "",
              "| 指标 | 实测 | 目标 | 达标 |", "|---|---|---|---|"]
    for k, (v, t) in targets.items():
        lines.append(f"| {k} | {v:.3f} | {t:.2f} | {'✅' if v >= t else '❌'} |")
    lines += ["", "## 3. 样例（前 5 题）", ""]
    for q in questions[:5]:
        s = q.get("_sample")
        if s:
            lines.append(f"- **{q['q']}** → {s['answer'][:100]}… (faith={s['faithfulness']})")
    with open(os.path.join(REPORTS, "eval_report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print("\n".join(lines))
    print("\nwrote reports/eval_report.md, reports/eval_metrics.csv")


if __name__ == "__main__":
    main()
