#!/usr/bin/env python3
"""
用于修复脚注中的生卒年格式。
按照毛泽东选集一至五卷对人名的注释习惯，修改静火版、赤旗版中脚注内的生卒年格式。
不完全正确，但能覆盖大部分常见情况，需要 review。

仅处理 <li class="duokan-footnote-item"> 内的 <p class="footnote"> 文本。
括号内为生卒年的，统一为：中文数字年份——中文数字年份，无月日、无年字。

正例：艾森豪威尔（一八九〇——一九六九）
反例：艾思奇（一九一〇年——一九六六年） → 艾思奇（一九一〇——一九六六）
反例：张奚若（1889 年－1973 年 7 月 18 日） → 张奚若（一八八九——一九七三）
反例：梁漱溟（1893 年 10 月 18 日-1988 年 6 月 23 日） → 梁漱溟（一八九三——一九八八）
反例：陶侃（259 年－334 年 7 月 30 日） → 陶侃（二五九——三三四）
反例：孙冶方（1908-1983） → 孙冶方（一九〇八——一九八三）

用法：修改 DRY_RUN、DEFAULT_ROOT 后直接运行。
"""

import re
import sys
from pathlib import Path

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

DEFAULT_ROOT = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "data/raw/mao/毛泽东选集全七卷（官方、静火、润之赤旗三合一版）"
)
DRY_RUN = True  # True=只探测不修改，False=执行修改

# 0-9 → 〇一二三四五六七八九
DIGIT_TO_CJK = str.maketrans("0123456789", "〇一二三四五六七八九")


def arabic_to_chinese(num_str: str) -> str:
    """阿拉伯数字转中文数字，如 1908 → 一九〇八"""
    return num_str.translate(DIGIT_TO_CJK)


def normalize_chinese_year(s: str) -> str:
    """若已是中文数字年份，去掉末尾的 年，如 一九一〇年 → 一九一〇"""
    s = s.strip()
    if s.endswith("年"):
        s = s[:-1]
    return s.strip()


def extract_years(content: str) -> tuple[str, str] | None:
    """
    从括号内容中提取两个年份。支持：
    - 1908-1983
    - 1889 年－1973 年 7 月 18 日
    - 一九一〇年——一九六六年
    - 1908.11.19～1969.06.03
    返回 (year1_cjk, year2_cjk) 或 None
    """
    content = content.strip()
    if not content:
        return None

    # 分隔符：——、-、－、~、～、—
    sep = r"[——\-－~～—]+"
    parts = re.split(sep, content, maxsplit=1)
    if len(parts) != 2:
        return None

    left = parts[0].strip()
    right = re.sub(r"^[——\-－~～—]+", "", parts[1]).strip()
    if not left or not right:
        return None

    def get_year(s: str) -> str | None:
        """从片段中提取年份（阿拉伯或中文），返回可转中文的字符串"""
        s = s.strip()
        # 中文数字年份：一九一〇、一九〇七
        m = re.match(r"^([一二三四五六七八九〇零十百千]+)", s)
        if m:
            y = m.group(1)
            if 2 <= len(y) <= 4:  # 二五九、一九〇八
                return normalize_chinese_year(y)
        # 阿拉伯数字：1908、1908.11.19、1889 年
        m = re.match(r"^(\d{1,4})", s)
        if m:
            return m.group(1)
        return None

    y1, y2 = get_year(left), get_year(right)
    if not y1 or not y2:
        return None

    # 若为阿拉伯数字，转中文
    if y1.isdigit():
        y1 = arabic_to_chinese(y1)
    if y2.isdigit():
        y2 = arabic_to_chinese(y2)

    return (y1, y2)


