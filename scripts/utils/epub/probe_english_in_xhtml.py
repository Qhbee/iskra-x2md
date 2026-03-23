"""
探测 EPUB 解压目录下 XHTML/HTML 中出现的拉丁字母英文片段（不含标签内文本）。

- 使用 BeautifulSoup 抽取可见文本，已排除 <script>/<style>/<head>。
- 不匹配纯标点；匹配缩写（如 H.C.）、带连字符/撇号的词、普通英文单词（≥2 字母）。
- 输出：相对路径、逻辑行号、匹配串、前后上下文。
- 「逻辑行」= 去掉标签后 `get_text(separator='\\n')` 再按换行切分，与 XHTML 源文件物理行号不一定一致。

用法：
    python probe_english_in_xhtml.py [EPUB解压根目录]
    python probe_english_in_xhtml.py --oebps-text   # 只扫 OEBPS/Text（正文）
    默认目录为项目内三合一毛选路径（见 DEFAULT_DIR）。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

if sys.platform == "win32":
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("需要 beautifulsoup4: pip install beautifulsoup4")
    sys.exit(1)

# ================= 配置 =================
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DEFAULT_DIR = (
    PROJECT_ROOT
    / "data/raw/mao/毛泽东选集全七卷（官方、静火、润之赤旗三合一版）"
)
CONTEXT_CHARS = 24
# 拉丁字母英文：缩写点号、撇号/连字符词、普通词（不含 HTML，已在上游去掉标签）
_ENGLISH_RE = re.compile(
    r"(?<![A-Za-z])(?:"
    r"(?:[A-Z]\.){2,}[A-Z]?"  # H.C.  U.S.A.
    r"|[A-Za-z]+(?:'[A-Za-z]+)+"  # 少见的多段撇号
    r"|[A-Za-z]+'[A-Za-z]+"  # don't 等
    r"|[A-Za-z]+(?:-[A-Za-z]+)+"  # well-known
    r"|[A-Za-z]{2,}"
    r")(?![A-Za-z])"
)


def _find_html_files(base: Path, *, oebps_text_only: bool) -> list[Path]:
    exts = {".html", ".htm", ".xhtml"}
    if oebps_text_only:
        sub = base / "OEBPS" / "Text"
        if not sub.is_dir():
            return []
        return sorted(p for p in sub.iterdir() if p.suffix.lower() in exts and p.is_file())
    return sorted(p for p in base.rglob("*") if p.suffix.lower() in exts and p.is_file())


def _visible_text_lines(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "head"]):
        tag.decompose()
    raw = soup.get_text(separator="\n")
    return raw.splitlines()


def _context(line: str, start: int, end: int, width: int = CONTEXT_CHARS) -> str:
    a = max(0, start - width)
    b = min(len(line), end + width)
    left = line[a:start]
    mid = line[start:end]
    right = line[end:b]
    return f"…{left}【{mid}】{right}…"


def probe(base: Path, *, oebps_text_only: bool) -> int:
    if not base.exists():
        print(f"❌ 目录不存在: {base}")
        return 1

    files = _find_html_files(base, oebps_text_only=oebps_text_only)
    if not files:
        print("❌ 未找到 HTML/XHTML 文件")
        return 1

    print(f"📖 根目录: {base}")
    print(f"🔍 匹配拉丁字母英文片段（标签与标签内属性不计）\n")
    print("=" * 88)

    total = 0
    for hp in files:
        try:
            text = hp.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            print(f"⚠️ 读取失败 {hp}: {e}")
            continue

        try:
            lines = _visible_text_lines(text)
        except Exception as e:
            print(f"⚠️ 解析失败 {hp}: {e}")
            continue

        rel = hp.relative_to(base) if base in hp.parents else hp
        rel_str = str(rel).replace("\\", "/")
        file_hits = 0

        for line_no, line in enumerate(lines, 1):
            if not line.strip():
                continue
            for m in _ENGLISH_RE.finditer(line):
                if file_hits == 0:
                    print(f"\n--- {rel_str} ---")
                file_hits += 1
                total += 1
                ctx = _context(line, m.start(), m.end())
                print(f"  {line_no:5d}  {m.group()!r:32s}  {ctx}")

    print("\n" + "=" * 88)
    print(f"共 {total} 处英文片段，涉及 {base.name} 下 XHTML/HTML")
    return 0 if total else 0


def main() -> int:
    p = argparse.ArgumentParser(description="探测 EPUB 解压目录 XHTML 中的英文片段")
    p.add_argument(
        "dir",
        nargs="?",
        type=Path,
        default=DEFAULT_DIR,
        help=f"EPUB 解压根目录（默认：{DEFAULT_DIR}）",
    )
    p.add_argument(
        "--oebps-text",
        action="store_true",
        help="只扫描 OEBPS/Text 下正文 xhtml（更快）",
    )
    args = p.parse_args()
    return probe(args.dir.resolve(), oebps_text_only=args.oebps_text)


if __name__ == "__main__":
    raise SystemExit(main())
