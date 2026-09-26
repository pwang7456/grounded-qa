"""RAG 主编排：安全 → 缓存 → 检索 → 生成 → 脱敏 → 日志。"""
import json
import os
import re
import time
import uuid

import cache
import llm
import retrieve
import safety
import sessions
import store
from settings import load_config

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(BASE_DIR, "logs", "rag.jsonl")

REFUSAL_LOW_CONF = (
    "抱歉，知识库中没有找到与您的问题足够匹配的资料，无法可靠回答。"
    "建议换一种问法、补充制度名称，或联系 HR 服务台（内线 8000）咨询。"
)

REFUSAL_LLM_UNAVAILABLE = (
    "抱歉，模型服务暂时不可用，请稍后重试；如急需可联系 HR 服务台（内线 8000）。"
)
REFUSAL_LLM_UNUSABLE = (
    "抱歉，模型本次未能给出可靠答复，请换个问法再试；如急需可联系 HR 服务台（内线 8000）。"
)
REFUSAL_EMBEDDING_UNAVAILABLE = (
    "抱歉，检索服务暂时不可用，请稍后重试；如急需可联系 HR 服务台（内线 8000）。"
)

_NO_USAGE = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

# 系统/模型固定话术：非事实性内容，不参与忠实度分母
BOILERPLATE_RE = re.compile(
    r"根据公司制度[:：]?|（来源：[^）]*）|资料不足[，,]?\s*建议联系\s*HR[。.]?|"
    r"如需进一步确认[，,]?请联系\s*HR[。.]?"
)


NUM_RE = re.compile(r"\d+(?:\.\d+)?")


def _content_tokens(text: str):
    return set(re.findall(r"[一-鿿]|[A-Za-z0-9]+", text.lower()))


def faithfulness(answer: str, hits) -> float:
    """答案事实 token（去除模板短语后）被检索资料覆盖的比例（0~1）。"""
    if not answer or not hits:
        return 0.0
    fact_part = BOILERPLATE_RE.sub("", answer)
    a_toks = _content_tokens(fact_part)
    if not a_toks:
        return 1.0
    ctx = " ".join(h["text"] for h in hits)
    c_toks = _content_tokens(ctx)
    return round(len(a_toks & c_toks) / len(a_toks), 4)


def numeric_grounded(answer: str, hits) -> bool:
    """数字接地：答案中的数字（剔除模板短语后）必须全部出现在检索资料里。

    词面覆盖式忠实度抓不住「15 天说成 25 天」——只要 25 也在语料里覆盖率不掉；
    制度问答里数字幻觉最危险，这里单独硬校验（不通过只打标记，不拒答）。"""
    if not answer or not hits:
        return True
    nums = set(NUM_RE.findall(BOILERPLATE_RE.sub("", answer)))
    if not nums:
        return True
    ctx = set(NUM_RE.findall(" ".join(h["text"] for h in hits)))
    return nums <= ctx


