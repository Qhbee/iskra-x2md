"""
探测 PDF 脚注结构：正文引用数 vs 页底 ① 数量、每行原始内容
用于排查 [^101]: 等空注脚问题

可能原因：
1. 正文 ① 数量 ≠ 页底 ① 数量 → 队列错位，部分注脚领到空内容
2. 页底某行仅有 ① 无内容 → PDF 本身是空白注脚
3. 注脚超过 ⑩ 使用 ⑪⑫… → 解析器仅匹配 ①-⑩ (U+2460-U+2469)

用法：
    1. 在 index.md 中搜 [^101] 等空注脚，找到对应文章
    2. 从文章路径推算页码范围（或搜索文中关键字定位页码）
    3. 修改下方 TARGET_PAGES、INPUT_PDF，运行：python scripts/utils/pdf/probe_footnotes.py
"""
import fitz
import re
from pathlib import Path

# ================= 配置 =================
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
INPUT_PDF = PROJECT_ROOT / "data/raw/lenin/列宁全集（版本II-文字版）（完整书签版）/列宁全集 第1卷（1893年—1894年）.pdf"

# 要探测的页码（1-based），可填多页以定位问题
TARGET_PAGES = [301, 302, 303]

# 分割线相关（与 lenin_parser 一致）
DETECT_THRESHOLD = 40
MARGIN_TOP_CUT = 110
MARGIN_BOTTOM_CUT = 520


def get_split_y(page):
    """与 lenin_parser 相同的分割线逻辑"""
    blocks = page.get_text("blocks")
    page_height = page.rect.height
    h_lines = []
    for d in page.get_drawings():
        r = d.get("rect")
        if not r or r.height >= 5:
            continue
        if 60 <= r.width <= 75:
            h_lines.append(r.y0)
    if h_lines:
        return max(h_lines) - 2
    for b in blocks:
        y0 = b[1]
        text = b[4].strip()
        if y0 > DETECT_THRESHOLD and re.search(r'接\s*上\s*页', text):
            return y0 - 1
    return page_height


def count_body_refs(text):
    """统计正文中 ①-⑩ 的出现次数（与解析器替换顺序一致）"""
    return len(re.findall(r'[\u2460-\u2469]', text))


def probe():
    if not INPUT_PDF.exists():
        print(f"❌ 找不到: {INPUT_PDF}")
        return

    doc = fitz.open(INPUT_PDF)

    for page_num in TARGET_PAGES:
        if page_num < 1 or page_num > doc.page_count:
            print(f"⚠️ 页码 {page_num} 超出范围")
            continue

        page = doc[page_num - 1]
        split_y = get_split_y(page)
        actual_top = min(MARGIN_TOP_CUT, split_y)
        clip_bottom = min(MARGIN_BOTTOM_CUT, page.rect.height)
        clip_rect = fitz.Rect(0, actual_top, page.rect.width, clip_bottom)
        data = page.get_text("rawdict", clip=clip_rect)

        body_lines = []
        foot_lines = []

        for block in data.get("blocks", []):
            if "image" in block:
                continue
            for line in block.get("lines", []):
                raw = "".join("".join(c["c"] for c in s["chars"]) for s in line.get("spans", []))
                bbox = line.get("bbox", (0, 0, 0, 0))
                if bbox[1] >= split_y:
                    foot_lines.append(raw.strip())
                else:
                    body_lines.append(raw.strip())

        body_ref_count = count_body_refs("".join(body_lines))
        foot_starts = [i for i, t in enumerate(foot_lines) if re.match(r'^[\u2460-\u2469]', t)]

        print("=" * 80)
        print(f"  📃 第 {page_num} 页  |  split_y={split_y:.1f}")
        print(f"  正文行数: {len(body_lines)}  |  正文 ①-⑩ 出现次数: {body_ref_count}")
        print(f"  注脚行数: {len(foot_lines)}  |  以 ①-⑩ 开头的行数: {len(foot_starts)}")
        if body_ref_count != len(foot_starts):
            print(f"  ⚠️ 不匹配：正文有 {body_ref_count} 个引用，页底有 {len(foot_starts)} 个 ① 行")
        print("-" * 80)
        print("  注脚区域原始内容：")
        for i, t in enumerate(foot_lines):
            flag = " ← 新注脚" if re.match(r'^[\u2460-\u2469]', t) else ""
            empty = " ⚠️ 空/仅有符号" if re.match(r'^[\u2460-\u2469]\s*$', t) else ""
            preview = (t[:70] + "…") if len(t) > 70 else t
            print(f"    [{i}] {repr(preview)}{flag}{empty}")
        print()

    doc.close()
    print("✅ 完成")


if __name__ == "__main__":
    probe()
