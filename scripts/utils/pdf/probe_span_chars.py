"""
探测 PDF 中某句的 span/chars 结构（rawdict 字符级），用于排查粗体/标点/字下加点等。
例：「这一部分依旧是社会的。」中，。与前面文字是否同一 span？
用法：
    python scripts/utils/pdf/probe_span_chars.py
可修改 SEARCH_TEXT / TARGET_PAGES 配置。
"""
import fitz
from pathlib import Path

# ================= 配置 =================
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
INPUT_PDF = PROJECT_ROOT / "data/raw/lenin/列宁全集（版本II-文字版）（完整书签版）/列宁全集 第1卷（1893年—1894年）.pdf"

# 要探测的句子或关键词
SEARCH_TEXT = "社会的"

# 可选：直接指定页码，留空则自动搜索
TARGET_PAGES = [160]  # 如 [138]

# =======================================


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
                break  # 只取第一个匹配页
        if not pages_to_check:
            print(f"❌ 未找到包含「{SEARCH_TEXT}」的页面")
            doc.close()
            return

    print(f"📖 {INPUT_PDF.name}")
    print(f"🔍 关键词: {SEARCH_TEXT}")
    print(f"📄 页码: {[p + 1 for p in pages_to_check]}\n")

    for page_idx in pages_to_check:
        page = doc[page_idx]
        data = page.get_text("rawdict", clip=page.rect)

        print("=" * 100)
        print(f"  📃 第 {page_idx + 1} 页 (rawdict, 字符级)")
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
            if SEARCH_TEXT not in block_text:
                continue

            print(f"\n  --- Block {b_idx} ---")
            # 找到包含关键词的片段，带上下文
            pos = block_text.find(SEARCH_TEXT)
            ctx_start = max(0, pos - 30)
            ctx_end = min(len(block_text), pos + len(SEARCH_TEXT) + 20)
            ctx = block_text[ctx_start:ctx_end]
            print(f"      上下文: …{ctx}…")

            for l_idx, line in enumerate(block["lines"]):
                line_text = ""
                for span in line.get("spans", []):
                    if "chars" in span:
                        line_text += "".join(c.get("c", "") for c in span["chars"])
                    else:
                        line_text += span.get("text", "")
                if SEARCH_TEXT not in line_text:
                    continue

                lb = line.get("bbox", (0, 0, 0, 0))
                print(f"\n    Line {l_idx} bbox={lb}")
                print(f"    行预览: {line_text[:100]}…" if len(line_text) > 100 else f"    行预览: {line_text}")

                for s_idx, span in enumerate(line.get("spans", [])):
                    font = span.get("font", "")[:20]
                    size = span.get("size", 0)
                    flags = span.get("flags", 0)
                    is_bold = bool(flags & 16)
                    is_italic = bool(flags & 2)
                    style = []
                    if is_bold:
                        style.append("粗体")
                    if is_italic:
                        style.append("斜体")
                    if "hei" in font.lower() or "bold" in font.lower():
                        style.append("黑体")
                    if "kai" in font.lower():
                        style.append("楷体")
                    style_str = "|".join(style) if style else "普通"

                    if "chars" in span:
                        chars = span["chars"]
                        text = "".join(c.get("c", "") for c in chars)
                        print(f"\n      Span {s_idx}: font={font} size={size:.1f} flags={flags} [{style_str}]")
                        print(f"        text={repr(text)}")
                        # 逐字：字符、bbox、是否粗体
                        for i, c in enumerate(chars):
                            ch = c.get("c", "?")
                            bbox = c.get("bbox", (0, 0, 0, 0))
                            ch_repr = repr(ch)
                            if ch in "。！？，、":
                                ch_repr += " ← 标点"
                            print(f"          [{i:2}] {ch_repr:8} bbox=({bbox[0]:.1f},{bbox[1]:.1f},{bbox[2]:.1f},{bbox[3]:.1f})")
                    else:
                        text = span.get("text", "")
                        bbox = span.get("bbox", (0, 0, 0, 0))
                        print(f"\n      Span {s_idx}: font={font} size={size:.1f} flags={flags} [{style_str}]")
                        print(f"        text={repr(text)} bbox={bbox}")

        print("\n")

    doc.close()
    print("✅ 完成")
    print("\n💡 若「。」与「社会的」在同一 span 且同 flags，会被一起包进 **；若分属不同 span 则标点自然在外")


if __name__ == "__main__":
    probe()
