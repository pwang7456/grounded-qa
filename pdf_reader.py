"""文字 PDF 抽取：优先 pypdf，无包时解析简单文本算子 (Tj/TJ)。"""
import re


def extract_pdf_text(path: str) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        return _raw_parse(path)
    try:
        reader = PdfReader(path)
        pages = [(p.extract_text() or "") for p in reader.pages]
        text = "\n\n".join(pages).strip()
        if text:
            return text
    except Exception:
        pass
    return _raw_parse(path)


_TJ = re.compile(r"\[((?:[^\]\\]|\\.)*)\]\s*TJ", re.S)
_Tj = re.compile(r"\((?:[^()\\]|\\.)*\)\s*Tj", re.S)


def _unescape(s: str) -> str:
    s = re.sub(r"\\([()\\])", r"\1", s)
    return re.sub(r"\\[0-7]{1,3}", " ", s)


def _raw_parse(path: str) -> str:
    with open(path, "rb") as f:
        raw = f.read().decode("latin-1")
    out = []
    for m in _TJ.finditer(raw):
        parts = re.findall(r"\((?:[^()\\]|\\.)*\)", m.group(1))
        out.append(_unescape("".join(p[1:-1] for p in parts)))
    for m in _Tj.finditer(raw):
        inner = re.match(r"\((.*)\)\s*Tj", m.group(0), re.S)
        if inner:
            out.append(_unescape(inner.group(1)))
    return "\n".join(x for x in out if x.strip())
