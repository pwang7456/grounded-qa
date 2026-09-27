"""入库层统一中间结构契约：所有 reader 只产 List[Block]，切块器只认 Block。

Block = {"type": "heading"|"paragraph"|"table", "level": int, "text": str}
新增一种文件格式 = 新增一个 reader，切块器与下游零改动。
"""

HEADING = "heading"
PARAGRAPH = "paragraph"
TABLE = "table"
TYPES = (HEADING, PARAGRAPH, TABLE)


def make_block(btype: str, text: str, level: int = 0):
    """构造并校验一个 Block；正文为空返回 None，由调用方丢弃。"""
    if btype not in TYPES:
        raise ValueError(f"未知 block 类型: {btype!r}（可用: {', '.join(TYPES)}）")
    body = (text or "").strip()
    if not body:
        return None
    if btype == HEADING:
        lvl = max(1, min(6, int(level or 1)))
    else:
        lvl = 0
    return {"type": btype, "level": lvl, "text": body}


def heading(text: str, level: int = 1):
    return make_block(HEADING, text, level)


def paragraph(text: str):
    return make_block(PARAGRAPH, text)


def table(text: str):
    return make_block(TABLE, text)


def table_from_rows(header, rows):
    """表格 → 「表头:值 | 表头:值」的键值行。每行自带列名，检索时无需回看表头行。

    header 缺失或列数不符时用「列N」兜底，保证键永远存在。
    """
    header = [(h or "").strip() for h in (header or [])]
    lines = []
    for row in rows:
        pairs = []
        for i, val in enumerate(row):
            val = (val or "").strip()
            if not val:
                continue
            key = header[i] if i < len(header) and header[i] else f"列{i + 1}"
            pairs.append(f"{key}:{val}")
        if pairs:
            lines.append(" | ".join(pairs))
    return table("\n".join(lines))


def clean(blocks) -> list:
    """过滤 None，保持文档顺序。"""
    return [b for b in blocks if b]


def type_counts(blocks) -> dict:
    counts = {t: 0 for t in TYPES}
    for b in blocks:
        counts[b["type"]] += 1
    return counts
