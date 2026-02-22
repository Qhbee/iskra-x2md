"""
探测 PDF 中「字下加点」相关的 span 结构：位置(bbox)、字体、逐 span 输出
目标：理解 ·****不·****仅·****超·****过·... 在 PyMuPDF 里的真实形态
- 每个 span 的 bbox、font、size、text
- 点 · 与汉字是否同一 span？点的 y 是否低于汉字（字下加点 vs 人名间隔号）
用法：修改 SEARCH_TEXT / TARGET_PAGES，运行
"""
import fitz
from pathlib import Path

# ================= 配置 =================
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
INPUT_PDF = PROJECT_ROOT / "data/raw/lenin/列宁全集（版本II-文字版）（完整书签版）/列宁全集 第1卷（1893年—1894年）.pdf"

# 要探测的关键词（字下加点例句）
SEARCH_TEXT = "不仅超过一餐饭"

# 可选：直接指定页码
TARGET_PAGES = [265]  # 留空则自动搜索

# 是否用 rawdict 输出字符级 bbox（用于看 · 与汉字的 y 差异）
USE_CHAR_LEVEL = True

# =======================================

DOT_CHARS = "\u00B7\u2022\u2024\u2219\u22C5"  # · • ․ ∙ ⋅


def has_dot(s):
    return any(c in s for c in DOT_CHARS) or "·" in s


def probe():
    if not INPUT_PDF.exists():
        print(f"❌ 找不到: {INPUT_PDF}")
        return

    doc = fitz.open(INPUT_PDF)

    if TARGET_PAGES:
        pages_to_check = [p - 1 for p in TARGET_PAGES if 1 <= p <= doc.page_count]
    else:
        pages_to_check = []
        for p in range(doc.page_count):
            if doc[p].search_for(SEARCH_TEXT):
                pages_to_check.append(p)
        if not pages_to_check:
            for p in range(min(100, doc.page_count)):
                if "·" in doc[p].get_text() or "这笔钱" in doc[p].get_text():
                    pages_to_check.append(p)
        if not pages_to_check:
            print(f"❌ 未找到包含「{SEARCH_TEXT}」或「·」的页面")
            doc.close()
            return

    print(f"📖 {INPUT_PDF.name}")
    print(f"🔍 关键词: {SEARCH_TEXT}")
    print(f"📄 页码: {[p+1 for p in pages_to_check]}\n")

    for page_idx in pages_to_check:
        page = doc[page_idx]
        fmt = "rawdict" if USE_CHAR_LEVEL else "dict"
        data = page.get_text(fmt, clip=page.rect)

        print("=" * 100)
        print(f"  📃 第 {page_idx + 1} 页 (format={fmt})")
        print("=" * 100)

        for b_idx, block in enumerate(data.get("blocks", [])):
            if "lines" not in block:
                continue
            block_text = ""
            for line in block["lines"]:
                for span in line.get("spans", []):
                    if "chars" in span:
                        block_text += "".join(c.get("c", "") for c in span["chars"])
                    else:
                        block_text += span.get("text", "")
            if SEARCH_TEXT not in block_text and not has_dot(block_text) and "这笔钱" not in block_text:
                continue

            print(f"\n  --- Block {b_idx} ---")
            print(f"      全文预览: {block_text[:120]}…" if len(block_text) > 120 else f"      全文预览: {block_text}")

            for l_idx, line in enumerate(block["lines"]):
                lb = line.get("bbox", (0, 0, 0, 0))
                print(f"\n    Line {l_idx} bbox={lb}")

                for s_idx, span in enumerate(line.get("spans", [])):
                    font = span.get("font", "")[:14]
                    size = span.get("size", 0)
                    flags = span.get("flags", 0)
                    bold = "bold" if (flags & 16) else ""
                    italic = "italic" if (flags & 2) else ""

                    if USE_CHAR_LEVEL and "chars" in span:
                        chars = span["chars"]
                        text = "".join(c.get("c", "") for c in chars)
                        print(f"      Span {s_idx}: font={font} size={size:.1f} {bold}{italic}")
                        # 逐字输出：字符、bbox、origin
                        for i, c in enumerate(chars):
                            ch = c.get("c", "?")
                            bbox = c.get("bbox", (0, 0, 0, 0))
                            orig = c.get("origin", (0, 0))
                            # 着重号点通常在字下方，y0 会更大
                            marker = " ← 点" if ch in DOT_CHARS or ch == "·" else ""
                            print(f"        [{i}] '{ch}' bbox=({bbox[0]:.1f},{bbox[1]:.1f},{bbox[2]:.1f},{bbox[3]:.1f}) origin=({orig[0]:.1f},{orig[1]:.1f}){marker}")
                    else:
                        text = span.get("text", "")
                        bbox = span.get("bbox", (0, 0, 0, 0))
                        origin = span.get("origin", (0, 0))
                        print(f"      Span {s_idx}: bbox=({bbox[0]:.1f},{bbox[1]:.1f},{bbox[2]:.1f},{bbox[3]:.1f}) font={font} size={size:.1f}")
                        print(f"             text={repr(text)}")

        print("\n")

    doc.close()
    print("✅ 完成")
    print("\n💡 若点的 bbox y0 明显大于同行汉字，可据 y 差判定 字下加点 vs 人名间隔号")


if __name__ == "__main__":
    probe()
