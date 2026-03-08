"""
搜索 toc.ncx 和 xhtml 标题中的冗余空格。

检测：连续多个空格、首尾空格、制表符、连续全角空格。
"""
import re
import sys
from pathlib import Path

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from bs4 import BeautifulSoup


# ================= 配置 =================
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
BASE_DIR = PROJECT_ROOT / "data/raw/mao/毛泽东选集（1-7卷 静火版）V1.20 2019最新版"
# =======================================


# 冗余模式：(名称, 正则)
REDUNDANT_PATTERNS = [
    ("连续半角空格(2+)", re.compile(r" {2,}")),
    ("连续全角空格(2+)", re.compile(r"　{2,}")),
    ("首部空格", re.compile(r"^[ \t　]+")),
    ("尾部空格", re.compile(r"[ \t　]+$")),
    ("制表符", re.compile(r"\t")),
]


def _check_text(text: str) -> list[tuple[str, str]]:
    """返回 [(问题类型, 匹配片段), ...]"""
    issues = []
    for name, pat in REDUNDANT_PATTERNS:
        for m in pat.finditer(text):
            issues.append((name, repr(m.group())))
    return issues


def _probe_toc_ncx(path: Path) -> list[tuple[str, int, str, list]]:
    """返回 [(位置描述, 行号, 原文, issues), ...]"""
    results = []
    text = path.read_text(encoding="utf-8", errors="replace")
    for m in re.finditer(r"<text>([^<]*)</text>", text):
        content = m.group(1)
        issues = _check_text(content)
        if not issues:
            continue
        line_no = text[: m.start()].count("\n") + 1
        results.append((f"toc.ncx <text>", line_no, content, issues))
    return results


def _probe_xhtml_titles(path: Path) -> list[tuple[str, int, str, list]]:
    """仅检测总文章标题：<title> 和 h1/h2/h3（不含 h4/h5/h6 文内小标题）"""
    results = []
    raw = path.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(raw, "html.parser")

    # <title>
    title_tag = soup.find("title")
    if title_tag:
        content = title_tag.get_text(strip=False)
        issues = _check_text(content)
        if issues:
            line_no = raw[: raw.find("<title>")].count("\n") + 1
            results.append((f"{path.name} <title>", line_no, content, issues))

    # h1/h2/h3 总标题（不含 h4/h5/h6 文内小标题）
    for tag in soup.find_all(["h1", "h2", "h3"]):
        content = tag.get_text(separator=" ", strip=False)
        issues = _check_text(content)
        if not issues:
            continue
        try:
            line_no = raw[: raw.find(str(tag)[:50])].count("\n") + 1
        except Exception:
            line_no = 0
        results.append((f"{path.name} <{tag.name}>", line_no, content, issues))

    return results


def main():
    if not BASE_DIR.exists():
        print(f"❌ 目录不存在: {BASE_DIR}")
        return 1

    toc_path = BASE_DIR / "OEBPS" / "toc.ncx"
    text_dir = BASE_DIR / "OEBPS" / "Text"

    print(f"📖 {BASE_DIR.name}")
    print("🔍 冗余空格检测：toc.ncx + xhtml 标题\n")
    print("=" * 70)

    total = 0

    # toc.ncx
    if toc_path.exists():
        for loc, line_no, content, issues in _probe_toc_ncx(toc_path):
            total += 1
            print(f"\n  {loc}  L{line_no}")
            print(f"    原文: {repr(content)}")
            for name, frag in issues:
                print(f"    → {name}: {frag}")

    # xhtml
    if text_dir.exists():
        for xpath in sorted(text_dir.glob("*.xhtml")):
            for loc, line_no, content, issues in _probe_xhtml_titles(xpath):
                total += 1
                print(f"\n  {loc}  L{line_no}")
                print(f"    原文: {repr(content)}")
                for name, frag in issues:
                    print(f"    → {name}: {frag}")

    print("\n" + "=" * 70)
    print(f"共 {total} 处")
    return 0


if __name__ == "__main__":
    sys.exit(main())
