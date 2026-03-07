"""
方案 B：转换完成后，扫描输出目录，根据实际目录结构生成目录 MD。
不依赖 epub toc，夹逼/漏掉/后加的文章都能正确反映。
用法: python gen_toc_from_output.py [输出目录]
"""

import os
import re
import sys
import yaml
from pathlib import Path

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def _natural_sort_key(s: str):
    """自然排序：01. 在 02. 前，01. 在 10. 前"""
    return [int(x) if x.isdigit() else x.lower() for x in re.split(r"(\d+)", s)]


def _collect_articles(root: Path, base: Path) -> list[tuple[Path, str, int]]:
    """
    递归收集所有 index.md，返回 [(article_dir, title, level), ...] 按路径自然排序。
    level = 相对 base 的深度（base 下直接子目录为 0）。
    """
    result = []
    for d in sorted(root.iterdir(), key=lambda p: _natural_sort_key(p.name)):
        if not d.is_dir():
            continue
        idx = d / "index.md"
        if not idx.exists():
            continue
        try:
            raw = idx.read_text(encoding="utf-8")
            if raw.startswith("---"):
                parts = raw.split("---", 2)
                fm = yaml.safe_load(parts[1].strip()) or {} if len(parts) >= 2 else {}
            else:
                fm = {}
            title = fm.get("title") or d.name
        except Exception:
            title = d.name
        depth = len(d.relative_to(base).parts)
        level = depth - 1  # base 直接子目录 level=0
        result.append((d, title, level))
        result.extend(_collect_articles(d, base))
    return result


def _find_contents_dir(root: Path) -> Path | None:
    """找到 title 为「目录」的 index.md 所在目录"""
    for d in root.rglob("*"):
        if not d.is_dir():
            continue
        idx = d / "index.md"
        if not idx.exists():
            continue
        try:
            raw = idx.read_text(encoding="utf-8")
            if not raw.startswith("---"):
                continue
            parts = raw.split("---", 2)
            fm = yaml.safe_load(parts[1].strip()) or {} if len(parts) >= 2 else {}
            if fm.get("title") == "目录":
                return d
        except Exception:
            continue
    return None


def main():
    if len(sys.argv) >= 2:
        output_dir = Path(sys.argv[1])
    else:
        output_dir = Path(__file__).resolve().parent.parent.parent.parent / "data/processed/mao/毛泽东选集（1-7卷 静火版）V1.20 2019最新版"

    if not output_dir.exists():
        print(f"❌ 目录不存在: {output_dir}")
        return 1

    contents_dir = _find_contents_dir(output_dir)
    if not contents_dir:
        print("❌ 未找到 title=目录 的 index.md")
        return 1

    articles = _collect_articles(output_dir, output_dir)
    # # 排除目录页自身
    # articles = [(d, t, lv) for d, t, lv in articles if d != contents_dir]

    lines = ["# 目　录", ""]
    for art_dir, title, level in articles:
        rel_raw = Path(os.path.relpath(str(art_dir / "index.md"), str(contents_dir))).as_posix()
        rel_str = rel_raw.replace(" ", "%20")
        indent = "  " * level
        lines.append(f"{indent}- [{title}]({rel_str})")

    body = "\n".join(lines)
    idx_path = contents_dir / "index.md"
    try:
        raw = idx_path.read_text(encoding="utf-8")
        if raw.startswith("---"):
            parts = raw.split("---", 2)
            fm = yaml.safe_load(parts[1].strip()) or {}
        else:
            fm = {}
    except Exception:
        fm = {}
    fm.setdefault("title", "目录")
    front_matter = yaml.dump(fm, allow_unicode=True)
    final = f"---\n{front_matter}---\n\n{body}"
    idx_path.write_text(final, encoding="utf-8")
    print(f"📋 已生成目录: {idx_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
