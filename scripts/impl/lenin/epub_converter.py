"""
EPUB 转 Markdown：按 spine 顺序逐 HTML 转换，输出 Page Bundles（index.md + assets/）。
与 pdf_converter_custom 输出格式一致。
"""

import sys
import ebooklib
import yaml
from pathlib import Path

from ebooklib import epub

from epub_html_parser import clean_filename, parse_html_to_markdown

# ==================== 仪表盘配置 ====================

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
INPUT_EPUB = PROJECT_ROOT / "data/raw/lenin/列宁全集.epub"
OUTPUT_DIR = PROJECT_ROOT / "data/processed/lenin"

# True = 侦察模式（只看 spine 结构）
# False = 执行模式（生成 Markdown）
DRY_RUN = False


# ==================== 转换逻辑 ====================

def _get_book_title(book) -> str:
    """从 metadata 提取书名"""
    titles = book.get_metadata("DC", "title")
    if titles and titles[0]:
        return titles[0][0].strip() or "unknown"
    return "unknown"


def _resolve_item(book, spine_entry):
    """
    从 spine 条目解析出 EpubItem。
    spine 条目可能是 (id, 'linear'|'no') 或直接是 item。
    """
    if hasattr(spine_entry, "get_content"):
        return spine_entry
    if isinstance(spine_entry, (list, tuple)):
        sid = spine_entry[0]
    else:
        sid = spine_entry
    return book.get_item_with_id(sid)


def _get_item_href(item) -> str:
    """获取 item 的 href/file_name，用于解析相对路径"""
    return getattr(item, "file_name", None) or item.get_name() or ""


def _build_get_item_fn(book):
    """构建 get_item 函数，支持多种 href 格式"""

    def get_item(href: str):
        item = book.get_item_with_href(href)
        if item is not None:
            return item
        # 尝试去掉前导 ./
        if href.startswith("./"):
            return book.get_item_with_href(href[2:])
        # 尝试不同的路径变体
        for alt in [href, href.lstrip("/"), "OEBPS/" + href, href.replace("\\", "/")]:
            item = book.get_item_with_href(alt)
            if item is not None:
                return item
        return None

    return get_item


def _extract_nav_hierarchy(book) -> dict:
    """
    从 toc 构建 href -> (title, category_path) 映射。
    toc 结构：Link(href, title)、Section(title, href)、(Section, [Link|Item|(Section,children)])
    """
    href_map = {}

    def walk(toc_entries, prefix: list):
        for entry in toc_entries or []:
            if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                section, children = entry[0], entry[1]
                sect_title = getattr(section, "title", str(section))
                walk(children, prefix + [clean_filename(str(sect_title))])
                continue
            # Link: href, title
            if hasattr(entry, "href") and hasattr(entry, "title"):
                href = (entry.href or "").split("#")[0].strip()
                title = entry.title or "未命名"
                if href:
                    href_map[href] = (str(title), "/".join(prefix))
                continue
            # EpubHtml/Item: file_name, title
            if hasattr(entry, "get_name"):
                href = (entry.get_name() or "").split("#")[0].strip()
                title = getattr(entry, "title", None) or "未命名"
                if href:
                    href_map[href] = (str(title), "/".join(prefix))

    if isinstance(book.toc, (list, tuple)):
        walk(book.toc, [])
    return href_map


def main():
    print(f"📖 读取: {INPUT_EPUB.name}")
    if not INPUT_EPUB.exists():
        print(f"❌ 文件不存在: {INPUT_EPUB}")
        return

    try:
        book = epub.read_epub(str(INPUT_EPUB))
    except Exception as e:
        print(f"❌ 无法打开: {e}")
        return

    book_title = _get_book_title(book)
    book_stem = clean_filename(book_title)
    get_item_fn = _build_get_item_fn(book)
    nav_map = _extract_nav_hierarchy(book)

    # 收集 spine 中的 HTML 文档
    spine_docs = []
    for i, entry in enumerate(book.spine):
        item = _resolve_item(book, entry)
        if item is None:
            continue
        if item.get_type() != ebooklib.ITEM_DOCUMENT:
            continue
        href = _get_item_href(item)
        if not href or not href.lower().endswith((".html", ".xhtml", ".htm")):
            continue
        title = getattr(item, "title", None) or ""
        if not title and href in nav_map:
            title = nav_map[href][0]
        if not title:
            title = Path(href).stem or f"章节_{i + 1}"
        cat_info = nav_map.get(href, (title, ""))
        category = cat_info[1] or book_stem
        spine_docs.append({
            "item": item,
            "href": href,
            "title": title,
            "category": category,
            "order": i + 1,
        })

    print(f"🔍 有效章节: {len(spine_docs)} 个\n")

    if DRY_RUN:
        for d in spine_docs:
            print(f"  📄 {d['title']} (order={d['order']}, category={d['category']})")
        print("\n📢 --- 侦察结束 ---")
        print("请检查上面的输出，确认后将 DRY_RUN 改为 False 执行。")
        return

    output_base = Path(OUTPUT_DIR)
    output_base.mkdir(parents=True, exist_ok=True)

    for d in spine_docs:
        item = d["item"]
        href = d["href"]
        title = d["title"]
        category = d["category"]
        order = d["order"]

        # 计算 Page Bundle 路径：output_base / category / safe_title
        safe_title = clean_filename(title)
        cat_parts = [p for p in category.split("/") if p]
        if cat_parts:
            parent = output_base
            for part in cat_parts:
                parent = parent / part
            article_dir = parent / safe_title
        else:
            article_dir = output_base / safe_title

        article_dir.mkdir(parents=True, exist_ok=True)
        file_path = article_dir / "index.md"

        print(f"🚀 转换: {title} (order={order})...")

        try:
            html_raw = item.get_content()
            if isinstance(html_raw, str):
                html_raw = html_raw.encode("utf-8", errors="replace")

            md_content = parse_html_to_markdown(
                html_content=html_raw,
                base_href=href,
                book_get_item=get_item_fn,
                article_dir=article_dir,
            )

            front_matter = {
                "title": title,
                "order": order,
                "category": category,
                "book": book_stem,
            }
            final = "---\n" + yaml.dump(front_matter, allow_unicode=True) + "---\n\n" + md_content

            file_path.write_text(final, encoding="utf-8")

        except Exception as e:
            print(f"  ❌ 失败: {e}")

    print("\n✅ 全部转换完成！")


if __name__ == "__main__":
    if len(sys.argv) >= 2:
        INPUT_EPUB = Path(sys.argv[1])
    if len(sys.argv) >= 3:
        OUTPUT_DIR = Path(sys.argv[2])
    main()
