import fitz  # PyMuPDF
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
INPUT_PDF = PROJECT_ROOT / "data/raw/stalin/斯大林选集_1-4卷_诸夏怀斯社.pdf"
doc = fitz.open(INPUT_PDF)
page = doc[192- 1]

# 1. 找矢量线
drawings = page.get_drawings()
print(f"矢量图数量: {len(drawings)}")
print(f"矢量图 {drawings.pop(0)}")
for item in drawings:
    rect = item['rect']
    # 打印位于页面下方的宽线
    if rect.y0 > page.rect.height * 0.6 and rect.width > 100:
        print(f"找到疑似分割线: {rect}, y={rect.y0}")

# 2. 找字符线
blocks = page.get_text("blocks")
for b in blocks:
    text = b[4].strip()
    if "____" in text or "————" in text:
        print(f"找到疑似字符分割线: {text}, y={b[1]}")