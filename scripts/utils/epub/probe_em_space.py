#!/usr/bin/env python3
"""
探测 EPUB 解压目录中文本里的 EM SPACE（全角 em 空格，U+2003， ）。

- 默认：只打印出现位置（文件、行号、上下文）。
- --replace：将 U+2003 全部替换为普通空格 U+0020 并写回文件。

用法：
    python probe_em_space.py
    python probe_em_space.py --replace
    python probe_em_space.py [解压根目录] [--replace]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

if sys.platform == "win32":
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

EMSP = "\u2003"  # EM SPACE
SPACE = " "  # U+0020

DEFAULT_ROOT = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "data/raw/mao/毛泽东选集全七卷（官方、静火、润之赤旗三合一版）"
)

# 参与扫描的扩展名（EPUB 常见文本）
TEXT_SUFFIXES = {".xhtml", ".html", ".htm", ".ncx", ".opf", ".css", ".xml"}
CONTEXT = 28


def _iter_text_files(root: Path) -> list[Path]:
    out: list[Path] = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() in TEXT_SUFFIXES:
            out.append(p)
    return sorted(out)


def probe_file(path: Path) -> list[tuple[int, int, str]]:
    """[(行号, 列偏移, 上下文片段), ...]"""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        print(f"⚠️ 读取失败 {path}: {e}", flush=True)
        return []
    hits: list[tuple[int, int, str]] = []
    for line_no, line in enumerate(text.splitlines(), 1):
        start = 0
        while True:
            i = line.find(EMSP, start)
            if i < 0:
                break
            a = max(0, i - CONTEXT)
            b = min(len(line), i + 1 + CONTEXT)
            ctx = line[a:b].replace("\n", "↵")
            hits.append((line_no, i, ctx))
            start = i + 1
    return hits


def replace_in_file(path: Path) -> tuple[int, bool]:
    """返回 (替换次数, 是否写回)"""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return 0, False
    count = text.count(EMSP)
    if count == 0:
        return 0, False
    new_text = text.replace(EMSP, SPACE)
    path.write_text(new_text, encoding="utf-8")
    return count, True


def main() -> int:
    ap = argparse.ArgumentParser(description="探测 / 替换 U+2003 EM SPACE")
    ap.add_argument(
        "root",
        nargs="?",
        type=Path,
        default=DEFAULT_ROOT,
        help="EPUB 解压根目录",
    )
    ap.add_argument(
        "--replace",
        action="store_true",
        help="将 U+2003 替换为普通空格并保存",
    )
    args = ap.parse_args()
    root = args.root.resolve()
    if not root.is_dir():
        print(f"❌ 不是目录: {root}", flush=True)
        return 1

    files = _iter_text_files(root)
    if not files:
        print(f"❌ 未找到可扫描文件: {TEXT_SUFFIXES}", flush=True)
        return 1

    print(f"📖 {root}")
    print(f"字符: EM SPACE U+2003 （显示为「{EMSP}」）")
    print(f"模式: {'替换为普通空格' if args.replace else '仅探测'}\n")
    print("=" * 80)

    total_hits = 0
    total_files = 0

    for fp in files:
        if args.replace:
            n, wrote = replace_in_file(fp)
            if n:
                total_hits += n
                total_files += 1
                try:
                    rel = fp.relative_to(root)
                except ValueError:
                    rel = fp
                print(f"\n✏️  {rel.as_posix()}  替换 {n} 处")
        else:
            hits = probe_file(fp)
            if not hits:
                continue
            total_files += 1
            total_hits += len(hits)
            try:
                rel = fp.relative_to(root)
            except ValueError:
                rel = fp
            print(f"\n--- {rel.as_posix()} --- ({len(hits)} 处)")
            for line_no, col, ctx in hits:
                print(f"  L{line_no}:{col}  {repr(ctx)}")

    print("\n" + "=" * 80)
    print(f"汇总: {total_hits} 处，涉及 {total_files} 个文件")
    if args.replace and total_hits:
        print("已写回磁盘。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
