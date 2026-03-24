#!/usr/bin/env python3
"""
探测处理后 Markdown 中「疑似表格被误解析为块引用」的片段：

  特征：连续 ≥N 行均以 `>` 开头（Markdown blockquote），常见于表格单元格被逐行写成 `>` 行。

仅探测、不写回。

用法：
    python probe_suspect_table_blockquotes.py
    python probe_suspect_table_blockquotes.py [Markdown 根目录或单个 .md 文件]
    python probe_suspect_table_blockquotes.py --min 8 [路径]
"""

from __future__ import annotations

import argparse
import io
import sys
from dataclasses import dataclass
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DEFAULT_ROOT = (
    PROJECT_ROOT
    / "data/processed/lenin"
    / "列宁全集（版本II-文字版）（完整书签版）"
)

PREVIEW_LINES = 5
PREVIEW_CHARS = 120


def _is_blockquote_line(line: str) -> bool:
    """是否为块引用行（行首可选空白后紧跟 >）。"""
    return line.lstrip().startswith(">")


def _toggle_fence(line: str, inside: bool) -> bool:
    s = line.strip()
    if s.startswith("```"):
        return not inside
    return inside


@dataclass(frozen=True)
class SuspectRun:
    start_line: int
    end_line: int
    length: int


def probe_text(text: str, min_consecutive: int) -> list[SuspectRun]:
    lines = text.splitlines()
    runs: list[SuspectRun] = []
    in_fence = False
    run_start: int | None = None
    run_len = 0

    for i, line in enumerate(lines, start=1):
        in_fence = _toggle_fence(line, in_fence)
        if in_fence:
            if run_len >= min_consecutive and run_start is not None:
                runs.append(SuspectRun(run_start, i - 1, run_len))
            run_start = None
            run_len = 0
            continue

        if _is_blockquote_line(line):
            if run_start is None:
                run_start = i
            run_len += 1
        else:
            if run_len >= min_consecutive and run_start is not None:
                runs.append(SuspectRun(run_start, i - 1, run_len))
            run_start = None
            run_len = 0

    if run_len >= min_consecutive and run_start is not None:
        runs.append(SuspectRun(run_start, len(lines), run_len))

    return runs


def _preview_block(lines: list[str], start_idx: int, n: int) -> list[str]:
    out: list[str] = []
    for j in range(start_idx, min(start_idx + n, len(lines))):
        raw = lines[j]
        trimmed = raw.strip()
        if len(trimmed) > PREVIEW_CHARS:
            trimmed = trimmed[:PREVIEW_CHARS] + "…"
        out.append(trimmed)
    return out


def _iter_md_paths(root: Path) -> list[Path]:
    if root.is_file():
        if root.suffix.lower() == ".md":
            return [root]
        print(f"❌ 不是 .md 文件: {root}", flush=True)
        return []
    out: list[Path] = []
    for p in root.rglob("*.md"):
        if p.is_file():
            out.append(p)
    return sorted(out)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="探测连续多行 `>` 块引用（疑似表格解析错误）",
    )
    ap.add_argument(
        "root",
        nargs="?",
        type=Path,
        default=DEFAULT_ROOT,
        help="Markdown 根目录或单个 .md 文件",
    )
    ap.add_argument(
        "--min",
        type=int,
        default=5,
        metavar="N",
        help="连续块引用行数阈值（默认 5）",
    )
    args = ap.parse_args()
    root = args.root.resolve()
    min_n = args.min
    if min_n < 2:
        print("❌ --min 至少为 2", flush=True)
        return 1

    if root.is_dir() and not root.exists():
        print(f"❌ 路径不存在: {root}", flush=True)
        return 1
    if root.is_file() and not root.exists():
        print(f"❌ 文件不存在: {root}", flush=True)
        return 1

    paths = _iter_md_paths(root)
    if not paths:
        if root.is_dir():
            print(f"❌ 未找到 .md: {root}", flush=True)
        return 1

    print(f"📖 扫描: {root}")
    print(f"规则: 连续 ≥{min_n} 行块引用（代码围栏 ``` 内忽略）\n")
    print("=" * 80)

    total_runs = 0
    files_with_hits = 0

    for fp in paths:
        try:
            text = fp.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            print(f"⚠️ 读取失败 {fp}: {e}", flush=True)
            continue
        lines = text.splitlines()
        runs = probe_text(text, min_n)
        if not runs:
            continue
        files_with_hits += 1
        total_runs += len(runs)
        try:
            rel = fp.relative_to(PROJECT_ROOT)
        except ValueError:
            rel = fp
        print(f"\n--- {rel.as_posix()} --- ({len(runs)} 段)")
        for r in runs:
            print(f"  L{r.start_line}–L{r.end_line}  ({r.length} 行)")
            prev = _preview_block(lines, r.start_line - 1, PREVIEW_LINES)
            for k, pv in enumerate(prev, start=1):
                print(f"    +{k}: {pv}")

    print("\n" + "=" * 80)
    print(f"汇总: {total_runs} 段疑似问题，涉及 {files_with_hits} 个文件")
    if total_runs == 0:
        print("（未发现满足条件的连续块引用）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
