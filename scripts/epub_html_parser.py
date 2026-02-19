"""
EPUB 单 HTML 解析器：清洗、图片提取、HTML→Markdown 转换、后处理。
与 stalin_parser / PDF 转 MD 输出格式一致。
"""

import re
from pathlib import Path

from bs4 import BeautifulSoup
from markdownify import markdownify as md

# ================= 配置 =================

# Markdownify：GitHub 风格
MD_OPTIONS = {
    "heading_style": "ATX",      # # ## ###
    "bullets": "-",
    "escape_asterisks": False,
    "escape_underscores": False,
}


# ================= 解析逻辑 =================

def clean_filename(text):
    """文件名清洗，去特殊字符"""
    return re.sub(r'[\\/:*?"<>|]', '_', text).strip()


def _remove_scripts_styles(soup):
    """移除 script、style 等无用标签"""
    for tag in soup.find_all(["script", "style"]):
        tag.decompose()


def _resolve_img_src(src: str, base_href: str) -> str:
    """
    将相对 src 解析为 EPUB 内的绝对路径（用于 get_item_with_href）。
    base_href 如 "OEBPS/chapter1.xhtml"，src 如 "./images/pic.png"
    """
    if not src or src.startswith(("data:", "http://", "https://")):
        return src
    base_dir = "/".join(base_href.split("/")[:-1]) + "/" if "/" in base_href else ""
    parts = (base_dir + src).replace("\\", "/").split("/")
    resolved = []
    for p in parts:
        if p == "..":
            if resolved:
                resolved.pop()
        elif p != "." and p:
            resolved.append(p)
    return "/".join(resolved)


def _postprocess_paragraph_breaks(text: str) -> str:
    """
    后处理：段落内不插入多余换行。
    目标：段落之间用 \\n\\n，段落内无多余空行。
    """
    lines = text.split("\n")
    result = []
    current_para = []
    in_fenced = False

    def flush_para():
        if current_para:
            merged = " ".join(current_para)
            result.append(merged)
            current_para.clear()

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            flush_para()
            in_fenced = not in_fenced
            result.append(line)
            continue
        if in_fenced:
            result.append(line)
            continue

        is_break = (
            not stripped
            or stripped.startswith("#")
            or stripped.startswith(">")
            or re.match(r'^[-*+]\s', stripped)
            or re.match(r'^\d+\.\s', stripped)
        )
        if is_break:
            flush_para()
            if stripped:
                result.append(stripped)
        else:
            current_para.append(stripped)

    flush_para()
    return "\n\n".join(result)


def parse_html_to_markdown(
    html_content: bytes,
    base_href: str,
    book_get_item,
    article_dir: Path,
) -> str:
    """
    将单 HTML 转为 Markdown，并提取图片到 article_dir/assets/。

    :param html_content: 原始 HTML 字节
    :param base_href: 当前 HTML 在 EPUB 中的路径（如 OEBPS/ch1.xhtml），用于解析相对 img src
    :param book_get_item: 函数 href -> EpubItem，用于取图片二进制
    :param article_dir: Page Bundle 目录，图片保存到 article_dir/assets/
    :return: Markdown 正文（不含 front matter）
    """
    soup = BeautifulSoup(html_content, "html.parser")

    _remove_scripts_styles(soup)

    # 1. 收集图片，替换为占位符，保存到 assets
    assets_dir = article_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    img_counter = 0
    img_placeholders = {}  # placeholder_id -> (img_filename, original_src)

    for img in soup.find_all("img"):
        src = img.get("src")
        if not src:
            continue
        resolved = _resolve_img_src(src, base_href)
        if resolved.startswith(("data:", "http://", "https://")):
            continue
        try:
            item = book_get_item(resolved)
            if item is None:
                continue
            raw = item.get_content()
            if not raw:
                continue
        except Exception:
            continue

        img_counter += 1
        ext = _get_image_ext(resolved, raw)
        filename = f"img_{img_counter}{ext}"
        img_path = assets_dir / filename
        try:
            img_path.write_bytes(raw)
        except Exception:
            continue

        placeholder = f"__IMG_PLACEHOLDER_{img_counter}__"
        img_placeholders[placeholder] = (filename, src)
        new_tag = soup.new_tag("span")
        new_tag.string = placeholder
        img.replace_with(new_tag)

    # 2. HTML -> Markdown
    body = soup.find("body")
    if body is None:
        body = soup
    html_str = str(body)
    md_text = md(html_str, **MD_OPTIONS)

    # 3. 替换占位符为 ![img](assets/xxx.png)
    for ph, (filename, _) in img_placeholders.items():
        md_text = md_text.replace(ph, f"![img](assets/{filename})")

    # 4. 后处理：段落内多余换行
    md_text = _postprocess_paragraph_breaks(md_text)

    return md_text.strip()


def _get_image_ext(href: str, raw: bytes) -> str:
    """从 href 或魔数推断图片扩展名"""
    href_lower = href.lower()
    if ".png" in href_lower:
        return ".png"
    if ".jpg" in href_lower or ".jpeg" in href_lower:
        return ".jpg"
    if ".gif" in href_lower:
        return ".gif"
    if ".webp" in href_lower:
        return ".webp"
    if raw[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if raw[:2] == b"\xff\xd8":
        return ".jpg"
    if raw[:6] in (b"GIF87a", b"GIF89a"):
        return ".gif"
    return ".png"
