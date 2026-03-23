#!/usr/bin/env python3
"""
探测并修复「阿拉伯数字～数值范围」分隔符：统一为浪纹线 ～（U+FF5E，全角）。

与 fix_date_range_sep.py 区分：
    - 仅匹配纯阿拉伯数字，不限位数；
    - 每一侧至多一个小数点（形如 34.5、1956.06），不匹配 1908.11.19 这类多点；
    - 中间可为 ~、～、—、–、-、－、—— 等，目标一律为 ～。

误报可能：电话号码片段、IP 等形如「数字-数字」；毛选正文中较少，请结合探测结果判断。

用法：修改 DRY_RUN、DEFAULT_ROOT、EXCLUDE_FOLLOWED_BY_PAGE 后运行；或：
    python fix_numeric_range_wave.py [--fix] [--include-page-ranges]
"""

from __future__ import annotations

import argparse
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
DRY_RUN = True  # True=只探测，False=写回文件

# True：跳过「范围」后紧接空白+「页」的匹配（如 12-15页、350～400 页），避免页码区间被改
EXCLUDE_FOLLOWED_BY_PAGE = True

# 国标数值范围常用浪纹线（全角）
TARGET_SEP = "～"  # U+FF5E

# 需替换为 ～ 的分隔符（长串在前）
BAD_SEPS = r"(?:——|[-~～－—–])"

# 单侧：纯整数，或「整数.小数」且整段仅一个点
_NUM_ONE = r"(?:\d+\.\d+|\d+)"
# 两侧不得与更长数字串粘连（避免 1908.11.19、1.2.3）
NUM_RANGE = re.compile(
    rf"(?<![\d.])({_NUM_ONE})({BAD_SEPS})({_NUM_ONE})(?![\d.])"
)

_FOLLOWED_BY_PAGE = re.compile(r"^\s*页")


def _is_followed_by_page(text: str, match_end: int) -> bool:
    """匹配结束位置之后是否为（可选空白）+「页」。"""
    return bool(_FOLLOWED_BY_PAGE.match(text[match_end:]))


def find_issues(
    text: str,
    *,
    exclude_followed_by_page: bool | None = None,
) -> list[tuple[int, str, str]]:
    """返回 [(start, 原片段, 修复后), ...]，已为 ～ 且两侧数字不变则跳过。"""
    excl = EXCLUDE_FOLLOWED_BY_PAGE if exclude_followed_by_page is None else exclude_followed_by_page
    issues: list[tuple[int, str, str]] = []
    for m in NUM_RANGE.finditer(text):
        if excl and _is_followed_by_page(text, m.end()):
            continue
        n1, _sep, n2 = m.group(1), m.group(2), m.group(3)
        fixed = f"{n1}{TARGET_SEP}{n2}"
        if m.group(0) != fixed:
            issues.append((m.start(), m.group(0), fixed))
    return issues


def fix_text(
    text: str,
    *,
    exclude_followed_by_page: bool | None = None,
) -> tuple[str, list[tuple[int, str, str]]]:
    issues = find_issues(text, exclude_followed_by_page=exclude_followed_by_page)
    if not issues:
        return text, []
    result = text
    for start, orig, fixed in reversed(issues):
        result = result[:start] + fixed + result[start + len(orig) :]
    return result, issues


def probe_xhtml(
    path: Path,
    *,
    exclude_followed_by_page: bool | None = None,
) -> list[tuple[int, str, str, str]]:
    text = path.read_text(encoding="utf-8")
    results = []
    for line_no, line in enumerate(text.split("\n"), 1):
        for start, orig, fixed in find_issues(
            line, exclude_followed_by_page=exclude_followed_by_page
        ):
            ctx_start = max(0, start - 25)
            ctx_end = min(len(line), start + len(orig) + 25)
            results.append((line_no, orig, fixed, line[ctx_start:ctx_end]))
    return results


def fix_xhtml(
    path: Path,
    *,
    exclude_followed_by_page: bool | None = None,
) -> list[tuple[int, str, str]]:
    text = path.read_text(encoding="utf-8")
    new_text, issues = fix_text(text, exclude_followed_by_page=exclude_followed_by_page)
    if not issues:
        return []
    line_offsets = [0]
    for line in text.split("\n"):
        line_offsets.append(line_offsets[-1] + len(line) + 1)
    out: list[tuple[int, str, str]] = []
    for start, orig, fixed in issues:
        line_no = 1
        for i in range(len(line_offsets) - 1):
            if line_offsets[i] <= start < line_offsets[i + 1]:
                line_no = i + 1
                break
        out.append((line_no, orig, fixed))
    path.write_text(new_text, encoding="utf-8")
    return out


