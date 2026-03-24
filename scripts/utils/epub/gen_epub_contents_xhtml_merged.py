#!/usr/bin/env python3
"""
从三合一 EPUB 的 toc.ncx 生成 OEBPS/Text/Contents.xhtml（静火版 Contents 式层级链接）。

前置固定四条：封面、扉页、肖像、目录（目录为 Contents.xhtml 自链）。
在正文流中插入位置由 WRITE_INTO_OPF 控制：默认插在 portrait 之后、Volume01 之前。
不修改 gen_toc_from_output_mao_merged.py（那是 Markdown 侧）。

用法:
    python gen_epub_contents_xhtml_merged.py              # 写 Contents.xhtml + 可选改 opf
顶部常量 WRITE_INTO_OPF = False 时只生成 xhtml，不碰 content.opf。
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

if sys.platform == "win32":
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

NS = {"n": "http://www.daisy.org/z3986/2005/ncx/"}

EPUB_ROOT = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "data/raw/mao/毛泽东选集全七卷（官方、静火、润之赤旗三合一版）"
)
NCX_PATH = EPUB_ROOT / "toc.ncx"
OUT_XHTML = EPUB_ROOT / "OEBPS/Text/Contents.xhtml"
OPF_PATH = EPUB_ROOT / "content.opf"

# True：在 content.opf 的 manifest 注册 Contents，并插入 spine（portrait 后）
WRITE_INTO_OPF = True


def _tag(local: str) -> str:
    return f"{{{NS['n']}}}{local}"


def _src_to_href(src: str) -> str:
    if not src:
        return "#"
    s = src.strip().replace("\\", "/")
    if s.startswith("OEBPS/Text/"):
        return s[len("OEBPS/Text/") :]
    if s == "titlepage.xhtml":
        return "../../titlepage.xhtml"
    return s.split("/")[-1]


def _toc_class(depth: int) -> str:
    if depth <= 0:
        return "toc1"
    if depth == 1:
        return "toc2"
    return "toc3"


def _emit_line(title: str, href: str, depth: int, *, vol: bool = False) -> str:
    esc_t = (
        title.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
    cls = _toc_class(depth)
    a_cls = "contents-a vol-link" if vol else "contents-a"
    return f'    <p class="{cls}"><a class="{a_cls}" href="{href}">{esc_t}</a></p>'


def _lines_from_ncx(ncx_path: Path) -> list[str]:
    tree = ET.parse(ncx_path)
    root = tree.getroot()
    nav_map = root.find("n:navMap", NS)
    if nav_map is None:
        raise SystemExit("navMap not found in toc.ncx")

    lines: list[str] = []

    lines.append(_emit_line("封面", _src_to_href("titlepage.xhtml"), 1))
    lines.append(_emit_line("扉页", "Epigraph.xhtml", 1))
    lines.append(_emit_line("肖像", "portrait.xhtml", 1))
    # 本页自链，便于从目录页内跳转/书签（与静火纸质目录中「目录」条类似）
    lines.append(_emit_line("目录", "Contents.xhtml", 1))

    def walk(np: ET.Element, depth: int) -> None:
        label_el = np.find("n:navLabel/n:text", NS)
        content_el = np.find("n:content", NS)
        title = (label_el.text or "").strip() if label_el is not None else ""
        src = content_el.get("src", "").strip() if content_el is not None else ""
        if depth == 0 and src.endswith("Epigraph.xhtml"):
            title, src = "", ""
        if title and src:
            href = _src_to_href(src)
            vol = depth == 0 and "卷" in title
            lines.append(_emit_line(title, href, depth, vol=vol))
        for child in np:
            if child.tag == _tag("navPoint"):
                walk(child, depth + 1)

    for child in nav_map:
        if child.tag == _tag("navPoint"):
            walk(child, 0)

    return lines


def _build_xhtml(body_lines: list[str]) -> str:
    lines_joined = "\n".join(body_lines)
    return f"""<?xml version='1.0' encoding='utf-8'?>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="zh-CN">
  <head>
    <title>目录</title>
    <meta http-equiv="Content-Type" content="text/html; charset=utf-8"/>
  <link rel="stylesheet" type="text/css" href="../../stylesheet.css"/>
<link rel="stylesheet" type="text/css" href="../../page_styles.css"/>
</head>
  <body class="calibre contents-root">
  <div class="contents-div">
    <h1 class="contents-title"><span class="contents-title-span">目　录</span></h1>

{lines_joined}

  </div>
</body>
</html>
"""


def _patch_opf(opf_text: str) -> str:
    if 'id="Contents.xhtml"' in opf_text:
        manifest_done = True
    else:
        manifest_done = False
    if '<itemref idref="Contents.xhtml"/>' in opf_text:
        spine_done = True
    else:
        spine_done = False

    if not manifest_done:
        needle = '<item id="portrait.xhtml"'
        insert = (
            '    <item id="Contents.xhtml" href="OEBPS/Text/Contents.xhtml" '
            'media-type="application/xhtml+xml"/>\n    <item id="portrait.xhtml"'
        )
        if needle not in opf_text:
            raise SystemExit("content.opf: manifest anchor portrait.xhtml not found")
        opf_text = opf_text.replace(needle, insert, 1)

    if not spine_done:
        needle = '<itemref idref="portrait.xhtml"/>'
        insert = (
            '<itemref idref="portrait.xhtml"/>\n    <itemref idref="Contents.xhtml"/>'
        )
        if needle not in opf_text:
            raise SystemExit("content.opf: spine portrait anchor not found")
        opf_text = opf_text.replace(needle, insert, 1)

    if 'type="toc"' not in opf_text or "Contents.xhtml" not in opf_text.split("<guide>", 1)[-1]:
        if "<guide>" in opf_text:
            opf_text = opf_text.replace(
                "<guide>",
                '<guide>\n    <reference type="toc" href="OEBPS/Text/Contents.xhtml" title="目录"/>',
                1,
            )
    return opf_text


def main() -> int:
    if not NCX_PATH.is_file():
        print(f"❌ 缺少 {NCX_PATH}", flush=True)
        return 1
    body = _lines_from_ncx(NCX_PATH)
    xhtml = _build_xhtml(body)
    OUT_XHTML.parent.mkdir(parents=True, exist_ok=True)
    OUT_XHTML.write_text(xhtml, encoding="utf-8")
    print(f"✅ 已写 {OUT_XHTML}（{len(body)} 条链接）", flush=True)

    if WRITE_INTO_OPF:
        opf = OPF_PATH.read_text(encoding="utf-8")
        new_opf = _patch_opf(opf)
        if new_opf != opf:
            OPF_PATH.write_text(new_opf, encoding="utf-8")
            print(f"✅ 已更新 {OPF_PATH}（manifest / spine / guide）", flush=True)
        else:
            print(f"ℹ️ {OPF_PATH} 无需变更（可能已写入）", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
