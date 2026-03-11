#!/usr/bin/env python3
"""
探测并修复「英文/数字」与「汉字」之间缺少空格的问题。

规则：
- 英文/数字 与 汉字 之间应有空格，如：1977年3月 → 1977 年 3 月，friend朋友 → friend 朋友
- 全角标点（。，、；：？！""''（）【】《》等）不视为汉字，英文/数字与全角标点之间可不加空格

模式：
- 探测（probe）：只扫描并报告问题，不修改
- 执行（fix）：实际插入空格并保存

用法：修改 DEFAULT_MODE、DEFAULT_ROOT 常量后直接运行 python fix_cjk_ascii_spaces.py
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
DEFAULT_MODE = "probe"  # probe/fix

# 英文/数字（含小数点，如 2.0、0.5）
ASCII_ALNUM = r"[a-zA-Z0-9]+(?:\.[a-zA-Z0-9]+)*"
# 汉字（CJK 统一汉字，不含全角标点）
CJK = r"[\u4e00-\u9fff]"

# 需要加空格的两种边界
PAT_ALNUM_CJK = re.compile(f"({ASCII_ALNUM})({CJK})")
PAT_CJK_ALNUM = re.compile(f"({CJK})({ASCII_ALNUM})")


def find_issues(text: str) -> list[tuple[int, str, str]]:
    """
    在文本中查找「英文/数字与汉字之间无空格」的位置。
    返回 [(start, 匹配片段, 修复后), ...]
    """
    issues = []
    for pat, fmt in [
        (PAT_ALNUM_CJK, r"\1 \2"),   # 英文/数字 + 汉字
        (PAT_CJK_ALNUM, r"\1 \2"),   # 汉字 + 英文/数字
    ]:
        for m in pat.finditer(text):
            fixed = m.expand(fmt)
            if m.group(0) != fixed:
                issues.append((m.start(), m.group(0), fixed))
    # 按位置排序，从后往前替换时不会偏移
    issues.sort(key=lambda x: x[0])
    return issues


def fix_text(text: str) -> tuple[str, list[tuple[int, str, str]]]:
    """
    在文本中插入空格。返回 (新文本, [(start, orig, fixed), ...])
    """
    issues = find_issues(text)
    if not issues:
        return text, []
    # 从后往前替换，避免偏移
    result = text
    for start, orig, fixed in reversed(issues):
        result = result[:start] + fixed + result[start + len(orig) :]
    return result, issues


def probe_xhtml(path: Path) -> list[tuple[int, str, str, str]]:
    """
    探测单个 xhtml 文件。返回 [(行号, 原片段, 修复后, 上下文), ...]
    """
    text = path.read_text(encoding="utf-8")
    lines = text.split("\n")
    results = []
    for i, line in enumerate(lines, 1):
        issues = find_issues(line)
        for start, orig, fixed in issues:
            # 上下文：前后各 20 字符
            ctx_start = max(0, start - 20)
            ctx_end = min(len(line), start + len(orig) + 20)
            ctx = line[ctx_start:ctx_end]
            results.append((i, orig, fixed, ctx))
    return results


def fix_xhtml(path: Path) -> list[tuple[int, str, str]]:
    """
    修复单个 xhtml 文件。返回 [(行号, 原片段, 修复后), ...]
    """
    text = path.read_text(encoding="utf-8")
    new_text, issues = fix_text(text)
    if not issues:
        return []
    # 计算行号（按字符偏移）
    line_offsets = [0]
    for line in text.split("\n"):
        line_offsets.append(line_offsets[-1] + len(line) + 1)
    results = []
    for start, orig, fixed in issues:
        line_no = 1
        for i in range(len(line_offsets) - 1):
            if line_offsets[i] <= start < line_offsets[i + 1]:
                line_no = i + 1
                break
        results.append((line_no, orig, fixed))
    path.write_text(new_text, encoding="utf-8")
    return results


def probe_toc_ncx(path: Path) -> list[tuple[str, str, str]]:
    """探测 toc.ncx 中 <text> 内容。返回 [(位置, 原片段, 修复后), ...]"""
    text = path.read_text(encoding="utf-8")
    results = []

    def repl(m: re.Match) -> str:
        content = m.group(1)
        issues = find_issues(content)
        for _, orig, fixed in issues:
            results.append((f"<text>", orig, fixed))
        if issues:
            new_content, _ = fix_text(content)
            return f"<text>{new_content}</text>"
        return m.group(0)

    # 只探测，不修改
    for m in re.finditer(r"<text>([^<]*)</text>", text):
        content = m.group(1)
        issues = find_issues(content)
        for _, orig, fixed in issues:
            results.append((f"<text>", orig, fixed))
    return results


def fix_toc_ncx(path: Path) -> list[tuple[str, str, str]]:
    """修复 toc.ncx 中 <text> 内容。返回 [(位置, 原片段, 修复后), ...]"""
    text = path.read_text(encoding="utf-8")
    results = []

    def repl(m: re.Match) -> str:
        content = m.group(1)
        new_content, issues = fix_text(content)
        for _, orig, fixed in issues:
            results.append((f"<text>", orig, fixed))
        return f"<text>{new_content}</text>"

    new_text = re.sub(r"<text>([^<]*)</text>", repl, text)
    if results:
        path.write_text(new_text, encoding="utf-8")
    return results


def main() -> int:
    mode = DEFAULT_MODE
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
    print(f"模式: {'探测（不修改）' if mode == 'probe' else '执行修复'}\n")

    total = 0

    # xhtml
    print("=== OEBPS/Text/*.xhtml ===")
    for f in sorted(text_dir.glob("*.xhtml")):
        if mode == "probe":
            items = probe_xhtml(f)
            for line_no, orig, fixed, ctx in items:
                total += 1
                print(f"\n  {f.name}  L{line_no}")
                print(f"    原: {repr(orig)}")
                print(f"    改: {repr(fixed)}")
                print(f"    上下文: {repr(ctx)}")
        else:
            items = fix_xhtml(f)
            for line_no, orig, fixed in items:
                total += 1
                print(f"\n  {f.name}  L{line_no}")
                print(f"    {repr(orig)} → {repr(fixed)}")

    # toc.ncx
    print("\n=== toc.ncx ===")
    if toc_path.exists():
        if mode == "probe":
            items = probe_toc_ncx(toc_path)
        else:
            items = fix_toc_ncx(toc_path)
        for loc, orig, fixed in items:
            total += 1
            print(f"\n  {loc}")
            print(f"    原: {repr(orig)}")
            print(f"    改: {repr(fixed)}")

    print(f"\n--- 汇总 ---")
    print(f"  共 {total} 处")
    if mode == "fix" and total > 0:
        print("  已保存修改")
    return 0


if __name__ == "__main__":
    sys.exit(main())
