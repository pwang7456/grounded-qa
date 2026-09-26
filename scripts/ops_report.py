"""运维报表：从 logs/rag.jsonl 聚合 p50/p95、token、缓存命中、拒答率、答案合规率。

用法：python scripts/ops_report.py [N]     # N=只统计最后 N 条请求（默认全量）
      python scripts/ops_report.py 96       # 提交口径：只取当前代码路径（云端生成 + bge-m3）那一段
输出：reports/ops_report.csv / reports/ops_report.md
"""
import csv
import json
import os
import statistics
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG = os.path.join(BASE, "logs", "rag.jsonl")
REPORTS = os.path.join(BASE, "reports")


def pct(xs, p):
    xs = sorted(xs)
    k = max(0, min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1)))))
    return xs[k]


def main():
    events = []
    with open(LOG, "r", encoding="utf-8") as f:
        for ln in f:
            try:
                events.append(json.loads(ln))
            except Exception:
                continue
    if not events:
        raise SystemExit("logs/rag.jsonl 为空，先跑 eval.py 或 load_test.py")
    total_logged = len(events)
    tail = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    if tail:
        events = events[-tail:]
    lats = [e["latency_ms"] for e in events]
    usages = [e.get("token_usage") or {} for e in events]
    tokens = [u.get("total_tokens", 0) for u in usages]
    llm_calls = [u for u in usages if u.get("total_tokens", 0) > 0]
    answered = [e for e in events if not e.get("refused")]
    rows = {
        "requests": len(events),
        "p50_latency_ms": pct(lats, 50),
        "p95_latency_ms": pct(lats, 95),
        "p99_latency_ms": pct(lats, 99),
        "within_10s_rate": round(sum(1 for x in lats if x <= 10000) / len(lats), 4),
        "llm_calls": len(llm_calls),
        "avg_tokens_per_llm_call": round(
            sum(u.get("total_tokens", 0) for u in llm_calls) / max(len(llm_calls), 1), 1),
        "avg_prompt_tokens": round(
            sum(u.get("prompt_tokens", 0) for u in llm_calls) / max(len(llm_calls), 1), 1),
        "avg_completion_tokens": round(
            sum(u.get("completion_tokens", 0) for u in llm_calls) / max(len(llm_calls), 1), 1),
        "tokens_per_1000_calls": sum(tokens) * 1000 // len(tokens),
        "cache_hit_rate": round(sum(bool(e.get("cache_hit")) for e in events) / len(events), 4),
        "refusal_rate": round(sum(1 for e in events if e.get("refused")) / len(events), 4),
        "avg_faithfulness_answered": round(statistics.mean(
            [e["faithfulness"] for e in answered if e.get("faithfulness") is not None] or [0]), 4),
        "numeric_grounded_rate": round(
            sum(1 for e in answered if e.get("numeric_grounded"))
            / max(sum(1 for e in answered if e.get("numeric_grounded") is not None), 1), 4),
        "answer_compliance_rate": round(sum(
            1 for e in answered if (e.get("faithfulness") or 0) >= 0.6) / max(len(answered), 1), 4),
    }
    os.makedirs(REPORTS, exist_ok=True)
    with open(os.path.join(REPORTS, "ops_report.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["metric", "value"])
        for k, v in rows.items():
            w.writerow([k, v])
    with open(os.path.join(REPORTS, "ops_report.md"), "w", encoding="utf-8") as f:
        f.write("# 运维报表 Ops Report\n\n")
        window = (f"来源：logs/rag.jsonl 最后 {rows['requests']} 条请求事件（全量 {total_logged} 条，"
                  "更早的记录属已删除的兜底/本地生成链路，不计入当前口径）"
                  if tail else f"来源：logs/rag.jsonl（{rows['requests']} 条请求事件）")
        f.write(window + "\n\n")
        f.write("| 指标 | 值 |\n|---|---|\n")
        for k, v in rows.items():
            f.write(f"| {k} | {v} |\n")
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    print("wrote reports/ops_report.csv, reports/ops_report.md")


if __name__ == "__main__":
    main()
