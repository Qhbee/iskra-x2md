# -*- coding: utf-8 -*-
"""
验证脚本：检查马恩全集 PDF 书签中，是否有含「索引」但不是已知类型的标题。

已知类型：人名索引、期刊索引、地名索引、著作索引、文献索引
"""
import sys
from pathlib import Path

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import fitz

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
INPUT_DIR = PROJECT_ROOT / "data/raw/marx-engels/马克思恩格斯全集-文字版-带书签"

KNOWN_INDEX = frozenset(["人名索引", "期刊索引", "地名索引", "著作索引", "文献索引"])


def sanitize(text: str) -> str:
    """移除 surrogate 字符"""
    return "".join(c for c in text if not ("\ud800" <= c <= "\udfff"))


def main():
    if not INPUT_DIR.exists():
        print(f"❌ 目录不存在: {INPUT_DIR}")
        return

    pdfs = sorted(INPUT_DIR.glob("*.pdf"))
    if not pdfs:
        print(f"❌ 无 PDF 文件")
        return

    found_other = []  # (pdf_name, title)

    for pdf_path in pdfs:
        try:
            doc = fitz.open(pdf_path)
        except Exception as e:
            print(f"⚠️ 无法打开 {pdf_path.name}: {e}")
            continue

        toc = doc.get_toc()
        for item in toc:
            lvl, title, _ = item[0], sanitize(item[1]).strip(), item[2]
            if "索引" not in title:
                continue
            if title in KNOWN_INDEX:
                continue
            found_other.append((pdf_path.name, title))

        doc.close()

    # 去重并按 PDF 分组输出
    if not found_other:
        print("✅ 未发现含「索引」但非已知类型的书签。")
        return

    seen = set()
    by_pdf = {}
    for pdf_name, title in found_other:
        key = (pdf_name, title)
        if key in seen:
            continue
        seen.add(key)
        by_pdf.setdefault(pdf_name, []).append(title)

    print(f"📋 发现 {len(seen)} 个非常见索引书签：\n")
    for pdf_name in sorted(by_pdf.keys()):
        titles = by_pdf[pdf_name]
        print(f"  {pdf_name}")
        for t in titles:
            print(f"    └ {t}")
        print()


if __name__ == "__main__":
    main()
