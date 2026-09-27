"""扫描 data/ 入库：docx / md / txt / pdf(文字型与扫描型) → Block → 切块 → embedding → Chroma。

新增一种格式 = 往 READERS 里加一个翻译器；切块器与下游零改动。
"""
import json
import os
import sys

import blocks
import docx_reader
import md_reader
import store
import text_reader

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

# 每个 reader 统一返回 (List[Block], used_ocr)
READERS = {
    ".txt": lambda p: (text_reader.extract_txt_blocks(p), False),
    ".md": lambda p: (md_reader.extract_md_blocks(p), False),
    ".docx": lambda p: (docx_reader.extract_docx_blocks(p), False),
    ".pdf": text_reader.extract_pdf_blocks,
}

# 明确不支持的格式：给出原因，而不是和"未知扩展名"混成一条静默跳过
KNOWN_UNSUPPORTED = {
    ".doc": "旧版二进制 Word，python-docx 不支持，请先另存为 .docx",
    ".docm": "带宏的 Word，先另存为 .docx",
    ".pptx": "未接入 PowerPoint reader",
    ".xlsx": "未接入 Excel reader",
    ".png": "图片需先 OCR，未接入图片直入通道",
    ".jpg": "图片需先 OCR，未接入图片直入通道",
}


def build_chunks_from_data():
    """扫描 data/ 产出 (chunks, per_file, skipped, failed)。

    ingest 与 scripts/embedding_experiment.py 共用这一份读取逻辑，避免两套实现漂移。
    """
    all_chunks, per_file, failed, skipped = [], {}, {}, []
    for name in sorted(os.listdir(DATA_DIR)):
        path = os.path.join(DATA_DIR, name)
        if not os.path.isfile(path):
            continue
        ext = os.path.splitext(name)[1].lower()
        reader = READERS.get(ext)
        if reader is None:
            reason = KNOWN_UNSUPPORTED.get(ext, "未知扩展名，没有对应 reader")
            print(f"[skip] unsupported: {name}（{reason}）", file=sys.stderr)
            skipped.append(name)
            continue
        try:
            blks, used_ocr = reader(path)
        except Exception as e:  # 抽取失败必须显式可见，不能静默少一份资料
            print(f"[fail] {name}: {e}", file=sys.stderr)
            failed[name] = str(e)
            continue
        chunks = store.chunk_blocks(blks, name, ocr=used_ocr)
        if not chunks:
            print(f"[skip] no chunks: {name}（blocks={blocks.type_counts(blks)}）",
                  file=sys.stderr)
        per_file[name] = {
            "blocks": blocks.type_counts(blks),
            "chunks": len(chunks),
            "ocr": used_ocr,
        }
        all_chunks.extend(chunks)
    return all_chunks, per_file, skipped, failed


def main():
    all_chunks, per_file, skipped, failed = build_chunks_from_data()
    n = store.rebuild_index(all_chunks)
    report = {
        "indexed_chunks": n,
        "chunker_version": store.CHUNKER_VERSION,
        "per_file": per_file,
        "skipped_unsupported": skipped,
        "failed": failed,
        "collection": store.COLLECTION_NAME,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if failed:
        sys.exit(1)  # 有文件抽取失败：入库结果不完整，退出码要让调用方知道


if __name__ == "__main__":
    main()
