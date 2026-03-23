"""
EPUB 单 HTML 解析器：清洗、图片提取、HTML→Markdown 转换、后处理。
与 PDF 转 MD 输出格式一致。

专用于：《毛泽东选集全七卷（官方、静火、润之赤旗三合一版）》→ 由 epub_converter_mao_merged.py 调用。
若三合一与静火版 HTML/CSS 类名、结构不一致，请在本文件调整，勿修改同目录下的 epub_html_parser.py（静火流水线仍用后者）。

三合一 stylesheet 为多看脚注（.duokan-footnote*），不包含静火 .zy/.zs/.zs1；脚注解析仅实现 Duokan；静火版请用 epub_html_parser.py。
"""

import re
from collections import deque
from itertools import groupby
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString
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


def _convert_epigraph_calibre_headings(soup):
    """
    div.epigraph 内按静火/三合一 stylesheet 语义将小标题转为 h2/h3/h4：
    calibre12 / calibre26 → ##（h2），calibre13 → ###（h3），calibre17 → ####（h4）。
    calibre26 与 12 版式同级，多见于前言后记；转换后拆掉 epigraph 容器，避免 markdownify 多包一层 div。
    """
    body = soup.find("body") or soup
    mapping = (
        ("calibre12", 2),
        ("calibre26", 2),
        ("calibre13", 3),
        ("calibre17", 4),
    )
    for ep in list(body.find_all("div", class_=lambda c: c and "epigraph" in c)):
        for p in list(ep.find_all("p", recursive=False)):
            classes = p.get("class") or []
            level = None
            for cls, lv in mapping:
                if cls in classes:
                    level = lv
                    break
            if level is None:
                continue
            h = soup.new_tag(f"h{level}")
            for child in list(p.children):
                h.append(child.extract())
            p.replace_with(h)
        # 拆掉 epigraph 容器，子节点整段前移（先快照再移动，避免迭代中 DOM 变化）
        to_move = list(ep.contents)
        for c in to_move:
            ep.insert_before(c)
        ep.decompose()


def _convert_centered_subheadings(soup):
    """
    将 p.a5 和 p.a0+span.f3 转为居中小标题（h1-h6）。
    层级由前一个真实标题（h1-h6）决定；连续的 p.a5/p.a0+f3 同级（如第一、第二、第三…）。
    若前一个已是 h6 则不转标题，当正文，改为加粗 ** ** 强调。
    """
    body = soup.find("body") or soup
    div = body.find("div", class_="div") or body
    if not hasattr(div, "find_all"):
        return

    last_heading_level = 0
    for tag in list(div.find_all(True)):
        if tag.name in ("h1", "h2", "h3", "h4", "h5", "h6"):
            last_heading_level = int(tag.name[1])
            continue
        if tag.name != "p":
            continue

        classes = tag.get("class", []) or []
        is_a5 = "a5" in classes
        has_f3 = tag.find(class_=lambda c: c and "f3" in c) is not None
        is_a0_f3 = "a0" in classes and has_f3

        if not (is_a5 or is_a0_f3):
            continue
        if last_heading_level >= 6:
            # h6 之后不转标题，改为加粗 ** ** 轻微强调
            strong = soup.new_tag("strong")
            for child in list(tag.children):
                strong.append(child.extract())
            tag.append(strong)
            continue

        level = last_heading_level + 1
        h_tag = soup.new_tag(f"h{level}")
        for child in list(tag.children):
            h_tag.append(child.extract())
        tag.replace_with(h_tag)
        # 不更新 last_heading_level：连续的 p.a5/p.a0+f3 保持同级


