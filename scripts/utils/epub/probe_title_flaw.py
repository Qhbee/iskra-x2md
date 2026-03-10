#!/usr/bin/env python3
"""
探测毛选 EPUB 中 4 处标题是否一致、是否有首尾/中间空格、head title 是否含 HTML。
只打印探测结果，不修改任何文件。
"""

import html
import re
import sys
import warnings
from pathlib import Path

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)


def strip_clean(s: str) -> str:
    """去除首尾空格，并将中间连续空格压缩为单个"""
    return " ".join(s.split())


def decode_title_from_head(html_raw: str) -> str | None:
    """从 head 提取 <title> 内容，解码 HTML 实体得到纯文本（保留原始首尾空格用于检测）"""
    m = re.search(r"<title>([^<]*)</title>", html_raw, re.IGNORECASE | re.DOTALL)
    if not m:
        return None
    raw = m.group(1)
    decoded = html.unescape(raw)
    return decoded


def has_html_in_title(title: str) -> bool:
    """检测是否含有 <a class="zy" 等 HTML 片段（已解码或未解码）"""
    return bool(
        re.search(r"<a\s+class=\"zy\"", title, re.IGNORECASE)
        or "〔" in title
        and "〕" in title
        and ("<a" in title or "&lt;a" in title)
    )


def get_h3_title_attr(soup) -> str | None:
    """h3.head-mzd 的 title 属性（保留原始首尾空格用于检测）"""
    h3 = soup.find("h3", class_="head-mzd")
    if not h3:
        return None
    return h3.get("title")


def get_h3_inner_text(soup) -> str | None:
    """h3.head-mzd 的可见文本（br/sup 忽略继续取，遇到 b 日期则停止，保留原始首尾空格用于检测）"""
    h3 = soup.find("h3", class_="head-mzd")
    if not h3:
        return None
    parts = []
    for child in h3.children:
        if isinstance(child, str):
            parts.append(child)
        elif child.name in ("br", "sup"):
            continue
        elif child.name == "b":
            break
        else:
            parts.append(child.get_text())
    s = "".join(parts)
    return s if s.strip() else None


def build_toc_map(toc_path: Path) -> dict[str, str]:
    """toc.ncx 文件名 -> navLabel 文本（保留原始首尾空格用于检测）"""
    soup = BeautifulSoup(toc_path.read_text(encoding="utf-8"), "html.parser")
    m = {}
    for content in soup.find_all("content", src=True):
        src = content.get("src", "")
        if "OEBPS/Text/" in src:
            fname = src.split("OEBPS/Text/")[-1]
            nav_point = content.find_parent("navpoint") or content.find_parent("navPoint")
            if nav_point:
                nav_label = nav_point.find("navlabel") or nav_point.find("navLabel")
                if nav_label:
                    text_tag = nav_label.find("text")
                    if text_tag and text_tag.string is not None:
                        m[fname] = text_tag.string
    return m


def has_leading_trailing_space(s: str) -> bool:
    return s != s.strip()


def has_inner_extra_space(s: str) -> bool:
    """中间有连续空格"""
    return "  " in s


def probe(root: Path) -> None:
    text_dir = root / "OEBPS" / "Text"
    toc_path = root / "toc.ncx"
    if not text_dir.exists():
        print(f"错误：未找到 {text_dir}")
        return

    toc_map = build_toc_map(toc_path) if toc_path.exists() else {}

    issues = []
    for f in sorted(text_dir.glob("*.xhtml")):
        html_raw = f.read_text(encoding="utf-8")
        soup = BeautifulSoup(html_raw, "html.parser")

        head_title = decode_title_from_head(html_raw)
        h3_attr = get_h3_title_attr(soup)
        h3_text = get_h3_inner_text(soup)
        toc_title = toc_map.get(f.name)

        # 没有 h3.head-mzd 的跳过（如 portrait.xhtml）
        if h3_attr is None and h3_text is None:
            continue

        # 规范化比较：统一 strip + 中间空格压缩
        vals = [head_title, h3_attr, h3_text, toc_title]
        vals_clean = [strip_clean(v) if v else "" for v in vals]

        # 1. 四者不一致
        canonical = next((v for v in vals_clean if v), "")
        if canonical:
            has_inconsistent = False
            for i, (name, raw, clean) in enumerate(
                zip(
                    ["head_title", "h3_title_attr", "h3_inner_text", "toc_navLabel"],
                    vals,
                    vals_clean,
                )
            ):
                if clean and clean != canonical:
                    has_inconsistent = True
                if raw and has_leading_trailing_space(raw):
                    issues.append((f.name, "leading_trailing_space", name, raw))
                if raw and has_inner_extra_space(raw):
                    issues.append((f.name, "inner_extra_space", name, raw))
            if has_inconsistent:
                issues.append(
                    (
                        f.name,
                        "inconsistent",
                        None,
                        {
                            "head_title": head_title,
                            "h3_title_attr": h3_attr,
                            "h3_inner_text": h3_text,
                            "toc_navLabel": toc_title,
                        },
                    )
                )

        # 2. head title 含 HTML
        if head_title and has_html_in_title(head_title):
            issues.append((f.name, "head_has_html", None, head_title))

    # 按文件分组输出
    by_file = {}
    for item in issues:
        fname = item[0]
        kind = item[1]
        by_file.setdefault(fname, []).append(item)

    for fname in sorted(by_file):
        print(f"\n=== {fname} ===")
        for item in by_file[fname]:
            kind = item[1]
            if kind == "inconsistent":
                d = item[3]
                print("  [inconsistent] 4 处标题不一致:")
                for k, v in d.items():
                    v_repr = repr(v) if v else "(空)"
                    print(f"    {k}: {v_repr}")
            elif kind == "head_has_html":
                print(f"  [head_has_html] {repr(item[3])}")
            else:
                print(f"  [{kind}] {item[2]}: {repr(item[3])}")

    print(f"\n共 {len(issues)} 条问题，涉及 {len(by_file)} 个文件")


DEFAULT_ROOT = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "data"
    / "raw"
    / "mao"
    / "毛泽东选集全七卷（官方、静火、润之赤旗三合一版）"
)


def main():
    root = Path(sys.argv[1]).resolve() if len(sys.argv) >= 2 else DEFAULT_ROOT
    if not root.is_dir():
        print(f"错误：{root} 不是目录")
        sys.exit(1)
    print(f"探测目录: {root}")
    probe(root)


if __name__ == "__main__":
    main()