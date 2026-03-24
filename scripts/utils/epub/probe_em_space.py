#!/usr/bin/env python3
"""
探测 EPUB 解压目录文本中的「非常规 Unicode 空白」（与 fix_sign_spacing.py 顶部说明对齐）。

包含：U+00A0、U+2002–U+200B、U+202F、U+205F、U+3000、U+FEFF 等。
不含 U+0020（半角空格），以免 HTML/XML 里刷屏。

- 默认：按码点打印出现位置（文件、行号、标签、上下文）。
- --replace：可视类 → 普通空格 U+0020；零宽类（U+200B、U+FEFF）→ 删除。写回文件。

用法：
    python probe_em_space.py
    python probe_em_space.py --replace
    python probe_em_space.py [解压根目录] [--replace]
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

if sys.platform == "win32":
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

SPACE = " "  # U+0020

# (字符, 探测输出用短标签)。顺序决定同位置多字符时优先级（单字符不会重叠）
# 零宽：替换时删除，不换成 U+0020
SPECIAL_SPACE_CHARS: tuple[tuple[str, str], ...] = (
    # ("\u00a0", "U+00A0 NBSP"),
    ("\u2002", "U+2002 EN SPACE"),
    ("\u2003", "U+2003 EM SPACE"),
    ("\u2004", "U+2004 THREE-PER-EM"),
    ("\u2005", "U+2005 FOUR-PER-EM"),
    ("\u2006", "U+2006 SIX-PER-EM"),
    ("\u2007", "U+2007 FIGURE SPACE"),
    ("\u2008", "U+2008 PUNCTUATION SPACE"),
    ("\u2009", "U+2009 THIN SPACE"),
    ("\u200a", "U+200A HAIR SPACE"),
    ("\u200b", "U+200B ZWSP"),
    ("\u202f", "U+202F NARROW NBSP"),
    ("\u205f", "U+205F MMSP"),
    ("\u3000", "U+3000 IDEOGRAPHIC"),
    ("\ufeff", "U+FEFF ZWNBSP/BOM"),
)

ZERO_WIDTH_REPLACE_EMPTY: frozenset[str] = frozenset({"\u200b", "\ufeff"})

CHAR_TO_LABEL: dict[str, str] = {ch: lab for ch, lab in SPECIAL_SPACE_CHARS}
PROBE_SET: frozenset[str] = frozenset(CHAR_TO_LABEL.keys())

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


def probe_file(path: Path) -> list[tuple[int, int, str, str]]:
    """[(行号, 列, 标签, 上下文), ...]"""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        print(f"⚠️ 读取失败 {path}: {e}", flush=True)
        return []
    hits: list[tuple[int, int, str, str]] = []
    for line_no, line in enumerate(text.splitlines(), 1):
        for i, ch in enumerate(line):
            if ch in PROBE_SET:
                a = max(0, i - CONTEXT)
                b = min(len(line), i + 1 + CONTEXT)
                ctx = line[a:b].replace("\n", "↵")
                hits.append((line_no, i, CHAR_TO_LABEL[ch], ctx))
    return hits


def replace_in_file(path: Path) -> tuple[int, bool, Counter[str]]:
    """返回 (总替换次数, 是否写回, 按标签计数)"""
    ctr: Counter[str] = Counter()
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return 0, False, ctr
    new_text = text
    total = 0
    for ch, lab in SPECIAL_SPACE_CHARS:
        n = new_text.count(ch)
        if n == 0:
            continue
        if ch in ZERO_WIDTH_REPLACE_EMPTY:
            new_text = new_text.replace(ch, "")
        else:
            new_text = new_text.replace(ch, SPACE)
        ctr[lab] += n
        total += n
    if total == 0:
        return 0, False, ctr
    path.write_text(new_text, encoding="utf-8")
    return total, True, ctr


def main() -> int:
    ap = argparse.ArgumentParser(description="探测 / 替换多种非常规 Unicode 空白")
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
        help="可视类→U+0020，零宽类→删除，并保存",
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
    print("探测码点: " + "、".join(lab for _, lab in SPECIAL_SPACE_CHARS))
    print("（不含 U+0020 半角空格）")
    print(f"替换: {'可视→U+0020，U+200B/U+FEFF→删除' if args.replace else '否（仅探测）'}\n")
    print("=" * 80)

    total_hits = 0
    total_files = 0
    global_ctr: Counter[str] = Counter()

    for fp in files:
        if args.replace:
            n, wrote, ctr = replace_in_file(fp)
            if n:
                total_hits += n
                total_files += 1
                global_ctr.update(ctr)
                try:
                    rel = fp.relative_to(root)
                except ValueError:
                    rel = fp
                detail = ", ".join(f"{k}:{v}" for k, v in sorted(ctr.items(), key=lambda x: -x[1]))
                print(f"\n✏️  {rel.as_posix()}  共 {n} 处 ({detail})")
        else:
            hits = probe_file(fp)
            if not hits:
                continue
            total_files += 1
            total_hits += len(hits)
            for _, _, lab, _ in hits:
                global_ctr[lab] += 1
            try:
                rel = fp.relative_to(root)
            except ValueError:
                rel = fp
            print(f"\n--- {rel.as_posix()} --- ({len(hits)} 处)")
            for line_no, col, lab, ctx in hits:
                print(f"  [{lab}] L{line_no}:{col}  {repr(ctx)}")

    print("\n" + "=" * 80)
    print(f"汇总: {total_hits} 处命中，涉及 {total_files} 个文件")
    if global_ctr:
        print("按类型: " + ", ".join(f"{k}: {v}" for k, v in global_ctr.most_common()))
    if args.replace and total_hits:
        print("已写回磁盘。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