def _convert_footnotes_to_markdown(soup) -> str:
    """
    将三合一毛选 EPUB 的注释格式转为 Markdown 脚注（与马列 PDF 输出一致）。

    仅处理多看（Duokan）结构：stylesheet 中 .duokan-footnote / .duokan-footnote-content 等；
    文内 ol.duokan-footnote-content + a.duokan-footnote（常为 sup+note.png）。

    - 文末 li 的 id 与文内 href（如 #ref_footnotebookmark_end_1_1、#A-9）对应
    - li 内 p.footnote 首段 a.duokan-footnote（◎）仅作标记，不写入 [^n]: 正文
    - 正文 [^n]，文末 [^n]: 全文；序号按 ol 中 li 顺序从 1 递增
    """
    body = soup.find("body") or soup
    href_to_num: dict[str, int] = {}
    footnote_defs: list[tuple[int, str]] = []
    idx_global = 0

    ols = body.find_all("ol", class_=lambda c: c and "duokan-footnote-content" in c)
    for ol in ols:
        for li in ol.find_all("li", recursive=False):
            idx_global += 1
            idx = idx_global
            li_id = li.get("id")
            if li_id:
                href_to_num[li_id] = idx
            p_fn = li.find("p", class_=lambda c: c and "footnote" in (c or []))
            if not p_fn:
                p_fn = li.find("p")
            text = ""
            if p_fn:
                for a in p_fn.find_all("a", class_="duokan-footnote"):
                    h = (a.get("href") or "").lstrip("#")
                    if h:
                        href_to_num[h] = idx
                for a in list(p_fn.find_all("a", class_="duokan-footnote")):
                    a.decompose()
                for br in p_fn.find_all("br"):
                    br.replace_with("\n")
                text = p_fn.get_text(separator="", strip=True)
                text = re.sub(r"\s+", " ", text).strip()
            footnote_defs.append((idx, text))
        ol.decompose()

    if not footnote_defs:
        return ""

    for a in list(soup.find_all("a", class_="duokan-footnote")):
        h = (a.get("href") or "").lstrip("#")
        if not h:
            continue
        n = href_to_num.get(h)
        if n is None:
            continue
        repl = NavigableString(f"[^{n}]")
        parent = a.parent
        if parent and parent.name == "sup":
            parent.replace_with(repl)
        else:
            a.replace_with(repl)

    lines = [f"[^{i}]: {t}" for i, t in sorted(footnote_defs, key=lambda x: x[0])]
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
    连续 blockquote 行（> 开头）之间只用 \\n，避免引用块内出现空行。
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

    lines = deque(lines)
    while lines:
        line = lines.popleft()
        stripped = line.strip()
        if stripped.startswith("```"):
            flush_para()
            in_fenced = not in_fenced
            result.append(line)
            continue
        if in_fenced:
            result.append(line)
            continue

        if stripped.startswith(">"):
            flush_para()
            block = [stripped]
            while lines and lines[0].strip().startswith(">"):
                block.append(lines.popleft().strip())
            result.append("\n".join(block))
            continue

        is_break = (
            not stripped
            or stripped.startswith("#")
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

    # 0.55 居中小标题：epigraph 内 calibre12/13/17 → h2/h3/h4（须在 0.5 之后，避免与「篇题 h3→h1」归一冲突）
    _convert_epigraph_calibre_headings(soup)

    # 0.56 标题内 br 直接移除（避免多余空格）
    body = soup.find("body") or soup
    for h in body.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
        for br in h.find_all("br"):
            br.decompose()

    # 0.57 Volume 封面「毛泽东选集」→ 加粗（span 含 c31 f1 t67 t42 全匹配）
    vol_cover_classes = ("c31", "f1", "t67", "t42")
    for p in body.find_all("p", class_=lambda c: c and "a0" in c and "t94" in c):
        span = p.find("span", class_=lambda c: c and all(k in c for k in vol_cover_classes))
        if span:
            strong = soup.new_tag("strong")
            for child in list(span.children):
                strong.append(child.extract())
            span.replace_with(strong)

    # 0.6 引用段落：p.a3 连续合并为一个 blockquote；p.a31 不合并，每个单独 blockquote（问/答独立）
    def _quote_type(tag):
        if tag.name != "p":
            return None
        c = tag.get("class", [])
        if not c:
            return None
        return "a31" if "a31" in c else ("a3" if "a3" in c else None)

    div = soup.find("div", class_="div") or soup.find("body") or soup
    all_p = div.find_all("p", recursive=True)

    # a3：连续合并
    for qt, group in groupby(all_p, key=_quote_type):
        if qt != "a3":
            continue
        group = list(group)
        if not group:
            continue
        bq = soup.new_tag("blockquote")
        group[0].insert_before(bq)
        for p in group:
            bq.append(p.extract())

    # a31：不合并；含 <br/> 的答分段为多个 p，段间有 > 空行，续行加前导空格
    for p in list(div.find_all("p", class_=lambda c: c and "a31" in c)):
        brs = p.find_all("br")
        if not brs:
            bq = soup.new_tag("blockquote")
            p.wrap(bq)
            continue
        # 按 br 分段（不修改 DOM，避免空分段时破坏 p）
        segments = []
        current = []
        for child in p.children:
            if getattr(child, "name", None) == "br":
                if current:
                    seg = BeautifulSoup("".join(str(c) for c in current), "html.parser").get_text(separator="", strip=True)
                    if seg:
                        segments.append(seg)
                    current = []
            else:
                current.append(child)
        if current:
            seg = BeautifulSoup("".join(str(c) for c in current), "html.parser").get_text(separator="", strip=True)
            if seg:
                segments.append(seg)
        if not segments:
            bq = soup.new_tag("blockquote")
            p.wrap(bq)
            continue
        bq = soup.new_tag("blockquote")
        for idx, seg in enumerate(segments):
            new_p = soup.new_tag("p")
            new_p.string = (" " + seg) if idx > 0 else seg
            bq.append(new_p)
        p.replace_with(bq)

    # 0.7 p.a0 + span.f2（日期/副标题）→ 斜体
    # 三种情况
    # --- OEBPS/Text/Section0647.xhtml ---
    #     15 | <p class="a0"><span class="f2">（一九五五年九月、十二月）</span></p>
    #     19 | <p class="a0"><span class="f2 t61">（一九五五年九月二十五日）</span></p>
    # --- OEBPS/Text/Section0215.xhtml ---
    #     15 | <p class="a0"><span class="f2 t63">论认识和实践的关系<br/>——知和行的关系</span></p>
    #     17 | <p class="a0"><span class="f2">（一九三七年七月）</span></p>
    # t63 是真副标题，也 * * 斜体
    # t61 是序、跋这种二级标题的小号字日期，也 * * 斜体
    # 不管 span.t63, span.t61，只要 p.a0 + span.f2 就  * * 斜体
    for p in list(div.find_all("p", class_=lambda c: c and "a0" in c)):
        if p.find(class_=lambda c: c and "f2" in c) is None:
            continue
        em = soup.new_tag("em")
        for child in list(p.children):
            em.append(child.extract())
        p.append(em)

    # 0.8 p.a2（右侧落款签名/日期）→ 斜体
    for p in list(div.find_all("p", class_=lambda c: c and "a2" in c)):
        em = soup.new_tag("em")
        for child in list(p.children):
            em.append(child.extract())
        p.append(em)

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
