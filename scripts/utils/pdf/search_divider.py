import fitz  # PyMuPDF
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
INPUT_PDF = PROJECT_ROOT / "data/raw/lenin/列宁全集（版本II-文字版）（完整书签版）/列宁全集 第1卷（1893年—1894年）.pdf"
doc = fitz.open(INPUT_PDF)
page = doc[85- 1]

# ==================== rect 说明 ====================
# rect = 矩形框，(x0,y0) 左上角，(x1,y1) 右下角
# PDF 坐标系：y 向下增大，所以 y0=0 是页面顶部，y 越大越靠下
# width = x1-x0, height = y1-y0
# 横线：height 很小(接近0)，width 较大
# 竖线：width 很小，height 较大

# 1. 找矢量线
drawings = page.get_drawings()
print(f"矢量图数量: {len(drawings)}")
for i, item in enumerate(drawings):
    print(f"第 {i+1} 个矢量图: {item}")
    rect = item['rect']
    # 打印位于页面下方的宽线
    if rect.y0 > page.rect.height * 0.6 and rect.width > 50:
        print(f"找到疑似分割线: {rect}, y={rect.y0}")

# 2. 找字符线
blocks = page.get_text("blocks")
for b in blocks:
    text = b[4].strip()
    if "____" in text or "————" in text:
        print(f"找到疑似字符分割线: {text}, y={b[1]}")