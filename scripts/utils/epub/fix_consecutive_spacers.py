#!/usr/bin/env python3
"""
探测并删除连续的 calibre3 空行块。

目标：<p class="calibre3" style="margin:0pt; border:0pt; height:1em"> </p>
当连续出现 2 个及以上时，合并为 1 个，减少多余垂直空白（可能引起阅读器末尾多翻一页空白）。

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
DRY_RUN = True  # True=只探测不修改，False=执行删除

# 单个 spacer 的完整标签（内容为 NBSP，与原文一致）
SPACER_TAG = '<p class="calibre3" style="margin:0pt; border:0pt; height:1em">\xa0</p>'
SPACER_PATTERN = re.compile(
    r'<p\s+class="calibre3"\s+style="margin:0pt;\s*border:0pt;\s*height:1em">[\s\xa0]*</p>',
    re.IGNORECASE
)
# 匹配连续 2 个及以上的 spacer（\s* 含换行与缩进；结尾仅换行，不吞下一行缩进）
SPACER_PART = r'\s*<p\s+class="calibre3"\s+style="margin:0pt;\s*border:0pt;\s*height:1em">[\s\xa0]*</p>(?:\r?\n)*'
MULTI_SPACER = re.compile(r'((?:' + SPACER_PART + r'){2,})', re.IGNORECASE)


def find_consecutive_spacers(text: str) -> list[tuple[int, str, int]]:
    """
    找出连续 2+ 个 spacer 的位置。
    返回 [(start, matched_text, count), ...]
    """
    results = []
    for m in MULTI_SPACER.finditer(text):
        chunk = m.group(1)
        count = len(SPACER_PATTERN.findall(chunk))
        if count >= 2:
            results.append((m.start(), chunk, count))
    return results


def dedupe_spacers(text: str) -> str:
    """将连续 2+ 个 spacer 合并为 1 个"""
    def repl(m: re.Match) -> str:
        chunk = m.group(1)
        first = SPACER_PATTERN.search(chunk)
        if first:
            prefix = chunk[: first.start()]
            return prefix + SPACER_TAG + "\n\n"
        return chunk
    return MULTI_SPACER.sub(repl, text)


def process_file(path: Path) -> list[tuple[int, str, int]]:
    """处理单个 xhtml，返回 [(line_no, chunk_preview, count), ...]"""
    text = path.read_text(encoding="utf-8")
    found = find_consecutive_spacers(text)
    results = []
    for start, chunk, count in found:
        line_no = text[:start].count("\n") + 1
        preview = chunk.replace("\n", " ").strip()[:80] + ("..." if len(chunk) > 80 else "")
        results.append((line_no, preview, count))
    if not DRY_RUN and found:
        new_text = dedupe_spacers(text)
        if new_text != text:
            path.write_text(new_text, encoding="utf-8")
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
    print(f"模式: {'探测（DRY_RUN=True）' if DRY_RUN else '执行删除'}\n")

    total = 0
    for f in sorted(text_dir.glob("*.xhtml")):
        items = process_file(f)
        for line_no, preview, count in items:
            total += 1
            print(f"  {f.name}  L{line_no}  连续 {count} 个")
            print(f"    {preview}")

    print(f"\n--- 汇总 ---")
    print(f"  共 {total} 处连续 spacer")
    if not DRY_RUN and total > 0:
        print("  已保存修改")
    elif DRY_RUN and total > 0:
        print("  DRY_RUN=True，未实际修改。改为 False 后重新运行以执行。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
