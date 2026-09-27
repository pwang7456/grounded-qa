"""纯向量 / 混合检索 / 轻量 rerank。BM25 倒排统计随语料缓存，不在每请求重算。"""
import collections
import math
import threading

import store

TOKEN_RE = store.TOKEN_RE

_idx_cache = None  # (key, doc_counters, doc_lens, avgdl, df)
_idx_lock = threading.Lock()


def _tokens(text: str):
    return TOKEN_RE.findall(text.lower())


def _index_key(chunks):
    return (
        len(chunks),
        chunks[0]["id"] if chunks else "",
        chunks[-1]["id"] if chunks else "",
    )


def _get_index(chunks):
    """倒排统计（token 计数 / 文档长度 / df / avgdl），key 变化才重建。"""
    global _idx_cache
    key = _index_key(chunks)
    with _idx_lock:
        if _idx_cache is not None and _idx_cache[0] == key:
            return _idx_cache
        counters = [collections.Counter(_tokens(c["text"])) for c in chunks]
        doc_lens = [sum(c.values()) for c in counters]
        avgdl = (sum(doc_lens) / len(doc_lens)) if doc_lens else 1.0
        df = {}
        for c in counters:
            for t in c:
                df[t] = df.get(t, 0) + 1
        _idx_cache = (key, counters, doc_lens, avgdl, df)
        return _idx_cache


def _minmax(scores):
    if not scores:
        return scores
    lo, hi = min(scores), max(scores)
    if hi - lo < 1e-9:
        return [1.0 if hi > 0 else 0.0 for _ in scores]
    return [(s - lo) / (hi - lo) for s in scores]


def bm25_scores(query: str, chunks, k1=1.5, b=0.75):
    """对全库 chunks 计算 BM25，返回与 chunks 对齐的分数列表。"""
    q_toks = _tokens(query)
    if not chunks or not q_toks:
        return [0.0] * len(chunks)
    _, counters, doc_lens, avgdl, df = _get_index(chunks)
    n = len(chunks)
    idf = {
        t: math.log(1 + (n - df.get(t, 0) + 0.5) / (df.get(t, 0) + 0.5))
        for t in set(q_toks)
    }
    scores = []
    for counter, dl in zip(counters, doc_lens):
        s = 0.0
        for t, idf_t in idf.items():
            tf = counter.get(t, 0)
            if tf:
                s += idf_t * tf * (k1 + 1) / (tf + k1 * (1 - b + b * dl / avgdl))
        scores.append(s)
    return scores


def rerank_score(query: str, text: str, base_score: float, body: str = None):
    """rerank = 0.55*score + 0.35*token_cover + 0.10*phrase_hit

    cover/phrase 只在正文上算：chunk 文本带有标题路径前缀，同章节的块共享大量
    标题词，词面覆盖会被系统性抬高，排序会偏向“标题像”而不是“正文像”。"""
    target = body or text
    q_set = set(_tokens(query))
    d_set = set(_tokens(target))
    cover = len(q_set & d_set) / len(q_set) if q_set else 0.0
    phrase = 1.0 if query.strip() and query.strip() in target else 0.0
    return 0.55 * base_score + 0.35 * cover + 0.10 * phrase


def _to_hit(cid, text, meta, score, v_score=None):
    return {
        "id": cid,
        "text": text,
        "source": meta.get("source", ""),
        "language": meta.get("language", ""),
        "ocr": bool(meta.get("ocr", False)),
        "heading_path": meta.get("heading_path", ""),
        "block_type": meta.get("block_type", "paragraph"),
        "prefix_len": int(meta.get("prefix_len", 0) or 0),
        "score": round(score, 4),
        "v_score": round(v_score, 4) if v_score is not None else None,
    }


def search_chunks(question: str, mode: str, top_k: int, return_k: int,
                  rerank_enabled: bool):
    """返回按分数降序的 hits（已截断到 return_k）。

    开 rerank 时每个 hit 附 `raw_score`（rerank 前分数）：拒答阈值用它判定，
    避免同一阈值在 rerank 开/关两种量纲下宽严不一。"""
    if mode == "vector":
        cand = store.query_vectors(question, top_k)
        hits = [_to_hit(cid, txt, meta, score, score) for cid, txt, meta, score in cand]
    else:  # hybrid
        vcand = store.query_vectors(question, top_k * 3)
        v_raw = {cid: score for cid, _, _, score in vcand}
        all_chunks = store.get_all_chunks()
        b_scores = _minmax(bm25_scores(question, all_chunks))
        fused = []
        for chunk, bs in zip(all_chunks, b_scores):
            vs = v_raw.get(chunk["id"], 0.0)
            score = 0.55 * vs + 0.45 * bs
            fused.append(_to_hit(chunk["id"], chunk["text"], chunk["metadata"], score, vs))
        fused.sort(key=lambda h: h["score"], reverse=True)
        hits = fused[:top_k]
    if rerank_enabled:
        for h in hits:
            h["raw_score"] = h["score"]
            body = h["text"][h.get("prefix_len", 0):]  # 剥掉标题路径前缀再算词面覆盖
            h["score"] = round(
                rerank_score(question, h["text"], h["score"], body=body), 4)
        hits.sort(key=lambda h: h["score"], reverse=True)
    return hits[:return_k]
