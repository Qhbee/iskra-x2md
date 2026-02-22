"""
探测 PDF 某一页的 block 结构：有哪些块、类型、bbox、行数、内容预览
用法：修改 TARGET_PAGES，运行查看 PyMuPDF 如何划分 block
"""
import fitz
from pathlib import Path

# ================= 配置 =================
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
INPUT_PDF = PROJECT_ROOT / "data/raw/lenin/列宁全集（版本II-文字版）（完整书签版）/列宁全集 第1卷（1893年—1894年）.pdf"

# 要探测的页码（1-based）
TARGET_PAGES = [312]

# 是否展开每个 block 的 lines（类似 probe_lines_bbox）
EXPAND_LINES = False

# =======================================


def block_text_preview(block, max_len=50):
    """提取 block 的文本预览"""
    if "image" in block:
        return "[图片]"
    text = ""
    for line in block.get("lines", []):
        for span in line.get("spans", []):
            text += span.get("text", "")
    text = text.strip().replace("\n", " ")
    return (text[:max_len] + "…") if len(text) > max_len else text


def probe():
    if not INPUT_PDF.exists():
        print(f"❌ 找不到: {INPUT_PDF}")
        return

    doc = fitz.open(INPUT_PDF)

    for page_num in TARGET_PAGES:
        if page_num < 1 or page_num > doc.page_count:
            print(f"⚠️ 页码 {page_num} 超出范围 (1-{doc.page_count})")
            continue

        page = doc[page_num - 1]
        data = page.get_text("dict", clip=page.rect)
        blocks = data.get("blocks", [])

        print("=" * 90)
        print(f"  📃 第 {page_num} 页 · 共 {len(blocks)} 个 block")
        print("=" * 90)

        for b_idx, block in enumerate(blocks):
            bbox = block.get("bbox", (0, 0, 0, 0))
            x0, y0, x1, y1 = bbox
            block_type = "image" if "image" in block else "text"
            line_count = len(block.get("lines", [])) if block_type == "text" else 0
            preview = block_text_preview(block)

            print(f"\n  Block {b_idx} | type={block_type:5} | bbox x0={x0:.1f} y0={y0:.1f} x1={x1:.1f} y1={y1:.1f} | lines={line_count}")
            print(f"           | {preview}")

            if EXPAND_LINES and block_type == "text":
                for l_idx, line in enumerate(block.get("lines", [])):
                    lb = line.get("bbox", (0, 0, 0, 0))
                    lt = "".join(s.get("text", "") for s in line.get("spans", [])).strip()
                    lt = (lt[:60] + "…") if len(lt) > 60 else lt
                    print(f"           |   Line {l_idx}: x0={lb[0]:.1f} y0={lb[1]:.1f} | {lt}")

        print("\n")

    doc.close()
    print("✅ 完成")


if __name__ == "__main__":
    probe()
