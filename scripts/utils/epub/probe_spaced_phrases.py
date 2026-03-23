#!/usr/bin/env python3
"""
探测 EPUB 解压目录中「普通空格（U+0020）插在字与字之间」的固定词组：

  - 毛 泽 东
  - 周 恩 来
  - 彭 德 怀
  - 中 央
  - 林 彪
  - 朱 德

仅探测、不写回。空格可为 1 个或多个（\\s+ 仅匹配 ASCII 空白，含 U+0020 / \\t 等）。

用法：
    python probe_spaced_phrases.py
    python probe_spaced_phrases.py [解压根目录]
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

TEXT_SUFFIXES = {".xhtml", ".html", ".htm", ".ncx", ".opf", ".css", ".xml"}
CONTEXT = 32

# 仅「普通 ASCII 空白」插在指定汉字之间（不含全角空格、EM SPACE 等）
PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("毛 泽 东", re.compile(r"毛[ \t]+泽[ \t]+东")),
    ("周 恩 来", re.compile(r"周[ \t]+恩[ \t]+来")),
    ("彭 德 怀", re.compile(r"彭[ \t]+德[ \t]+怀")),
    ("中 央", re.compile(r"中[ \t]+央")),
    ("林 彪", re.compile(r"林[ \t]+彪")),
    ("朱 德", re.compile(r"朱[ \t]+德")),
]


def _iter_text_files(root: Path) -> list[Path]:
    out: list[Path] = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() in TEXT_SUFFIXES:
            out.append(p)
    return sorted(out)


def probe_file(path: Path) -> list[tuple[str, int, int, str]]:
    """[(标签, 行号, 列偏移, 上下文), ...]"""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        print(f"⚠️ 读取失败 {path}: {e}", flush=True)
        return []
    hits: list[tuple[str, int, int, str]] = []
    for line_no, line in enumerate(text.splitlines(), 1):
        for label, pat in PATTERNS:
            for m in pat.finditer(line):
                i = m.start()
                a = max(0, i - CONTEXT)
                b = min(len(line), m.end() + CONTEXT)
                ctx = line[a:b].replace("\n", "↵")
                hits.append((label, line_no, i, ctx))
    return hits


def main() -> int:
    ap = argparse.ArgumentParser(description="探测「毛 泽 东」等普通空格分隔词组")
    ap.add_argument(
        "root",
        nargs="?",
        type=Path,
        default=DEFAULT_ROOT,
        help="EPUB 解压根目录",
    )
    args = ap.parse_args()
    root = args.root.resolve()
    if not root.is_dir():
        print(f"❌ 不是目录: {root}", flush=True)
        return 1

    files = _iter_text_files(root)
    if not files:
        print(f"❌ 未找到可扫描文件", flush=True)
        return 1

    print(f"📖 {root}")
    print("探测：普通 ASCII 空白插在字间的固定词组\n")
    print("=" * 80)

    by_label: dict[str, int] = {lbl: 0 for lbl, _ in PATTERNS}
    total_hits = 0
    total_files = 0

    for fp in files:
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
        for label, line_no, col, ctx in sorted(hits, key=lambda x: (x[1], x[2], x[0])):
            by_label[label] += 1
            print(f"  [{label}] L{line_no}:{col}  {repr(ctx)}")

    print("\n" + "=" * 80)
    print(f"汇总: {total_hits} 处，涉及 {total_files} 个文件")
    for lbl, _ in PATTERNS:
        n = by_label.get(lbl, 0)
        if n:
            print(f"  {lbl}: {n}")
    if total_hits == 0:
        print("（未发现上述模式）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
