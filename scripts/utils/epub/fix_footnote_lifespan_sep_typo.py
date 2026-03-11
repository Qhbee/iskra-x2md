#!/usr/bin/env python3
"""
修复脚注中括号内生卒年的分隔符错字：中间的「一」误为分隔符，应为「——」。

错误：张伯伦（一八六九一一九四〇）  （中间的一应为——）
正确：张伯伦（一八六九——一九四〇）

仅处理 <li class="duokan-footnote-item"> 内、括号（ ）中的内容。

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

# 中文数字年份：3-4 位，如 一八六九、一九四〇、二五九
YEAR_CJK = r"[一二三四五六七八九〇零]{3,4}"
# 错误：年份 + 一 + 年份（中间的一应为——）
PAT = re.compile(rf"（([^）]*?)({YEAR_CJK})一({YEAR_CJK})([^）]*?)）")


def fix_paren_content(text: str) -> tuple[str, list[tuple[str, str]]]:
    """
    将括号内的 年份一年份 改为 年份——年份
    返回 (新文本, [(原, 改), ...])
    """
    changes = []

    def repl(m: re.Match) -> str:
        pre, y1, y2, suf = m.group(1), m.group(2), m.group(3), m.group(4)
        old = f"（{pre}{y1}一{y2}{suf}）"
        new = f"（{pre}{y1}——{y2}{suf}）"
        changes.append((old, new))
        return new

    result = PAT.sub(repl, text)
    return result, changes


def strip_html(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s).replace("\n", " ").strip()


def process_xhtml(path: Path) -> list[tuple[int, str, str, str]]:
    """只处理脚注区"""
    html = path.read_text(encoding="utf-8")
    results = []

    pat = re.compile(
        r'<li class="duokan-footnote-item"[^>]*>.*?<p class="footnote">(.*?)</p>\s*</li>',
        re.DOTALL,
    )

    def repl_li(m: re.Match) -> str:
        li_full = m.group(0)
        p_content = m.group(1)
        new_p, changes = fix_paren_content(p_content)
        if changes:
            text = strip_html(p_content)
            for old_val, new_val in changes:
                pos = html.find(li_full)
                line_no = html[:pos].count("\n") + 1
                idx = text.find(old_val)
                if idx >= 0:
                    start = max(0, idx - 40)
                    end = min(len(text), idx + len(old_val) + 40)
                    preview = ("..." if start > 0 else "") + text[start:end] + ("..." if end < len(text) else "")
                else:
                    preview = text[:100] + ("..." if len(text) > 100 else "")
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
        items = process_xhtml(f)
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
