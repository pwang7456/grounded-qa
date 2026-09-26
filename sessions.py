"""内存多轮会话 + 查询改写。带 TTL 淘汰与并发安全的快照读。"""
import re
import threading
import time
from collections import deque

_sessions = {}  # session_id -> {"turns": deque[(role, content)], "last_used": float}
_lock = threading.Lock()
_TTL_SECONDS = 2 * 3600   # 空闲会话 2 小时过期
_MAX_SESSIONS = 1000      # 超上限按 last_used 淘汰最旧的 10%

# 追问线索：指代/延续/省略式问句（含英文），命中才拼接上文
FOLLOWUP_RE = re.compile(
    r"呢[？?]?\s*$|^(那|那么|还有|另外|以及)|这个|这项|该制度|该政策|上述|上面|前文|它的?|"
    r"^and\b|\b(what about|how about|same for)\b",
    re.I,
)


def _evict_locked():
    """调用方需持锁。先清过期，仍超上限再按 last_used 淘汰。"""
    now = time.time()
    if len(_sessions) > _MAX_SESSIONS:
        for k, _ in sorted(_sessions.items(), key=lambda kv: kv[1]["last_used"])[
                : max(1, len(_sessions) // 10)]:
            _sessions.pop(k, None)
        return
    expired = [k for k, v in _sessions.items() if now - v["last_used"] > _TTL_SECONDS]
    for k in expired[:100]:
        _sessions.pop(k, None)


def _history(sid: str, max_turns: int):
    with _lock:
        _evict_locked()
        rec = _sessions.get(sid)
        if rec is None:
            rec = {"turns": deque(maxlen=max_turns * 2), "last_used": time.time()}
            _sessions[sid] = rec
        rec["last_used"] = time.time()
        return rec


def rewrite_query(sid: str, question: str, max_turns: int) -> str:
    """仅当问句像追问（含指代/延续线索）时拼接最近 2 条上文问句；
    独立新问题只用原句检索，避免被历史问句稀释（实测会丢金标段）。"""
    hist = _history(sid, max_turns)
    with _lock:
        prior_users = [c for r, c in hist["turns"] if r == "user"][-2:]
    if prior_users and FOLLOWUP_RE.search(question):
        return " ".join(prior_users + [question]).strip()
    return question


def append_turn(sid: str, question: str, answer: str, max_turns: int):
    hist = _history(sid, max_turns)
    with _lock:
        hist["turns"].append(("user", question))
        hist["turns"].append(("assistant", answer))


def get_messages(sid: str, max_turns: int):
    hist = _history(sid, max_turns)
    with _lock:
        return [{"role": r, "content": c} for r, c in hist["turns"]]
