"""
探测 EPUB 中 stylesheet.css 定义的 class 在哪些 HTML 里出现过。

用法：
    python scripts/utils/epub/probe_css_classes.py [EPUB解压目录或.epub路径]

默认扫描 data/raw/mao 下的毛选解压目录。
输出：每个 CSS class 的出现文件列表及次数；未使用的 class 会标出。
"""
import re
import sys
from pathlib import Path

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


# ================= 配置 =================
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DEFAULT_DIR = PROJECT_ROOT / "data/raw/mao/毛泽东选集（1-7卷 静火版）V1.20 2019最新版"
# =======================================


def _find_stylesheet(base: Path) -> Path | None:
    """查找 stylesheet.css"""
    candidates = [
        base / "OEBPS" / "Styles" / "stylesheet.css",
        base / "Styles" / "stylesheet.css",
        base / "stylesheet.css",
    ]
    for p in candidates:
        if p.exists():
            return p
    for p in base.rglob("stylesheet.css"):
        return p
    return None


def _find_html_files(base: Path) -> list[Path]:
    """查找所有 HTML/XHTML 文件"""
    exts = {".html", ".htm", ".xhtml"}
    return sorted(p for p in base.rglob("*") if p.suffix.lower() in exts and p.is_file())


def _extract_css_classes(css_path: Path) -> dict[str, str]:
    """
    从 stylesheet.css 提取 class 名及注释。
    返回 {class_name: comment}
    """
    text = css_path.read_text(encoding="utf-8", errors="replace")
    result = {}
    lines = text.split("\n")
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("@"):
            continue
        for m in re.finditer(r"\.([a-zA-Z_][a-zA-Z0-9_-]*)\s*[\{,]", stripped):
            cls = m.group(1)
            if cls in result:
                continue
            # 注释通常在规则块内第一行 /* xxx */
            comment = ""
            for j in range(i + 1, min(i + 5, len(lines))):
                inner = lines[j].strip()
                cm = re.search(r"/\*\s*(.*?)\s*\*/", inner)
                if cm:
                    comment = cm.group(1).strip()
                    break
                if inner.startswith("}") or (inner and not inner.startswith("/*")):
                    break
            result[cls] = comment
    return result


def _extract_classes_from_html(html_path: Path) -> dict[str, int]:
    """从 HTML 文件提取 class 出现次数。返回 {class_name: count}"""
    text = html_path.read_text(encoding="utf-8", errors="replace")
    # 匹配 class="xxx" 或 class='xxx'，支持多 class: class="a b c"
    counts = {}
    for m in re.finditer(r'\bclass\s*=\s*["\']([^"\']+)["\']', text, re.I):
        for cls in m.group(1).split():
            cls = cls.strip()
            if cls:
                counts[cls] = counts.get(cls, 0) + 1
    return counts


def probe(base: Path):
    if not base.exists():
        print(f"❌ 目录不存在: {base}")
        return 1

    css_path = _find_stylesheet(base)
    if not css_path:
        print(f"❌ 未找到 stylesheet.css")
        return 1

    html_files = _find_html_files(base)
    if not html_files:
        print(f"❌ 未找到 HTML 文件")
        return 1

    css_classes = _extract_css_classes(css_path)
    # class -> [(rel_path, count), ...]
    usage: dict[str, list[tuple[str, int]]] = {cls: [] for cls in css_classes}

    for hp in html_files:
        try:
            counts = _extract_classes_from_html(hp)
        except Exception as e:
            print(f"⚠️ 读取失败 {hp}: {e}")
            continue
        rel = hp.relative_to(base) if base in hp.parents or hp.parent == base else hp.name
        rel_str = str(rel).replace("\\", "/")
        for cls, cnt in counts.items():
            if cls in usage:
                usage[cls].append((rel_str, cnt))

    # 输出
    print(f"📖 {base.name}")
    print(f"📄 CSS: {css_path.relative_to(base) if base in css_path.parents else css_path.name}")
    print(f"📄 HTML 文件: {len(html_files)} 个\n")
    print("=" * 70)
    print("【stylesheet.css 中 class 的出现位置】")
    print("=" * 70)

    for cls in sorted(css_classes.keys(), key=lambda x: (x.rstrip("0123456789"), x)):
        comment = css_classes.get(cls, "")
        items = usage.get(cls, [])
        total = sum(c for _, c in items)
        if not items:
            print(f"\n  .{cls}  （未使用）  /* {comment} */")
            continue
        print(f"\n  .{cls}  共 {total} 次  /* {comment} */")
        for rel, cnt in sorted(items, key=lambda x: -x[1])[:15]:
            print(f"      {rel}: {cnt}")
        if len(items) > 15:
            print(f"      ... 还有 {len(items) - 15} 个文件")

    unused = [c for c in css_classes if not usage.get(c)]
    if unused:
        print("\n" + "=" * 70)
        print(f"【未使用的 class】共 {len(unused)} 个: {', '.join('.' + c for c in sorted(unused))}")

    print()
    return 0


def main():
    if len(sys.argv) >= 2:
        base = Path(sys.argv[1])
    else:
        base = DEFAULT_DIR

    if base.suffix.lower() == ".epub":
        print("⚠️ 请传入解压后的目录，而非 .epub 文件")
        return 1

    return probe(base)


if __name__ == "__main__":
    sys.exit(main())
