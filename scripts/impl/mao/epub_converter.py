"""
EPUB 转 Markdown：按 spine 顺序逐 HTML 转换，输出 Page Bundles（index.md + assets/）。
与 pdf_converter_custom 输出格式一致。
"""

import sys

# Windows 控制台 UTF-8 输出，避免 UnicodeEncodeError
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import ebooklib
import yaml
from pathlib import Path

from ebooklib import epub

from epub_html_parser import clean_filename, parse_html_to_markdown

# ==================== 仪表盘配置 ====================

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
INPUT_EPUB = PROJECT_ROOT / "data/raw/mao/毛泽东选集（1-7卷 静火版）V1.20 2019最新版.epub"
OUTPUT_DIR = PROJECT_ROOT / "data/processed/mao/毛泽东选集（1-7卷 静火版）V1.20 2019最新版"

# True = 侦察模式（只看 spine 结构）
# False = 执行模式（生成 Markdown）
DRY_RUN = True


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
    NCX 中父级 navPoint 也有 content src，需一并加入 href_map。
    """
    href_map = {}

    def walk(toc_entries, prefix: list):
        for entry in toc_entries or []:
            if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                section, children = entry[0], entry[1]
                sect_title = str(getattr(section, "title", str(section)))
                next_prefix = prefix + [clean_filename(sect_title)]
                # 父级 navPoint 的 href（如 第一卷->Volume01.xhtml, Section01->第一次国内革命战争时期）
                # 使用 next_prefix 作为 category，使 Section 写入 卷/时期/index.md 而非 卷/时期
                for attr in ("href", "content", "file_name"):
                    if hasattr(section, attr):
                        val = getattr(section, attr)
                        if val:
                            href = (str(val) or "").split("#")[0].strip()
                            if href:
                                href_map[href] = (sect_title, "/".join(next_prefix))
                            break
                walk(children, next_prefix)
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


def _common_category_prefix(cat_a: str, cat_b: str) -> str:
    """两 category 的公共路径前缀，如 卷一/时期一 与 卷一/时期二 → 卷一"""
    parts_a = (cat_a or "").split("/")
    parts_b = (cat_b or "").split("/")
    common = []
    for pa, pb in zip(parts_a, parts_b):
        if pa == pb:
            common.append(pa)
        else:
            break
    return "/".join(common)


# 根级项：href 文件名（英文）→ 中文标题。ebooklib 的 item.title 可能不完整，用 stem 更可靠
_FRONT_MATTER_ZH = {
    "Cover": "封面",
    "Epigraph": "题词",
    "Author": "作者",
    "Author1": "作者",
    "Contents": "目录"
}

def _href_in_nav(href: str, nav_map: dict) -> bool:
    """检查 href 是否在 toc/nav 中（支持多种路径格式）"""
    if href in nav_map:
        return True
    # 尝试变体：OEBPS/Text/xxx、Text/xxx、xxx
    base = href.split("/")[-1] if "/" in href else href
    return any(h.endswith(base) or base in h for h in nav_map)


def _reassign_root_category_to_volume(spine_docs: list, book_stem: str, nav_map: dict) -> None:
    """
    按 toc 处理 category：
    1. spine 中第一个 toc 项之前的 → 根级（category=""）
    2. 未在 toc 的项 → 向前找最近的在 toc 项，取其卷作为 category
    """
    # 找到 spine 中第一个出现在 toc 的项，其前的全部保留在根级
    first_toc_idx = None
    for i, d in enumerate(spine_docs):
        if _href_in_nav(d.get("href", "") or "", nav_map):
            first_toc_idx = i
            break
    root_indices = set(range(first_toc_idx)) if first_toc_idx is not None else set()

    for i, d in enumerate(spine_docs):
        if i in root_indices:
            d["category"] = ""
            continue
        cat = d["category"] or ""
        if not cat or cat == book_stem:
            # 夹逼：前一个、后一个都在 toc 且同一目录 → 中间的被遗漏，放同一目录
            prev_cat = None
            if i > 0:
                prev = spine_docs[i - 1]
                if _href_in_nav(prev.get("href", "") or "", nav_map):
                    prev_cat = prev.get("category") or ""
            next_cat = None
            if i < len(spine_docs) - 1:
                nxt = spine_docs[i + 1]
                if _href_in_nav(nxt.get("href", "") or "", nav_map):
                    next_cat = nxt.get("category") or ""
            if prev_cat and next_cat and prev_cat == next_cat:
                d["category"] = prev_cat
            elif prev_cat and next_cat:
                # 前后不同目录（如 时期一/文章一 与 时期二/文章三 之间）：用公共前缀
                # 如 卷一/时期一 与 卷一/时期二 → 卷一
                common = _common_category_prefix(prev_cat, next_cat)
                if common:
                    d["category"] = common
                else:
                    d["category"] = prev_cat
            elif prev_cat:
                # 边界（卷首/卷尾）：仅前一个在 toc，用前一个的 category
                d["category"] = prev_cat


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
            stem = Path(href).stem or f"章节_{i + 1}"
            title = _FRONT_MATTER_ZH.get(stem, stem)
        cat_info = nav_map.get(href, (title, ""))
        category = cat_info[1] or book_stem
        spine_docs.append({
            "item": item,
            "href": href,
            "title": title,
            "category": category,
            "order": i + 1,
        })

    # 将 category=毛泽东选集 的项按 spine 顺序分配到对应卷（消除根级「毛泽东选集」）
    # toc 未覆盖的项会落入 book_stem；spine 中第一个 toc 项之前的自动保留在根级
    _reassign_root_category_to_volume(spine_docs, book_stem, nav_map)

    print(f"🔍 有效章节: {len(spine_docs)} 个\n")

    if DRY_RUN:
        # 按 category 层级输出树状结构，与 PDF 侦察模式一致
        category_stack = []
        for d in spine_docs:
            cat_parts = [p for p in (d["category"] or "").split("/") if p]
            title = d["title"]
            safe_title = clean_filename(title)
            last_cat = clean_filename(cat_parts[-1]) if cat_parts else ""
            is_section_index = bool(last_cat and last_cat == safe_title)

            # 输出未打印的 category 文件夹（📂）
            for i, part in enumerate(cat_parts):
                if i >= len(category_stack) or category_stack[i] != part:
                    indent = "  " * i
                    print(f"{indent}📂 {part}")
                    category_stack = category_stack[:i] + [part]

            # 输出文章（📄）；section 与文件夹同名时显示为 index.md
            indent = "  " * len(cat_parts)
            display_title = "index.md" if is_section_index else title
            print(f"{indent}📄 {display_title}")
        print("\n📢 --- 侦察结束 ---")
        print("请检查上面的输出：")
        print("1. 标有 📂 的是你想要的分类文件夹吗？")
        print("2. 标有 📄 的是你想要独立出来的文件吗？")
        print("如果是，请将 DRY_RUN 改为 False 正式执行。")
        return

    output_base = Path(OUTPUT_DIR)
    output_base.mkdir(parents=True, exist_ok=True)

    print(f"📂 输入: {INPUT_EPUB}")
    print(f"📂 输出: {output_base}")
    print(f"📄 共 {len(spine_docs)} 个章节\n")
    print("=" * 60)
    print(f"📖 {INPUT_EPUB.name}")
    print("=" * 60)

    category_stack = []
    # 01. 02. 序号（模仿列宁/马恩）：同一父目录下按 spine 顺序递增
    article_idx_per_parent = {}
    # path_stack: category 前缀 -> 实际路径（含序号）。子项通过此表找到带序号的父目录
    path_stack = {"": output_base}
    for d in spine_docs:
        item = d["item"]
        href = d["href"]
        title = d["title"]
        category = d["category"]
        order = d["order"]

        # 计算 Page Bundle 路径
        safe_title = clean_filename(title)
        cat_parts = [p for p in category.split("/") if p]
        last_cat = clean_filename(cat_parts[-1]) if cat_parts else ""
        is_section_index = bool(last_cat and last_cat == safe_title)  # 标题与 category 最后一级同名

        # 确定父目录：section index 的父是上一级，普通文章的父是当前 category 的文件夹
        parent_cat = "/".join(cat_parts[:-1]) if len(cat_parts) > 1 else ("" if cat_parts else "")
        parent = path_stack.get(parent_cat if is_section_index else category, output_base)

        # 同一 parent 下序号递增，生成 01. 02. 前缀
        key = str(parent)
        article_idx_per_parent[key] = article_idx_per_parent.get(key, 0) + 1
        idx = article_idx_per_parent[key]
        numbered_name = f"{idx:02d}. {safe_title}"

        if cat_parts:
            article_dir = parent / numbered_name
            if is_section_index:
                path_stack[category] = article_dir  # 供子项查找
        else:
            article_dir = output_base / numbered_name

        article_dir.mkdir(parents=True, exist_ok=True)
        file_path = article_dir / "index.md"

        # 输出未打印的 category 文件夹（与 PDF 执行模式一致）
        for i, part in enumerate(cat_parts):
            if i >= len(category_stack) or category_stack[i] != part:
                indent = "  " * i
                print(f"{indent}📂 创建目录: {part}")
                category_stack = category_stack[:i] + [part]

        indent = "  " * len(cat_parts)
        display_title = f"{title} (index.md)" if is_section_index else title
        print(f"{indent}🚀 转换「文章包」📦 : {display_title}")

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
            print(f"{indent}❌ 失败: {e}")

    print("\n✅ 全部转换完成！")


if __name__ == "__main__":
    if len(sys.argv) >= 2:
        INPUT_EPUB = Path(sys.argv[1])
    if len(sys.argv) >= 3:
        OUTPUT_DIR = Path(sys.argv[2])
    main()
