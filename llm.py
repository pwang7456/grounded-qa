"""OpenAI 兼容 /chat/completions 客户端（DeepSeek / 智谱 GLM，由 config.json 预设切换）。

配置：config.json → `llm.active`（预设名）+ `llm.providers.<预设>.{base_url, model, api_key}`；
预设可带 `thinking`（如智谱 GLM 的 {"type": "disabled"} 关闭思考模式）与 `timeout_seconds`。
"""
import json
import re
import urllib.error
import urllib.request

from settings import load_config


class LLMUnavailable(Exception):
    """端点不可达 / 鉴权失败 / 超时等调用失败。"""

    def __init__(self, msg, usage=None):
        super().__init__(msg)
        self.usage = usage


class LLMUnusableOutput(LLMUnavailable):
    """调用成功但输出不可用（CoT 残留 / 回显问题 / 过短 / max_tokens 截断）。"""


PROMPT_VERSION = "v5"  # 提示词与生成配置版本；参与缓存 salt，变更自动失效旧缓存


def _llm_cfg() -> dict:
    cfg = load_config().get("llm") or {}
    return cfg if isinstance(cfg, dict) else {}


def active_name() -> str:
    return str(_llm_cfg().get("active") or "").strip().lower()


def active_preset() -> dict:
    presets = _llm_cfg().get("providers") or {}
    preset = presets.get(active_name()) if isinstance(presets, dict) else None
    return preset if isinstance(preset, dict) else {}


def model_name() -> str:
    return str(active_preset().get("model") or "")


def api_key() -> str:
    return str(active_preset().get("api_key") or "")


def has_api_key() -> bool:
    return bool(api_key())


def _base_url() -> str:
    base = str(active_preset().get("base_url") or "").strip()
    if not base.startswith(("http://", "https://")):
        base = "http://" + base
    return base.rstrip("/")


def cache_salt() -> str:
    return f"{active_name()}|{model_name()}|{PROMPT_VERSION}"


SYSTEM_PROMPT = (
    "你是公司内部制度问答助手。\n"
    "规则：\n"
    "1. 只能依据【资料】中的原文事实回答，禁止添加资料之外的任何信息"
    "（不要问候、安慰、建议、翻译标注、推测性补充）。\n"
    "2. 资料不足以回答时，只回复：资料不足，建议联系 HR。\n"
    "3. 输出一段纯文本，不要换行，不要 Markdown（禁止 **、#、列表符号），不超过 150 字。\n"
    "4. 直接复述资料中的关键事实与数字，尽量沿用资料原文措辞。\n"
    "5. 答案末尾附来源，格式：（来源：文件名）。\n"
    "6. 禁止输出思考过程、Thinking、分析步骤，直接给出最终答案。\n"
    "7. 回答语言必须与提问语言一致：英文提问必须用 English 作答，中文提问用中文——即使资料全是中文。"
)


def build_prompt(question: str, hits):
    docs = "\n".join(f"[{h['source']}] {h['text']}" for h in hits)
    user = (
        "根据下面【资料】回答员工问题，只使用【资料】原文中的信息。\n"
        "【资料】\n" + docs + "\n"
        "【问题】\n" + question
    )
    return user


def strip_thinking(raw: str) -> str:
    """剥掉 CoT 段，尽量抽出最终答案。"""
    if not raw:
        return ""
    text = raw.strip()
    m = re.search(r"(?:最终答案|Final Answer|结论|答案)[:：]\s*(.+)$", text, re.S)
    if m:
        return m.group(1).strip()
    lines = [
        ln for ln in text.splitlines()
        if not re.search(r"thinking|analysis|推理|分析过程|步骤\s*\d|Let'?s think", ln, re.I)
    ]
    return "\n".join(lines).strip()


def looks_like_bad_answer(text: str) -> bool:
    if not text or len(text) < 4:
        return True
    if re.search(r"thinking|过程[:：]|步骤\s*\d", text, re.I):
        return True
    if re.search(r"【?问题】?[?:：]?$", text) or "资料】" in text[-20:]:
        return True
    return False


def answer_indicates_insufficient(text: str) -> bool:
    """模型自述“资料不足”视为拒答（不计入合规答案，也不写缓存）。"""
    return bool(re.search(
        r"资料不足|信息不足|无法(?:回答|确定)|insufficient information|"
        r"not enough information|no (?:relevant )?information",
        text or "", re.I,
    ))


def _call_openai(prompt: str, history=None, timeout=None):
    cfg = _llm_cfg()
    preset = active_preset()
    if timeout is None:
        timeout = float(preset.get("timeout_seconds") or cfg.get("timeout_seconds") or 8)
    max_tokens = int(cfg.get("max_tokens") or 400)
    body = {
        "model": model_name(),
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}]
        + (history or [])
        + [{"role": "user", "content": prompt}],
        "temperature": float(cfg.get("temperature") or 0.2),
        "max_tokens": max_tokens,
        "stream": False,
    }
    reasoning_effort = preset.get("reasoning_effort")
    if reasoning_effort:
        body["reasoning_effort"] = str(reasoning_effort)  # 思考力度（智谱 glm-5.x 始终思考，low/high/max）
    headers = {"Content-Type": "application/json"}
    key = api_key()
    if key:
        headers["Authorization"] = "Bearer " + key
    req = urllib.request.Request(
        _base_url() + "/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", "replace")[:200]
        except Exception:
            pass
        raise LLMUnavailable(f"HTTP {e.code} from {_base_url()}: {detail}")
    except (urllib.error.URLError, OSError, json.JSONDecodeError, TimeoutError) as e:
        raise LLMUnavailable(f"LLM endpoint unreachable: {e}")
    choice = data["choices"][0]
    content = choice.get("message", {}).get("content") or ""
    usage = data.get("usage") or {}
    return content, {
        "prompt_tokens": int(usage.get("prompt_tokens", 0)),
        "completion_tokens": int(usage.get("completion_tokens", 0)),
        "total_tokens": int(usage.get("total_tokens", 0)),
    }, choice.get("finish_reason") or ""


def generate(question: str, hits, history=None):
    """返回 (answer_text, provider, usage)；最多尝试两次，两类失败都重试一次：
    瞬时调用失败（超时/网络/5xx）→ LLMUnavailable；输出不可用（CoT 残留/过短/截断）→ LLMUnusableOutput。"""
    name = active_name()
    if not api_key():
        raise LLMUnavailable(
            f"api_key 未配置：请在 config.local.json 的 llm.providers.{name} 填 api_key")
    prompt = build_prompt(question, hits)
    total = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    last_transient, last_raw = None, ""
    for _ in range(2):
        try:
            raw, usage, finish_reason = _call_openai(prompt, history=history)
        except LLMUnavailable as e:
            if e.usage:
                for k in total:
                    total[k] += e.usage.get(k, 0)
            last_transient, last_raw = e, ""
            continue
        for k in total:
            total[k] += usage.get(k, 0)
        clean = strip_thinking(raw)
        if finish_reason != "length" and not looks_like_bad_answer(clean):
            return clean, name, total
        last_transient, last_raw = None, raw  # max_tokens 截断或坏输出：重试一次
    if last_transient is not None:
        raise last_transient
    raise LLMUnusableOutput(
        f"模型输出不可用（CoT 残留/回显/过短/max_tokens 截断），原始输出片段：{last_raw.strip()[:150]!r}",
        total)
