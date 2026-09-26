"""扫描 data/ 入库：txt / pdf / ocr.txt → 分块 → embedding → Chroma。"""
import json
import os
import re
import sys

import pdf_reader
import store

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")


def _is_heading(line: str) -> bool:
    return (
        len(line) <= 40
        and re.search(r"[A-Za-z]{3,}", line)
        and not re.search(r"[。;；，,]$", line)
        and not line.rstrip().endswith(".")
    )


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


def read_file(path: str) -> str:
    if path.lower().endswith(".pdf"):
        return split_pdf_paragraphs(pdf_reader.extract_pdf_text(path))
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def is_ocr(filename: str) -> bool:
    return filename.endswith(".ocr.txt") or "scanned" in filename.lower()


def main():
    all_chunks = []
    per_file = {}
    for name in sorted(os.listdir(DATA_DIR)):
        path = os.path.join(DATA_DIR, name)
        if not os.path.isfile(path):
            continue
        if not name.lower().endswith((".txt", ".pdf", ".md")):
            continue
        text = read_file(path)
        if not text.strip():
            print(f"[skip] empty text: {name}", file=sys.stderr)
            continue
        chunks = store.chunk_text(text, name, ocr=is_ocr(name))
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