def fix_footnote_text(text: str) -> tuple[str, list[tuple[str, str]]]:
    """
    修复脚注文本中的生卒年。返回 (新文本, [(原, 改), ...])
    """
    changes = []
    result = text

    # 匹配 全角（...）或 半角(...) 内疑似生卒年
    def repl(m: re.Match) -> str:
        inner = m.group(1)
        years = extract_years(inner)
        if years is None:
            return m.group(0)
        y1, y2 = years
        fixed_inner = f"{y1}——{y2}"
        if inner != fixed_inner:
            changes.append((m.group(0), f"（{fixed_inner}）"))
            return f"（{fixed_inner}）"
        return m.group(0)

    # 全角括号
    result = re.sub(r"（([^）]*?)）", repl, result)
    return result, changes


def process_xhtml_simple(path: Path) -> list[tuple[int, str, str, str]]:
    """
    简化版：直接对 HTML 字符串做正则替换，只替换 footnote 段落内的括号内容。
    """
    html = path.read_text(encoding="utf-8")
    results = []

    # 匹配 <p class="footnote">...</p> 内的内容
    def process_footnote(m: re.Match) -> str:
        full = m.group(0)
        content = m.group(1)
        new_content, changes = fix_footnote_text(content)
        if changes:
            for old_val, new_val in changes:
                if old_val in content:
                    # 记录（用 content 找行号较复杂，先记 full）
                    pos = html.find(full)
                    line_no = html[:pos].count("\n") + 1
                    preview = content[:80] + "..." if len(content) > 80 else content
                    results.append((line_no, old_val, new_val, preview))
                    content = content.replace(old_val, new_val, 1)
                    break
        return full.replace(m.group(1), content, 1)

    # 匹配 footnote 段落：<p class="footnote">...<a...>◎</a>...文本...</p>
    # 需要匹配整个 p 标签内容。用更简单的策略：找所有 （...） 在 li.duokan-footnote-item 内的
    pat = re.compile(
        r'<li class="duokan-footnote-item"[^>]*>.*?<p class="footnote">(.*?)</p>\s*</li>',
        re.DOTALL,
    )

    def strip_html(s: str) -> str:
        return re.sub(r"<[^>]+>", "", s).replace("\n", " ").strip()

    def repl_li(m: re.Match) -> str:
        li_full = m.group(0)
        p_content = m.group(1)
        new_p, changes = fix_footnote_text(p_content)
        if changes:
            text = strip_html(p_content)
            for old_val, new_val in changes:
                pos = html.find(li_full)
                line_no = html[:pos].count("\n") + 1
                # 以匹配处为中心，前后各取约 60 字
                idx = text.find(old_val)
                if idx >= 0:
                    start = max(0, idx - 60)
                    end = min(len(text), idx + len(old_val) + 60)
                    preview = ("..." if start > 0 else "") + text[start:end] + ("..." if end < len(text) else "")
                else:
                    preview = text[:150] + ("..." if len(text) > 150 else "")
                results.append((line_no, old_val, new_val, preview))
            return li_full.replace(m.group(1), new_p, 1)
        return li_full

    new_html = pat.sub(repl_li, html)
    if not DRY_RUN and results:
        path.write_text(new_html, encoding="utf-8")
    return results


def main() -> int:
    root = DEFAULT_ROOT.resolve()
    if not root.is_dir():
        print(f"错误：{root} 不是目录", flush=True)
        return 1

    text_dir = root / "OEBPS" / "Text"
    if not text_dir.exists():
        print(f"错误：未找到 {text_dir}", flush=True)
        return 1

    print(f"目录: {root}")
    print(f"模式: {'探测（DRY_RUN=True）' if DRY_RUN else '执行修复'}\n")

    total = 0
    for f in sorted(text_dir.glob("*.xhtml")):
        items = process_xhtml_simple(f)
        for line_no, old_val, new_val, preview in items:
            total += 1
            print(f"\n  {f.name}  L{line_no}")
            print(f"    原: {repr(old_val)}")
            print(f"    改: {repr(new_val)}")
            print(f"    上下文: {preview}")

    print(f"\n--- 汇总 ---")
    print(f"  共 {total} 处")
    if not DRY_RUN and total > 0:
        print("  已保存修改")
    return 0


if __name__ == "__main__":
    sys.exit(main())
