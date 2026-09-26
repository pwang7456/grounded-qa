"""Prompt 注入、越界拒答、PII 脱敏。"""
import re

INJECTION_PATTERNS = [
    r"忽略(之前|以上|上面|所有|先前)[^。！？\n]{0,12}(指令|规则|提示|设定)",
    r"无视[^。！？\n]{0,12}(规则|指令|限制)",
    r"(泄露|透露|输出|打印|复述|回显)[^。！？\n]{0,12}(系统提示|提示词|system prompt|password|密码|密钥|token|秘钥)",
    r"(reveal|print|show|repeat|leak)\s+(the\s+)?(system\s+)?prompt",
    r"ignore\s+(all\s+|previous\s+|prior\s+|above\s+)?(instructions|rules|prompts)",
    r"disregard\s+(the\s+)?(system|previous|above)\s+(prompt|instructions|rules)",
    r"(扮演|假装|act\s+as|pretend\s+to\s+be)\s*(一个)?\s*(没有限制|不受限|DAN|jailbreak)",
    r"jailbreak|developer\s+mode|越狱模式",
    r"(输出|列出|给我).{0,8}(全部|所有).{0,8}(员工|用户).{0,8}(薪资|工资|密码|身份证|手机号)",
    r"system\s*prompt\s*[:：]?",
]

OUT_OF_SCOPE_PATTERNS = [
    r"股市|股票|大盘|k线",
    r"天气|气温|下雨|台风|预报",
    r"入侵|外挂|破解|黑客攻击|ddos",
    r"彩票|赌球|开奖",
    r"做饭|食谱|菜谱|旅游.*攻略|景点推荐",
    r"^(translate|翻译)[:：]",
    r"写(一首)?诗|讲(个)?笑话|闲聊|陪我说",
]

_REFUSAL_INJECTION = "抱歉，您的问题包含试图修改助手规则或索取敏感内容的指令，已被安全策略拦截。我只能基于公司知识库回答制度类问题，例如年假、病假、报销、合规等。"
_REFUSAL_SCOPE = "抱歉，这个问题超出了我的服务范围。我只能回答公司内部制度相关问题（如考勤假期、报销、合规、技术架构等），欢迎换个问题。"


def detect_injection(text: str) -> bool:
    low = text.lower()
    return any(re.search(p, low) for p in INJECTION_PATTERNS)


def is_out_of_scope(text: str) -> bool:
    return any(re.search(p, text) for p in OUT_OF_SCOPE_PATTERNS)


def redact_pii(text: str) -> str:
    # 顺序：身份证 → 手机号 → 邮箱 → 银行卡（长数字最后匹配避免误伤）
    text = re.sub(r"\b\d{17}[\dXx]\b", "[ID]", text)
    text = re.sub(r"\b1[3-9]\d{9}\b", "[PHONE]", text)
    text = re.sub(r"[\w.+-]+@[\w-]+\.[\w.]+", "[EMAIL]", text)
    text = re.sub(r"\b\d{13,19}\b", "[BANKCARD]", text)
    return text
