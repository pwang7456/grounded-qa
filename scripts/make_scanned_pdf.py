"""生成扫描风格 PDF(图片型):探亲假制度渲染成纸面图像 → 噪点/歪斜/模糊 → 包成 PDF。

产物 data/scanned_leave.pdf 没有(也不该有)文字层,pypdf 抽不出字,
入库时由 pdf_reader 走 RapidOCR——替代此前用 .ocr.txt 模拟 OCR 结果的做法。
重生成:python scripts/make_scanned_pdf.py
"""
import os
import random

from PIL import Image, ImageDraw, ImageFilter, ImageFont

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "data", "scanned_leave.pdf")
FONT = "C:/Windows/Fonts/msyh.ttc"

# (文本, 是否标题)——标题独立成行,正文段落按页宽自动折行
PARAGRAPHS = [
    ("探亲假制度", True),
    ("员工与配偶、父母不住在同一地点，且公休假日不能回家团聚的，可享受探亲假。", False),
    ("探望配偶每年 20 天；未婚员工探望父母每年 20 天（或每两年 45 天）；已婚员工探望父母每四年 20 天。", False),
    ("路费按硬座/二等座标准凭票据实报销，每年一次。", False),
]


def _wrap(text, font, max_w):
    """按像素宽度折行(中文无空格,逐字累积)。"""
    lines, cur = [], ""
    for ch in text:
        if ch == " " and not cur:
            continue
        if font.getlength(cur + ch) > max_w and cur:
            lines.append(cur)
            cur = ch
        else:
            cur += ch
    if cur:
        lines.append(cur)
    return lines


def render_page():
    w, h = 1240, 1754  # A4 @ 150dpi
    img = Image.new("L", (w, h), 246)  # 纸面微灰
    d = ImageDraw.Draw(img)
    y = 140
    for text, is_title in PARAGRAPHS:
        size = 56 if is_title else 42
        font = ImageFont.truetype(FONT, size)
        for ln in _wrap(text, font, w - 240):
            d.text((120, y), ln, font=font, fill=35)
            y += int(size * 1.9)
        y += 30
    img = img.rotate(0.6, fillcolor=246, resample=Image.BICUBIC)  # 扫描歪斜
    img = img.filter(ImageFilter.GaussianBlur(0.6))
    px = img.load()
    rng = random.Random(7)
    for _ in range(80000):  # 扫描噪点(固定种子保证可复现)
        x, yy = rng.randrange(w), rng.randrange(h)
        px[x, yy] = max(0, min(255, px[x, yy] + rng.randint(-35, 20)))
    return img.convert("RGB")


def main():
    render_page().save(OUT, "PDF", resolution=150.0)
    print(f"wrote {OUT} ({os.path.getsize(OUT)} bytes)")


if __name__ == "__main__":
    main()
