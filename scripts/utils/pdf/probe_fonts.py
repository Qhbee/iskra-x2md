"""
探测 PDF 中的字体信息：楷体、仿宋、黑体、宋体等
用法：修改 TARGET_PAGES，运行
"""
import fitz
from pathlib import Path
from collections import defaultdict

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
INPUT_PDF = PROJECT_ROOT / "data/raw/lenin/列宁全集（版本II-文字版）（完整书签版）/列宁全集 第1卷（1893年—1894年）.pdf"

# 可选：直接指定页码
TARGET_PAGES = []  # 留空则自动搜索全书


def _decode_flags(flags_set):
    """将 flags 集合转为可读描述"""
    parts = []
    for f in sorted(flags_set):
        if f == 0:
            parts.append("普通")
        else:
            names = []
            if f & 1: names.append("上标")
            if f & 2: names.append("斜体")
            if f & 4: names.append("衬线")
            if f & 8: names.append("无衬线")
            if f & 16: names.append("粗体")
            if f & 32: names.append("等宽")
            parts.append("+".join(names) if names else str(f))
    return "(" + ";".join(parts) + ")" if parts else ""


def classify_font(font_name):
    """按 lenin_parser 的语义归类"""
    f = font_name.lower()
    if "kai" in f:
        return "楷体"
    if "fang" in f:
        return "仿宋"
    if "hei" in f or "bold" in f or "simhei" in f:
        return "黑体"
    if "song" in f or "simsun" in f or "宋体" in f:
        return "宋体"
    return "其他"


def probe():
    if not INPUT_PDF.exists():
        print(f"[X] 找不到: {INPUT_PDF}")
        return

    doc = fitz.open(INPUT_PDF)
    pages = [p - 1 for p in TARGET_PAGES] if TARGET_PAGES else list(range(doc.page_count))

    # font -> {count, sizes, flags, pages}
    font_info = defaultdict(lambda: {"count": 0, "sizes": set(), "flags": set(), "pages": set()})
    # 语义类 -> 字体列表
    by_class = defaultdict(set)

    for page_idx in pages:
        if page_idx >= doc.page_count:
            break
        page = doc[page_idx]
        data = page.get_text("rawdict", clip=page.rect)

        for block in data.get("blocks", []):
            if "lines" not in block:
                continue
            for line in block["lines"]:
                for span in line.get("spans", []):
                    font = span.get("font", "")
                    size = span.get("size", 0)
                    flags = span.get("flags", 0)
                    font_info[font]["count"] += 1
                    font_info[font]["sizes"].add(round(size, 1))
                    font_info[font]["flags"].add(flags)
                    font_info[font]["pages"].add(page_idx + 1)  # 1-based
                    by_class[classify_font(font)].add(font)

    doc.close()

    # 输出
    print("=" * 70)
    print("[probe] 字体信息")
    print("=" * 70)
    print(f"PDF: {INPUT_PDF.name}")
    print(f"扫描: {len(pages)} 页\n")

    print("【按语义类】")
    for cls in ["黑体", "楷体", "仿宋", "宋体", "其他"]:
        fonts = by_class.get(cls, set())
        if not fonts:
            continue
        total = sum(font_info[f]["count"] for f in fonts)
        all_pages = set()
        for f in fonts:
            all_pages |= font_info[f]["pages"]
        pages_str = ",".join(str(p) for p in sorted(all_pages)[:5])
        if len(all_pages) > 5:
            pages_str += f"...(共{len(all_pages)}页)"
        print(f"  {cls}: {total} span, 字体={sorted(fonts)}, 页码={pages_str}")

    print("\n【按字体名】font | span数 | 字号 | flags | 页码")
    for font in sorted(font_info.keys(), key=lambda f: -font_info[f]["count"]):
        info = font_info[font]
        sizes = sorted(info["sizes"])[:6]
        sizes_str = ",".join(str(s) for s in sizes) + (".." if len(info["sizes"]) > 6 else "")
        flags_desc = _decode_flags(info["flags"])
        pages_sorted = sorted(info["pages"])
        if len(pages_sorted) <= 8:
            pages_str = ",".join(str(p) for p in pages_sorted)
        else:
            pages_str = ",".join(str(p) for p in pages_sorted[:4]) + f"..{pages_sorted[-1]}(共{len(pages_sorted)}页)"
        cls = classify_font(font)
        print(f"  {font[:22]:<22} | {info['count']:>6} | {sizes_str:>10} | {flags_desc:>12} | {pages_str} [{cls}]")

    print("\n--- flags 说明 (PyMuPDF 位标志, 可组合相加) ---")
    print("  0=普通  1=上标  2=斜体  4=衬线  8=无衬线  16=粗体  32=等宽")
    print("  例: 18 = 16+2 = 粗体+斜体")


if __name__ == "__main__":
    probe()
