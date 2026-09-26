"""实验：提示词约束对生成质量的影响（宽松提示词 vs 约束提示词）。

同一评测集、同一模型，仅改 SYSTEM_PROMPT/build_prompt，对比 Faithfulness 与 Style Consistency。
用法：python scripts/prompt_experiment.py
输出：reports/prompt_experiment.md
"""
import os
import statistics
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

import eval as eval_mod  # noqa: E402
import llm  # noqa: E402
import pipeline  # noqa: E402

# 约束前的旧提示词（原始版本，作为对照）
PERMISSIVE_PROMPT = (
    "你是公司内部制度问答助手。只能依据用户提供的【资料】回答，禁止编造。"
    "资料不足以回答时，回复“资料不足”并建议联系 HR。"
    "用简洁友好的中文回答（可含关键英文条款），不超过 150 字。"
    "禁止输出思考过程、Thinking、分析步骤，直接给出最终答案。"
)
PERMISSIVE_USER = (
    "根据下面【资料】友好地回答员工问题。\n"
    "【资料】\n{docs}\n"
    "【问题】\n{question}"
)


def _permissive_build(question, hits):
    docs = "\n".join(f"[{h['source']}] {h['text']}" for h in hits)
    return PERMISSIVE_USER.format(docs=docs, question=question)


def run(name, system_prompt, build_fn):
    orig_prompt, orig_build = llm.SYSTEM_PROMPT, llm.build_prompt
    llm.SYSTEM_PROMPT, llm.build_prompt = system_prompt, build_fn
    cfg = dict(pipeline.load_config())
    cfg["cache_enabled"] = False  # 两组实验互不污染
    faiths, styles = [], []
    try:
        for q in eval_mod.load_questions():
            if q["expect"] != "answer":
                continue
            r = pipeline.answer_question(
                {"q": q["q"], "session_id": f"pexp-{name}-{q['id']}"}, cfg)
            a = r.get("answer", "")
            faiths.append(r.get("faithfulness") or 0.0)
            styles.append(statistics.mean(eval_mod.style_features(a, q).values()))
    finally:
        llm.SYSTEM_PROMPT, llm.build_prompt = orig_prompt, orig_build
    return {
        "faithfulness": round(statistics.mean(faiths), 4),
        "style": round(statistics.mean(styles), 4),
        "n": len(faiths),
    }


def main():
    constrained_prompt, constrained_build = llm.SYSTEM_PROMPT, llm.build_prompt
    before = run("permissive", PERMISSIVE_PROMPT, _permissive_build)
    after = run("constrained", constrained_prompt, constrained_build)
    rows = [
        ("Faithfulness", before["faithfulness"], after["faithfulness"]),
        ("Style Consistency", before["style"], after["style"]),
    ]
    lines = ["# 实验：提示词约束对生成质量的影响", "",
             f"- 模型：{llm.active_name()} / {llm.model_name()}；题量：{before['n']}（应答题）",
             "- 对照组：约束前旧提示词（宽松，无输出格式约束）",
             "- 实验组：当前 `llm.SYSTEM_PROMPT`（只依据原文事实 / 单段纯文本 / 末尾标来源）", "",
             "| 指标 | 宽松提示词 | 约束提示词 | 提升 |", "|---|---|---|---|"]
    for name, b, a in rows:
        gain = (a - b) / b * 100 if b else 0
        lines.append(f"| {name} | {b:.3f} | {a:.3f} | {gain:+.1f}% |")
    with open(os.path.join(BASE, "reports", "prompt_experiment.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    print("\nwrote reports/prompt_experiment.md")


if __name__ == "__main__":
    main()
