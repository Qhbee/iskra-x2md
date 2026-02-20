import fitz
from pathlib import Path


# ================= 配置 =================
# 自动定位路径
PROJECT_ROOT = Path(__file__).resolve().parent.parent
INPUT_PDF = PROJECT_ROOT / "data/raw/stalin/斯大林选集_1-4卷_诸夏怀斯社.pdf"
doc = fitz.open(INPUT_PDF)
page = doc[177 - 1]
blocks = page.get_text("dict")["blocks"]

for b in blocks:
    if "lines" in b:
        for l in b["lines"]:
            for s in l["spans"]:
                if "生产力在增长着，旧关系在破坏着。" in s["text"]: # 找马克思那句话
                    print(f"字体名: {s['font']}，字号: {s['size']}")
                    # 打印全部属性
                    # print(s)