def log_event(event: dict):
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def answer_question(payload: dict, cfg: dict = None) -> dict:
    t0 = time.time()
    cfg = cfg or load_config()
    question = (payload.get("q") or payload.get("question") or "").strip()
    sid = payload.get("session_id") or "anon"
    mode = payload.get("retrieval_mode") or cfg["retrieval_mode"]
    rerank = payload.get("rerank_enabled")
    if rerank is None:
        rerank = bool(cfg["rerank_enabled"])
    rerank = bool(rerank)

    request_id = uuid.uuid4().hex[:12]
    base = {
        "request_id": request_id,
        "session_id": sid,
        "question": safety.redact_pii(question),
        "retrieval_mode": mode,
        "rerank_enabled": rerank,
    }

    def finish(resp, provider, refused, cache_hit=False, hits=None,
               usage=None, faith=None, answer="", llm_error=None, num_grounded=None):
        resp.update({
            "answer": answer,
            "refused": refused,
            "hits": hits or [],
            "provider": provider,
            "cache_hit": cache_hit,
            "retrieval_mode": mode,
            "rerank_enabled": rerank,
            "token_usage": usage or _NO_USAGE,
            "faithfulness": faith,
            "numeric_grounded": num_grounded,
            "latency_ms": int((time.time() - t0) * 1000),
        })
        event = dict(base)
        hs = hits or []
        event.update({
            "provider": provider,
            "refused": refused,
            "cache_hit": cache_hit,
            "token_usage": resp["token_usage"],
            "latency_ms": resp["latency_ms"],
            "hit_ids": [h["id"] for h in hs],
            "top_score": round(max([h["score"] for h in hs] or [0]), 4),
            "top_raw_score": round(
                max([h.get("raw_score", h["score"]) for h in hs] or [0]), 4),
            "top_v_score": round(max([h.get("v_score") or 0.0 for h in hs] or [0]), 4),
            "faithfulness": faith,
            "numeric_grounded": num_grounded,
            "llm_error": llm_error,
            "answer": safety.redact_pii(answer),
            "ok": True,
        })
        log_event(event)
        return resp

    if not question:
        return finish({}, "empty", True, answer="请输入问题。")

    # 1) 安全
    if safety.detect_injection(question):
        return finish({}, "safety", True, answer=safety._REFUSAL_INJECTION)
    if safety.is_out_of_scope(question):
        return finish({}, "safety", True, answer=safety._REFUSAL_SCOPE)

    # 2) 缓存
    key = cache.make_key(question, mode, rerank, llm.cache_salt())
    if cfg["cache_enabled"]:
        entry = cache.get(key, cfg["cache_ttl_seconds"])
        if entry:
            cached_answer = entry.get("answer", "")
            if not llm.looks_like_bad_answer(cached_answer) and not entry.get("refused"):
                hits = entry.get("hits", [])
                return finish(
                    {"session_id": sid}, entry.get("provider", "cache"), False,
                    cache_hit=True, hits=hits, usage=entry.get("token_usage"),
                    faith=entry.get("faithfulness"), answer=cached_answer,
                    num_grounded=entry.get("numeric_grounded"),
                )
            # 坏缓存：丢弃并重新生成（写入侧不缓存拒答，此处兜底防脏数据）

    # 3) 多轮改写
    search_query = sessions.rewrite_query(sid, question, cfg["max_history_turns"])

    # 4) 检索
    try:
        hits = retrieve.search_chunks(
            search_query, mode, int(cfg["top_k"]), int(cfg["return_k"]), rerank
        )
    except store.EmbeddingUnavailable as e:
        return finish({"session_id": sid}, "embedding-unavailable", True,
                      answer=REFUSAL_EMBEDDING_UNAVAILABLE, llm_error=str(e)[:300])

    # 5) 低置信拒答。语义 embedding（ollama/zhipu）用向量余弦判定：它跨问题可比
    #    （相关资料 ≈0.6+，无关 ≈0.45）；hybrid 融合分里的 BM25 项经 min-max 归一化后
    #    每条问题第一名恒为 1.0，绝对值没有可比性，词面 embedding 时代才用融合分。
    if store.embedding_signature().startswith("hash:"):
        gate_score = max((h.get("raw_score", h["score"]) for h in hits), default=0.0)
    else:
        gate_score = max((h.get("v_score") or 0.0 for h in hits), default=0.0)
    if not hits or gate_score < float(cfg["refuse_threshold"]):
        return finish({"session_id": sid}, "low-confidence", True,
                      hits=hits, answer=REFUSAL_LOW_CONF)

    # 6) 生成（真实模型；输出不可用 / 端点异常按拒答处理，不做本地改写兜底）
    provider, usage, answer, faith = llm.active_name(), _NO_USAGE, "", None
    num_grounded = None
    llm_error, llm_refused = None, False
    try:
        answer, provider, usage = llm.generate(
            question, hits, history=sessions.get_messages(sid, cfg["max_history_turns"]))
        faith = faithfulness(answer, hits)
        num_grounded = numeric_grounded(answer, hits)
        if llm.answer_indicates_insufficient(answer):
            provider = provider + "+insufficient"
            llm_refused = True
        elif not num_grounded:
            provider = provider + "-num-ungrounded-flag"
        elif faith < 0.35:
            provider = provider + "-low-faithfulness-flag"
    except llm.LLMUnusableOutput as e:
        llm_error = str(e)[:300]
        usage = e.usage or _NO_USAGE
        answer = REFUSAL_LLM_UNUSABLE
        provider = llm.active_name() + "+unusable-output"
        llm_refused = True
    except llm.LLMUnavailable as e:
        llm_error = str(e)[:300]
        usage = e.usage or _NO_USAGE
        answer = REFUSAL_LLM_UNAVAILABLE
        provider = llm.active_name() + "+unavailable"
        llm_refused = True

    # 7) PII 脱敏
    answer = safety.redact_pii(answer)

    # 8) 写缓存 + 会话（拒答不写缓存，避免回放）
    if cfg["cache_enabled"] and not llm_refused:
        cache.put(key, {
            "answer": answer, "hits": _trim_hits(hits), "provider": provider,
            "token_usage": usage, "faithfulness": faith, "refused": False,
            "numeric_grounded": num_grounded,
        })
    sessions.append_turn(sid, question, answer, cfg["max_history_turns"])

    return finish({"session_id": sid}, provider, llm_refused, hits=_trim_hits(hits),
                  usage=usage, faith=faith, answer=answer, llm_error=llm_error,
                  num_grounded=num_grounded)


def _trim_hits(hits):
    return [{**h, "text": h["text"][:500]} for h in hits]
