"""PDF 抽取：文字型 PDF 走 pypdf 搬运字符；扫描型（无文字层）走 RapidOCR；不静默兜底。"""
import os


class PDFExtractionError(Exception):
    """PDF 无法抽取（依赖缺失 / 无文字层且无嵌入图片）。"""


def extract_pdf_text(path: str):
    """返回 (text, used_ocr)。文字型直接抽取；抽不出文字则按扫描件对嵌入图片做 OCR。"""
    try:
        from pypdf import PdfReader
    except ImportError as e:
        raise PDFExtractionError(
            f"pypdf 未安装（{e}）；请先 python -m pip install -r requirements.txt")

    reader = PdfReader(path)
    pages = [(p.extract_text() or "") for p in reader.pages]
    text = "\n\n".join(pages).strip()
    if text:
        return text, False

    # 无文字层 → 判定为扫描件：把每页嵌入的位图交给 OCR（显式依赖，失败即报错）
    name = os.path.basename(path)
    try:
        from rapidocr_onnxruntime import RapidOCR
        import numpy as np
    except ImportError as e:
        raise PDFExtractionError(
            f"{name} 无文字层（判定为扫描件），需要 OCR 支持："
            f"python -m pip install rapidocr-onnxruntime（{e}）")

    ocr = RapidOCR()
    out = []
    for i, page in enumerate(reader.pages, 1):
        page_imgs = _page_images(page, name)
        if not page_imgs:
            raise PDFExtractionError(
                f"{name} 第 {i} 页既无文字层也无嵌入图片，无法抽取；"
                "请先用外部 OCR 工具处理，或换成文字型 PDF")
        for img in page_imgs:
            result, _ = ocr(np.array(img.convert("RGB")))
            if result:
                out.append("\n".join(line[1] for line in result))
    return "\n\n".join(x for x in out if x.strip()), True


def _page_images(page, name: str):
    try:
        return [im.image for im in page.images]
    except Exception as e:
        raise PDFExtractionError(f"{name} 读取页面嵌入图片失败：{e}")
