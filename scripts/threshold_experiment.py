"""实验：refuse_threshold 误配（0.6）导致的误拒飙升复现。

用法：python scripts/threshold_experiment.py
输出：reports/threshold_experiment.md
"""
import json
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

import pipeline  # noqa: E402
import store  # noqa: E402


def refusal_stats(threshold):
    cfg = pipeline.load_config()
    cfg["refuse_threshold"] = threshold
    cfg["cache_enabled"] = False
    with open(os.path.join(BASE, "eval", "questions.jsonl"), encoding="utf-8") as f:
        qs = [json.loads(ln) for ln in f if ln.strip()]
    ans = [q for q in qs if q["expect"] == "answer"]
    wrongly_refused = 0
    for q in ans:
        r = pipeline.answer_question({"q": q["q"], "session_id": f"thr-{threshold}"}, cfg)
        if r["refused"]:
            wrongly_refused += 1
    return wrongly_refused, len(ans)


def main():
    cfg = pipeline.load_config()
    calib = float(cfg["refuse_threshold"])
    semantic = not store.embedding_signature().startswith("hash:")
    gate = "向量余弦 `top_v_score`" if semantic else "rerank 前融合分 `top_raw_score`"
    lines = ["# 实验：refuse_threshold 误配影响",
             "",
             f"阈值作用在 rerank **前**的分数；当前 embedding={store.embedding_signature()}，"
             f"判据为{gate}，校准值 {calib}"
             "（语义 embedding 下应答题余弦最低 0.600 / 应拒题最高 0.495，见 docs/issue_diagnosis.md 问题五；"
             "hash 时代量纲不同，校准值 0.12，不可直接对比）。",
             ""]
    for t in (0.9, calib):
        bad, n = refusal_stats(t)
        ok_rate = (n - bad) / n
        lines.append(f"- threshold={t}: 应答题误拒 {bad}/{n}，有效回答率 {ok_rate:.1%}")
        print(lines[-1], flush=True)
    with open(os.path.join(BASE, "reports", "threshold_experiment.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("wrote reports/threshold_experiment.md")


if __name__ == "__main__":
    main()
