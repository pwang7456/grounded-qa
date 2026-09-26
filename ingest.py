"""扫描 data/ 入库：txt / pdf(文字型与扫描型) → 分块 → embedding → Chroma。"""
import json
import os
import re
import sys

import pdf_reader
import store

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")


def _is_heading(line: str) -> bool:
    line = line.strip()
    if not line or len(line) > 40:
        return False
    if re.search(r"[。;；，,！？、：:]$", line) or line.endswith("."):
        return False
    if re.search(r"[A-Za-z]{3,}", line):
        return True  # 中英混排标题（如"考勤制度 Attendance"）
    # 纯中文短行、无任何标点/数字（如"报销政策"）：正文行几乎必然更长或含标点
    return len(line) <= 12 and not re.search(r"[。;；，,！？、：:()（）\d]", line) \
        and bool(re.search(r"[一-鿿]", line))


def split_pdf_paragraphs(text: str) -> str:
    """pypdf 抽出的文字没有空行；按标题行切段，段内行合并。"""
    if re.search(r"\n\s*\n", text):
        return text
    blocks = []
    cur = []
    for line in (ln.strip() for ln in text.splitlines()):
        if not line:
            continue
        if _is_heading(line) and cur:
            if len(cur) == 1:
                cur.append(line)  # 连续标题行合并，避免产生无正文的碎块
                continue
            blocks.append(" ".join(cur))
            cur = [line]
        else:
            cur.append(line)
    if cur:
        blocks.append(" ".join(cur))
    return "\n\n".join(blocks)


def read_file(path: str):
    """返回 (text, ocr_used)。ocr 标记来自真实抽取路径，不做文件名猜测。"""
    if path.lower().endswith(".pdf"):
        text, used_ocr = pdf_reader.extract_pdf_text(path)
        return split_pdf_paragraphs(text), used_ocr
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read(), False


def main():
    all_chunks = []
    per_file = {}
    for name in sorted(os.listdir(DATA_DIR)):
        path = os.path.join(DATA_DIR, name)
        if not os.path.isfile(path):
            continue
        if not name.lower().endswith((".txt", ".pdf", ".md")):
            continue
        text, used_ocr = read_file(path)
        if not text.strip():
            print(f"[skip] empty text: {name}", file=sys.stderr)
            continue
        chunks = store.chunk_text(text, name, ocr=used_ocr)
        per_file[name] = len(chunks)
        all_chunks.extend(chunks)
    n = store.rebuild_index(all_chunks)
    print(json.dumps({
        "indexed_chunks": n,
        "per_file": per_file,
        "collection": store.COLLECTION_NAME,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
