"""
探测 EPUB 中 item.get_content() 的返回内容，对比解压后的原始 HTML，排查信息丢失原因。

用法：
    python scripts/utils/epub/probe_get_content.py

可修改下方 INPUT_EPUB、EXTRACTED_DIR、LIMIT、DETAIL_LIMIT 配置。
- LIMIT=0：扫描全部 HTML 项；>0 则只处理前 N 项
- DETAIL_LIMIT：详细输出前 N 项，0 表示全部
"""
import re
import sys
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import ebooklib
from ebooklib import epub
from pathlib import Path

# ================= 配置 =================
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
INPUT_EPUB = PROJECT_ROOT / "data/raw/mao/毛泽东选集（1-7卷 静火版）V1.20 2019最新版.epub"

# 解压后的目录（若存在则对比原始 HTML）
EXTRACTED_DIR = PROJECT_ROOT / "data/raw/mao/毛泽东选集（1-7卷 静火版）V1.20 2019最新版"

# 扫描项数：0=全部，>0=只处理前 N 项
LIMIT = 0

# 详细输出项数：0=全部，>0=只对前 N 项打印完整对比
DETAIL_LIMIT = 5

# =======================================


def _read_extracted(href: str, base: Path) -> str | None:
    """从解压目录读取原始文件内容。href 如 Text/Cover.xhtml，解压后通常在 OEBPS/Text/"""
    href_clean = href.replace("\\", "/").lstrip("/")
    for full in [base / "OEBPS" / href_clean, base / href_clean]:
        if full.exists():
            return full.read_text(encoding="utf-8", errors="replace")
    return None


def _extract_sections(html: str) -> dict:
    """提取 DOCTYPE、html 属性、head、body 便于对比"""
    out = {}
    m = re.search(r"<!DOCTYPE[^>]*>", html, re.I | re.DOTALL)
    out["doctype"] = (m.group(0) if m else "").strip()
    m = re.search(r"<html([^>]*)>", html, re.I)
    out["html_attrs"] = (m.group(1) if m else "").strip()
    m = re.search(r"<head[^>]*>(.*?)</head>", html, re.I | re.DOTALL)
    out["head"] = (m.group(1) if m else "").strip()
    if "<head/>" in html or "<head />" in html:
        out["head"] = ""
    m = re.search(r"<body[^>]*>(.*?)</body>", html, re.I | re.DOTALL)
    out["body"] = (m.group(1) if m else "").strip()
    return out


def _normalize_ws(s: str) -> str:
    """合并空白、去除首尾，便于 body 对比"""
    return " ".join(s.split())


def probe():
    if not INPUT_EPUB.exists():
        print(f"❌ 找不到: {INPUT_EPUB}")
        return

    book = epub.read_epub(str(INPUT_EPUB))
    all_items = list(book.get_items_of_type(ebooklib.ITEM_DOCUMENT))
    items = all_items[:LIMIT] if LIMIT else all_items

    extracted_base = EXTRACTED_DIR if EXTRACTED_DIR.exists() else None

    print(f"📖 {INPUT_EPUB.name}")
    print(f"📄 共 {len(all_items)} 个 HTML 项，本次扫描 {len(items)} 个")
    if extracted_base:
        print(f"📂 解压目录: {extracted_base}\n")
    else:
        print("📂 未配置解压目录，仅显示 get_content()\n")

    # 第一轮：全量扫描，统计丢失信息
    stats = {"head_lost": 0, "doctype_changed": 0, "html_attrs_changed": 0, "body_diff": 0, "no_orig": 0}
    diffs = []

    for i, item in enumerate(items):
        href = item.file_name
        raw = item.get_content()
        text = raw.decode("utf-8", errors="replace")
        gc = _extract_sections(text)

        rec = {"i": i, "href": href, "gc": gc}
        if extracted_base:
            orig = _read_extracted(href, extracted_base)
            if not orig:
                stats["no_orig"] += 1
                rec["orig"] = None
            else:
                oc = _extract_sections(orig)
                rec["orig"] = oc
                if oc["head"] and not gc["head"]:
                    stats["head_lost"] += 1
                if oc["doctype"] and oc["doctype"] != gc["doctype"]:
                    stats["doctype_changed"] += 1
                if oc["html_attrs"] != gc["html_attrs"]:
                    stats["html_attrs_changed"] += 1
                if _normalize_ws(oc["body"]) != _normalize_ws(gc["body"]):
                    stats["body_diff"] += 1
        diffs.append(rec)

    # 输出统计
    print("=" * 70)
    print("【信息丢失统计】")
    print("=" * 70)
    if extracted_base:
        print(f"  head 丢失（原始有 <title>/<link>/<style>，get_content 为空）: {stats['head_lost']} / {len(items)}")
        print(f"  DOCTYPE 被简化: {stats['doctype_changed']} / {len(items)}")
        print(f"  html 属性被改（如 lang=\"zh-CN\" → lang=\"en\"）: {stats['html_attrs_changed']} / {len(items)}")
        print(f"  body 内容有差异（忽略空白）: {stats['body_diff']} / {len(items)}")
        print(f"  解压目录中未找到: {stats['no_orig']}")
    print()

    # 详细输出前 DETAIL_LIMIT 项
    detail_count = len(diffs) if not DETAIL_LIMIT else min(DETAIL_LIMIT, len(diffs))
    print("=" * 70)
    print(f"【详细对比】前 {detail_count} 项")
    print("=" * 70)

    for rec in diffs[:detail_count]:
        i, href, gc = rec["i"], rec["href"], rec["gc"]
        print(f"\n[{i}] {href}")
        print(f"    get_content() len = {sum(len(v) for v in gc.values())} (approx)")

        print("\n  --- get_content() 返回 ---")
        print(f"  DOCTYPE: {gc['doctype'][:80] or '(空)'}...")
        print(f"  html 属性: {gc['html_attrs'][:120] or '(空)'}...")
        print(f"  head: {gc['head'][:200] or '(空)'}...")
        print(f"  body 前 150 字符: {gc['body'][:150]}...")

        if rec.get("orig"):
            oc = rec["orig"]
            print("\n  --- 解压后原始文件 ---")
            print(f"  DOCTYPE: {oc['doctype'][:80] or '(空)'}...")
            print(f"  html 属性: {oc['html_attrs'][:120] or '(空)'}...")
            print(f"  head: {oc['head'][:200] or '(空)'}...")
            lost = []
            if oc["head"] and not gc["head"]:
                lost.append("head")
            if oc["doctype"] != gc["doctype"]:
                lost.append("DOCTYPE")
            if oc["html_attrs"] != gc["html_attrs"]:
                lost.append("html 属性")
            if _normalize_ws(oc["body"]) != _normalize_ws(gc["body"]):
                lost.append("body")
            if lost:
                print(f"\n  ⚠️ 丢失/变更: {', '.join(lost)}")

    if len(diffs) > detail_count:
        print(f"\n... 其余 {len(diffs) - detail_count} 项未详细输出（可调大 DETAIL_LIMIT）")

    print("\n" + "=" * 70)
    print("说明：ebooklib 解析 EPUB 时会对 HTML 做转换，常见丢失：<head> 整块、DOCTYPE、xml:lang 等。")


if __name__ == "__main__":
    probe()
