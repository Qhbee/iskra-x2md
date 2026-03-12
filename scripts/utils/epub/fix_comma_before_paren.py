#!/usr/bin/env python3
"""
修复逗号位置错误：逗号在左括号前，应在右括号后。

错误：某某，（括号内容）后面的文字
正确：某某（括号内容），后面的文字

全文处理，不限脚注，不限括号内容类型。
排除：纯列举项如（一）（二）（三）或（1）（2）（3）等，不修改。

注意：可能会误伤，需要 review，比如 "工人不听话，（资本家）要斗争（工人），这是合法的" 这种情况不用改。
用法：修改 DRY_RUN、DEFAULT_ROOT 后直接运行。
"""

import re

# 纯数字列举项，跳过不修改
SKIP_PURE_NUM = re.compile(r"^[一二三四五六七八九十〇零百千]+$|^\d+$")


def is_pure_num_list(inner: str) -> bool:
    """括号内容是否为纯数字列举，如（一）（二）或（1）（2）"""
    return bool(SKIP_PURE_NUM.match(inner.strip()))
import sys
from pathlib import Path

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

DEFAULT_ROOT = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "data/raw/mao/毛泽东选集全七卷（官方、静火、润之赤旗三合一版）"
)
DRY_RUN = True  # True=只探测不修改，False=执行修复


def fix_comma_pos(text: str) -> tuple[str, list[tuple[int, str, str]]]:
    """
    将 ，（...） 或 ，（...）， 改为 （...），
    返回 (新文本, [(位置, 原, 改), ...])
    """
    changes = []

    def repl(m: re.Match) -> str:
        inner = m.group(1)
        if is_pure_num_list(inner):
            return m.group(0)
        trailing_comma = m.group(2) or ""
        old = f"，（{inner}）{trailing_comma}"
        new = f"（{inner}），"
        changes.append((m.start(), old, new))
        return new

    result = re.sub(r"，（([^）]+)）([，]?)", repl, text)
    return result, changes


def process_xhtml(path: Path) -> list[tuple[int, str, str, str]]:
    """处理单个 xhtml 全文"""
    html = path.read_text(encoding="utf-8")
    results = []

    new_html, changes = fix_comma_pos(html)
    for pos, old_val, new_val in changes:
        line_no = html[:pos].count("\n") + 1
        # 上下文：取匹配处前后各约 40 字（去 HTML）
        start = max(0, pos - 60)
        end = min(len(html), pos + len(old_val) + 60)
        ctx = html[start:end]
        ctx = re.sub(r"<[^>]+>", "", ctx).replace("\n", " ")
        ctx = ("..." if start > 0 else "") + ctx + ("..." if end < len(html) else "")
        results.append((line_no, old_val, new_val, ctx))

    if not DRY_RUN and results:
        path.write_text(new_html, encoding="utf-8")
    return results


def main() -> int:
    root = DEFAULT_ROOT.resolve()
    if not root.is_dir():
        print(f"错误：{root} 不是目录", flush=True)
        return 1

    text_dir = root / "OEBPS" / "Text"
    toc_path = root / "toc.ncx"
    if not text_dir.exists():
        print(f"错误：未找到 {text_dir}", flush=True)
        return 1

    print(f"目录: {root}")
    print(f"模式: {'探测（DRY_RUN=True）' if DRY_RUN else '执行修复'}\n")

    total = 0

    print("=== OEBPS/Text/*.xhtml ===")
    for f in sorted(text_dir.glob("*.xhtml")):
        items = process_xhtml(f)
        for line_no, old_val, new_val, preview in items:
            total += 1
            print(f"\n  {f.name}  L{line_no}")
            print(f"    原: {repr(old_val)}")
            print(f"    改: {repr(new_val)}")
            print(f"    上下文: {preview}")

    print("\n=== toc.ncx ===")
    if toc_path.exists():
        toc_text = toc_path.read_text(encoding="utf-8")
        new_toc, toc_changes = fix_comma_pos(toc_text)
        for pos, old_val, new_val in toc_changes:
            total += 1
            line_no = toc_text[:pos].count("\n") + 1
            start = max(0, pos - 40)
            end = min(len(toc_text), pos + len(old_val) + 40)
            ctx = toc_text[start:end].replace("\n", " ")
            print(f"\n  toc.ncx  L{line_no}")
            print(f"    原: {repr(old_val)}")
            print(f"    改: {repr(new_val)}")
            print(f"    上下文: {ctx}")
        if not DRY_RUN and toc_changes:
            toc_path.write_text(new_toc, encoding="utf-8")

    print(f"\n--- 汇总 ---")
    print(f"  共 {total} 处")
    if not DRY_RUN and total > 0:
        print("  已保存修改")
    return 0


if __name__ == "__main__":
    sys.exit(main())
