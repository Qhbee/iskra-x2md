"""
EPUB 单 HTML 解析器：清洗、图片提取、HTML→Markdown 转换、后处理。
与 PDF 转 MD 输出格式一致。
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


def _normalize_heading_levels_in_soup(soup):
    """
    预处理：最高级标题提升为 h1，其余顺延。
    如文档最大是 h3 → h1，h4 → h2；若已是 h1 则不改。
    """
    body = soup.find("body") or soup
    headings = body.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])
    if not headings:
        return
    min_level = min(int(tag.name[1]) for tag in headings)
    if min_level <= 1:
        return
    offset = min_level - 1
    for tag in headings:
        old_level = int(tag.name[1])
        new_level = max(1, old_level - offset)
        tag.name = f"h{new_level}"


def _convert_footnotes_to_markdown(soup) -> str:
    """
    将毛选 EPUB 的注释格式转为 Markdown 脚注（与马列 PDF 输出一致）。
    - 正文内 <a class="zy" href="#idNa">〔N〕</a> → [^N]
    - 注释区 <p class="zs"><a class="hl" id="idNa">〔N〕</a>内容</p> → [^N]: 内容
    - p.zs1 为上一注脚续行，拼接到上一段
    """
    # 1. 正文内：a.zy 替换为 [^N]
    for a in soup.find_all("a", class_="zy"):
        aid = a.get("id") or ""
        m = re.match(r"^id(\d+)$", aid)
        if m:
            note_id = m.group(1)
            ref = soup.new_string(f"[^{note_id}]")
            a.replace_with(ref)

    body = soup.find("body") or soup
    div = body.find("div", class_="div") or body
    if not hasattr(div, "find_all"):
        return ""

    # 3. 收集 p.zs / p.zs1，转为 [^N]: content（按文档顺序）
    current_note_id = None
    current_content = []
    note_blocks = []

    for tag in div.find_all("p", class_=True):
        classes = tag.get("class", [])
        is_zs = "zs" in classes and "zs1" not in classes
        is_zs1 = "zs1" in classes
        if not is_zs and not is_zs1:
            continue

        if is_zs:
            a_hl = tag.find("a", class_="hl")
            if a_hl:
                if current_note_id is not None and current_content:
                    note_blocks.append((current_note_id, current_content))
                mid = a_hl.get("id") or ""
                mm = re.match(r"^id(\d+)a$", mid)
                if mm:
                    current_note_id = mm.group(1)
                    parts = []
                    for s in a_hl.next_siblings:
                        if hasattr(s, "get_text"):
                            parts.append(s.get_text())
                        elif isinstance(s, str):
                            parts.append(s)
                    content = " ".join(parts).strip()
                    current_content = [content] if content else []
        else:
            if current_note_id is not None:
                current_content.append(tag.get_text(separator=" ", strip=True))

    if current_note_id is not None and current_content:
        note_blocks.append((current_note_id, current_content))

    # 4. 移除注释区（p.zs/p.zs1 已收集；移除「注　　释」标题行）
    for tag in div.find_all("p", class_=True):
        classes = tag.get("class", [])
        if "zs" in classes or "zs1" in classes:
            tag.decompose()
    for tag in div.find_all("p"):
        txt = tag.get_text(strip=True)
        if txt and "注" in txt and "释" in txt and len(txt) < 15:
            tag.decompose()
            break

    # 5. 生成脚注块（多段时用缩进续行，保留分段）
    def _indent_block(s):
        """段落内若有换行，每行都缩进"""
        return "\n".join("    " + line for line in s.split("\n"))

    lines = []
    for nid, paras in note_blocks:
        if not paras:
            continue
        first = paras[0].strip()
        rest = [p.strip() for p in paras[1:] if p.strip()]
        if rest:
            body = first + "\n\n" + "\n\n".join(_indent_block(p) for p in rest)
        else:
            body = first
        lines.append(f"[^{nid}]: {body}")
    return "\n\n".join(lines) if lines else ""


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

    # 0. 注释转 Markdown 脚注（与马列格式一致），并移除注释区
    footnote_block = _convert_footnotes_to_markdown(soup)

    # 0.5 标题层级归一：最高级提升为 h1，其余顺延（预处理，避免后处理多遍历）
    _normalize_heading_levels_in_soup(soup)

    # 1. 收集图片，替换为占位符，保存到 assets
    assets_dir = article_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    img_counter = 0
    img_placeholders = {}  # placeholder_id -> (img_filename, original_src)

    image_sources = []
    for img in soup.find_all("img"):
        src = img.get("src")
        if src:
            image_sources.append((img, src))
    for svg in soup.find_all("svg"):
        img_el = svg.find("image")
        if img_el:
            src = img_el.get("href") or img_el.get("xlink:href")
            if not src and img_el.attrs:
                for k, v in img_el.attrs.items():
                    if "href" in k.lower() and v:
                        src = v
                        break
            if src:
                image_sources.append((svg, src))

    for tag, src in image_sources:
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
            img_counter -= 1
            continue

        placeholder = f"__IMG_PLACEHOLDER_{img_counter}__"
        img_placeholders[placeholder] = (filename, src)
        new_tag = soup.new_tag("span")
        new_tag.string = placeholder
        tag.replace_with(new_tag)

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

    # 5. 追加脚注块（与马列 PDF 输出一致）
    if footnote_block:
        md_text = md_text.rstrip() + "\n\n" + footnote_block

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
