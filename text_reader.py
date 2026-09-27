"""纯文本类来源（txt / pdf 抽出的裸文本）→ Block。

这里保留的 _is_heading 是**无结构来源的专用兜底**：txt 和 pypdf 都不带样式信息，
只能靠行长和标点猜标题。docx / markdown 有真实结构，不走这条路径。
"""
import re

import blocks
import pdf_reader

HEADING_PUNCT_RE = re.compile(r"[。;；，,！？、：:]$")
CJK_RE = re.compile(r"[一-鿿]")
BRACKET_OR_DIGIT_RE = re.compile(r"[。;；，,！？、：:()（）\d]")
# 显式章节序号是结构信号，不是猜测：双语章节标题常常长过 _is_heading 的 40 字上限
SECTION_MARK_RE = re.compile(r"^第[一二三四五六七八九十百零〇\d]+[章节篇款项]\s")


def _is_section_mark(line: str) -> bool:
    return bool(SECTION_MARK_RE.match(line.strip())) \
        and not HEADING_PUNCT_RE.search(line)


def _is_heading(line: str) -> bool:
    line = line.strip()
    if not line or len(line) > 40:
        return False
    if HEADING_PUNCT_RE.search(line) or line.endswith("."):
        return False
    if re.search(r"[A-Za-z]{3,}", line):
        return True  # 中英混排标题（如"考勤制度 Attendance"）
    # 纯中文短行、无任何标点/数字：正文行几乎必然更长或含标点
    return len(line) <= 12 and not BRACKET_OR_DIGIT_RE.search(line) \
        and bool(CJK_RE.search(line))


def split_pdf_paragraphs(text: str) -> str:
    """pypdf 抽出的文字没有空行；按标题行切段，段内行合并。"""
    if re.search(r"\n\s*\n", text):
        return text
    parts = []
    cur = []
    for line in (ln.strip() for ln in text.splitlines()):
        if not line:
            continue
        if _is_heading(line) and cur:
            if len(cur) == 1:
                cur.append(line)  # 连续标题行合并，避免产生无正文的碎块
                continue
            parts.append(" ".join(cur))
            cur = [line]
        else:
            cur.append(line)
    if cur:
        parts.append(" ".join(cur))
    return "\n\n".join(parts)


def text_to_blocks(text: str) -> list:
    """空行分段；短而像标题的段落识别为 heading（level 由编号或长度粗判为 2）。"""
    out = []
    for para in re.split(r"\n\s*\n", text or ""):
        body = para.strip()
        if not body:
            continue
        if "\n" not in body and (_is_heading(body) or _is_section_mark(body)):
            out.append(blocks.heading(body, level=_guess_level(body)))
            continue
        out.append(blocks.paragraph(body))
    return out


def _guess_level(title: str) -> int:
    """无结构来源的层级猜测：带章节/第N条字样的当一级，其余当二级。"""
    if re.match(r"^(第[一二三四五六七八九十百\d]+[章节篇章])", title):
        return 1
    return 2


def extract_txt_blocks(path: str) -> list:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return text_to_blocks(f.read())


def extract_pdf_blocks(path: str):
    """返回 (blocks, used_ocr)。扫描件走 OCR 出来的行同样按无结构来源处理。"""
    text, used_ocr = pdf_reader.extract_pdf_text(path)
    return text_to_blocks(split_pdf_paragraphs(text)), used_ocr
