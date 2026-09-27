"""Markdown 抽取：逐行状态机产出 Block，不引第三方库。

与 txt 的本质区别：空行只是段落分隔符，不再充当切块边界——切块由切块器按标题层级决定。
"""
import re

import blocks

HEAD_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
TABLE_ROW_RE = re.compile(r"^\s*\|(.+)\|\s*$")
SEP_CELL_RE = re.compile(r"[-: ]+")
FENCE = "```"


def _split_row(inner: str) -> list:
    # 按未转义的 | 切列，\| 还原成字面竖线（GFM 转义）
    return [c.replace("\\|", "|").strip() for c in re.split(r"(?<!\\)\|", inner)]


def extract_md_blocks(path: str) -> list:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.read().splitlines()

    out = []
    para, table_rows, code = [], [], None

    def flush_para():
        if para:
            blk = blocks.paragraph("\n".join(para))
            if blk:
                out.append(blk)
            para.clear()

    def flush_table():
        if table_rows:
            blk = blocks.table_from_rows(table_rows[0], table_rows[1:])
            if blk:
                out.append(blk)
            table_rows.clear()

    def flush_all():
        flush_para()
        flush_table()

    for line in lines:
        stripped = line.strip()

        if code is not None:  # 围栏代码块：整块收成一个 paragraph
            if stripped.startswith(FENCE):
                blk = blocks.paragraph("\n".join(code).strip())
                if blk:
                    out.append(blk)
                code = None
            else:
                code.append(line)
            continue

        if stripped.startswith(FENCE):
            flush_all()
            code = []
            continue

        m = HEAD_RE.match(line)
        if m:
            flush_all()
            blk = blocks.heading(m.group(2), len(m.group(1)))
            if blk:
                out.append(blk)
            continue

        tm = TABLE_ROW_RE.match(stripped)
        if tm:
            cells = _split_row(tm.group(1))
            # GFM 的 |---|---| 对齐行只跳过，不能去 flush：它是表格的一部分，
            # 一旦 flush 就会把上面刚收到的表头行当成空表格丢掉，整张表列名错位
            # （空单元格按分隔行处理：|  |  | 这类行在表格里没有信息量）
            if cells and all((not c) or SEP_CELL_RE.fullmatch(c) for c in cells):
                continue
            flush_para()
            table_rows.append(cells)
            continue

        if not stripped:
            flush_all()
            continue

        flush_table()
        para.append(stripped)

    flush_all()
    if code:  # 未闭合围栏：把已收集内容照常入库，不静默丢
        blk = blocks.paragraph("\n".join(code).strip())
        if blk:
            out.append(blk)
    return out