def probe_toc_ncx(
    path: Path,
    *,
    exclude_followed_by_page: bool | None = None,
) -> list[tuple[str, str, str]]:
    text = path.read_text(encoding="utf-8")
    results = []
    for m in re.finditer(r"<text>([^<]*)</text>", text):
        for _, orig, fixed in find_issues(
            m.group(1), exclude_followed_by_page=exclude_followed_by_page
        ):
            results.append(("<text>", orig, fixed))
    return results


def fix_toc_ncx(
    path: Path,
    *,
    exclude_followed_by_page: bool | None = None,
) -> list[tuple[str, str, str]]:
    text = path.read_text(encoding="utf-8")
    results: list[tuple[str, str, str]] = []

    def repl(m: re.Match[str]) -> str:
        content = m.group(1)
        new_content, issues = fix_text(
            content, exclude_followed_by_page=exclude_followed_by_page
        )
        for _, orig, fixed in issues:
            results.append(("<text>", orig, fixed))
        return f"<text>{new_content}</text>"

    new_text = re.sub(r"<text>([^<]*)</text>", repl, text)
    if results:
        path.write_text(new_text, encoding="utf-8")
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="数值范围分隔符 → ～")
    parser.add_argument(
        "--fix",
        action="store_true",
        help="执行写回（默认仅探测；也可用脚本顶部 DRY_RUN=False）",
    )
    parser.add_argument(
        "--include-page-ranges",
        action="store_true",
        help="仍处理「数字-数字页 / 数字 页」类区间（默认：见脚本 EXCLUDE_FOLLOWED_BY_PAGE，常为排除）",
    )
    parser.add_argument(
        "root",
        nargs="?",
        type=Path,
        default=None,
        help="EPUB 解压根目录（默认 DEFAULT_ROOT）",
    )
    args = parser.parse_args()
    root = (args.root or DEFAULT_ROOT).resolve()
    dry = DRY_RUN and not args.fix
    exclude_page = EXCLUDE_FOLLOWED_BY_PAGE and not args.include_page_ranges

    if not root.is_dir():
        print(f"错误：{root} 不是目录", flush=True)
        return 1

    text_dir = root / "OEBPS" / "Text"
    toc_path = root / "toc.ncx"
    if not text_dir.exists():
        print(f"错误：未找到 {text_dir}", flush=True)
        return 1

    print(f"目录: {root}")
    print(f"模式: {'探测（不修改）' if dry else '执行修复'}")
    print(
        f"后接「页」: {'跳过' if exclude_page else '仍处理'} "
        f"(EXCLUDE_FOLLOWED_BY_PAGE={EXCLUDE_FOLLOWED_BY_PAGE}"
        f"{', --include-page-ranges' if args.include_page_ranges else ''})\n"
    )

    total = 0
    print("=== OEBPS/Text/*.xhtml ===")
    for f in sorted(text_dir.glob("*.xhtml")):
        if dry:
            for line_no, orig, fixed, ctx in probe_xhtml(
                f, exclude_followed_by_page=exclude_page
            ):
                total += 1
                print(f"\n  {f.name}  L{line_no}")
                print(f"    原: {repr(orig)}")
                print(f"    改: {repr(fixed)}")
                print(f"    上下文: {repr(ctx)}")
        else:
            for line_no, orig, fixed in fix_xhtml(
                f, exclude_followed_by_page=exclude_page
            ):
                total += 1
                print(f"\n  {f.name}  L{line_no}")
                print(f"    {repr(orig)} → {repr(fixed)}")

    print("\n=== toc.ncx ===")
    if toc_path.exists():
        if dry:
            items = probe_toc_ncx(toc_path, exclude_followed_by_page=exclude_page)
        else:
            items = fix_toc_ncx(toc_path, exclude_followed_by_page=exclude_page)
        for loc, orig, fixed in items:
            total += 1
            print(f"\n  {loc}")
            print(f"    原: {repr(orig)}")
            print(f"    改: {repr(fixed)}")

    print(f"\n--- 汇总 ---")
    print(f"  共 {total} 处")
    if not dry and total > 0:
        print("  已保存修改")
    return 0


if __name__ == "__main__":
    sys.exit(main())
