"""
查找 PDF 中指定字号的所有文本（按行/段落输出）
用于分析某字号在书中的分布和用途，辅助 FONT_MAP 配置。
"""
import fitz
from pathlib import Path

# ================= 配置 =================
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
INPUT_PDF = PROJECT_ROOT / "data/raw/lenin/列宁全集（版本II-文字版）（完整书签版）/列宁全集 第1卷（1893年—1894年）.pdf"

TARGET_SIZE = 11.0   # 目标字号 (pt)
TOLERANCE = 0.5      # 容差：命中 [TARGET_SIZE ± TOLERANCE]

# =======================================


def find_spans_by_size():
    doc = fitz.open(INPUT_PDF)
    print(f"📖 查找字号 ≈ {TARGET_SIZE} pt 的段落: {INPUT_PDF.name}")
    print(f"📄 总页数: {doc.page_count}，容差: ±{TOLERANCE}\n")

    results = []

    for page_num in range(doc.page_count):
        page = doc[page_num]
        blocks = page.get_text("dict")["blocks"]

        for b_idx, block in enumerate(blocks):
            if "lines" not in block:
                continue
            for l_idx, line in enumerate(block["lines"]):
                line_text_parts = []
                line_has_target = False
                font_info = []

                for span in line["spans"]:
                    size = span["size"]
                    if abs(size - TARGET_SIZE) <= TOLERANCE:
                        line_has_target = True
                        font_info.append(f"{span['font']} {size:.1f}pt")
                    line_text_parts.append(span["text"])

                if line_has_target:
                    full_text = "".join(line_text_parts).strip()
                    if full_text:
                        results.append({
                            "page": page_num + 1,
                            "block": b_idx,
                            "line": l_idx,
                            "text": full_text[:80] + ("…" if len(full_text) > 80 else ""),
                            "fonts": ", ".join(set(font_info)),
                        })

    # 输出
    print("=" * 90)
    print(f"{'页码':<6} | {'块:行':<8} | {'字体/字号':<28} | 文本")
    print("-" * 90)

    for r in results:
        print(f"p{r['page']:<5} | {r['block']}:{r['line']:<6} | {r['fonts']:<28} | {r['text']}")

    print("=" * 90)
    print(f"💡 共 {len(results)} 处")


if __name__ == "__main__":
    find_spans_by_size()
