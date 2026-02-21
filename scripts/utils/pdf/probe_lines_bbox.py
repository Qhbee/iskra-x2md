"""
探测 PDF 中 PyMuPDF 的 line 结构：bbox、spans、字体
用于理解「我们并不向世界说」等引用为何被拆成多行或误判为 ###。
用法：修改 SEARCH_TEXT 和 TARGET_PAGES，然后运行
"""
import fitz
from pathlib import Path

# ================= 配置 =================
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
INPUT_PDF = PROJECT_ROOT / "data/raw/lenin/列宁全集（版本II-文字版）（完整书签版）/列宁全集 第1卷（1893年—1894年）.pdf"

# 要探测的关键词（找到包含此词的页面并打印该页/该块的行结构）
SEARCH_TEXT = "我们并不向世界说"

# 可选：直接指定页码列表，留空则自动搜索
TARGET_PAGES = [312]  # 例如 [124, 125]

# 只打印包含关键词的 block，节省输出
ONLY_BLOCKS_WITH_TEXT = True

# =======================================


def has_heiti(span):
    font = span.get("font", "").lower()
    return "hei" in font or "bold" in font


def probe():
    if not INPUT_PDF.exists():
        print(f"❌ 找不到: {INPUT_PDF}")
        return

    doc = fitz.open(INPUT_PDF)

    # 确定要探测的页码
    if TARGET_PAGES:
        pages_to_check = [p - 1 for p in TARGET_PAGES if 1 <= p <= doc.page_count]
    else:
        pages_to_check = []
        for p in range(doc.page_count):
            if doc[p].search_for(SEARCH_TEXT):
                pages_to_check.append(p)
        if not pages_to_check:
            print(f"❌ 未找到包含「{SEARCH_TEXT}」的页面")
            return

    print(f"📖 {INPUT_PDF.name}")
    print(f"🔍 关键词: {SEARCH_TEXT}")
    print(f"📄 探测页码: {[p+1 for p in pages_to_check]}\n")

    for page_idx in pages_to_check:
        page = doc[page_idx]
        data = page.get_text("dict", clip=page.rect)

        print("=" * 100)
        print(f"  📃 第 {page_idx + 1} 页")
        print("=" * 100)

        for b_idx, block in enumerate(data.get("blocks", [])):
            if "lines" not in block:
                continue

            # 先检查该 block 是否包含关键词
            block_text = ""
            for line in block["lines"]:
                for span in line.get("spans", []):
                    block_text += span.get("text", "")
            if ONLY_BLOCKS_WITH_TEXT and SEARCH_TEXT not in block_text:
                continue

            print(f"\n  --- Block {b_idx} ---")

            for l_idx, line in enumerate(block["lines"]):
                bbox = line.get("bbox", (0, 0, 0, 0))
                x0, y0, x1, y1 = bbox

                line_text_parts = []
                line_heiti = False
                span_info = []

                for span in line.get("spans", []):
                    t = span.get("text", "")
                    line_text_parts.append(t)
                    if has_heiti(span):
                        line_heiti = True
                    span_info.append(f"{span['font'][:12]} {span['size']:.1f}pt")

                full_text = "".join(line_text_parts).strip()
                if not full_text:
                    continue

                # 判定：按 lenin_parser 的逻辑会得到什么 prefix
                CENTER_THRESHOLD = 150
                INDENT_2_THRESHOLD = 120
                INDENT_THRESHOLD = 105

                if line_heiti:
                    if x0 >= CENTER_THRESHOLD:
                        prefix_guess = "### "
                    elif x0 >= INDENT_2_THRESHOLD:
                        prefix_guess = "> "
                    elif x0 > INDENT_THRESHOLD:
                        prefix_guess = "> ?(续行)"
                    else:
                        prefix_guess = "body"
                else:
                    prefix_guess = "(非黑体)"

                print(f"    Line {l_idx:2d} | bbox x0={x0:6.1f} y0={y0:6.1f} x1={x1:6.1f} y1={y1:6.1f} | {prefix_guess}")
                print(f"           | {full_text[:70]}{'…' if len(full_text) > 70 else ''}")
                print(f"           | spans: {', '.join(span_info)}")
                print()

        print()

    doc.close()
    print("✅ 探测完成")


if __name__ == "__main__":
    probe()
