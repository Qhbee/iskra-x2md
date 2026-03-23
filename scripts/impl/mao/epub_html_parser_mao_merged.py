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


def _caption_block_start_index(children, node):
    """node 在 container 的第几个顶层子块开始（直接子或某子树内）。"""
    if node is None:
        return None
    if node in children:
        return children.index(node)
    for i, c in enumerate(children):
        if getattr(c, "name", None) and node in c.descendants:
            return i
    return None


def _restructure_caption_style_blocks(soup):
    """
    按 stylesheet 语义统一拆「标题行 + 副标题 + 日期」，不区分 head / head-mzd：
    - span.underline1：副标题 → 紧跟的独立段落 <strong>…</strong>（Markdown **）
    - b.calibre9 / b.calibre16：日期等 → 再一段 <em>…</em>（Markdown *斜体*，去掉 b 粗体）
    - 主行：上述块之前的节点（含脚注 [^n]）；内部仅版式用的 <br> 丢弃（中文折行直接相接）

    作用范围：所有 h1–h6；以及含 calibre12 的 p（如第七卷汇编篇目列表）。
    须在脚注替换、标题层级归一、epigraph→标题 之后执行。
    """
    body = soup.find("body") or soup

    def _is_date_b(classes):
        if not classes:
            return False
        return "calibre9" in classes or "calibre16" in classes

    candidates = []
    candidates.extend(body.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]))
    candidates.extend(body.find_all("p", class_=lambda c: c and "calibre12" in c))

    for tag in list(candidates):
        u = tag.find("span", class_=lambda c: c and "underline1" in c)
        b_meta = tag.find("b", class_=lambda c: _is_date_b(c or []))
        if u is None and b_meta is None:
            continue

        subtitle_text = ""
        if u is not None:
            for br in list(u.find_all("br")):
                br.replace_with("")
            subtitle_text = u.get_text(separator="", strip=True)

        date_text = ""
        if b_meta is not None:
            date_text = b_meta.get_text(separator="", strip=True)

        children = list(tag.children)
        iu = _caption_block_start_index(children, u)
        ib = _caption_block_start_index(children, b_meta)
        idxs = [x for x in (iu, ib) if x is not None]
        if not idxs:
            continue
        split_i = min(idxs)

        head_chunks = []
        for c in children[:split_i]:
            if getattr(c, "name", None) == "br":
                continue
            head_chunks.append(c)

        for c in children[split_i:]:
            if getattr(c, "name", None):
                c.decompose()
            else:
                c.extract()

        tag.clear()
        for ch in head_chunks:
            tag.append(ch)

        insert_after = tag
        if subtitle_text:
            p_sub = soup.new_tag("p")
            st = soup.new_tag("strong")
            st.append(NavigableString(subtitle_text))
            p_sub.append(st)
            insert_after.insert_after(p_sub)
            insert_after = p_sub
        if date_text:
            p_dt = soup.new_tag("p")
            em = soup.new_tag("em")
            em.append(NavigableString(date_text))
            p_dt.append(em)
            insert_after.insert_after(p_dt)


def _iter_xinjian_fs_paragraphs(div):
    """div.xinjian-fs 内所有 p.calibre14 / p.calibre15（生成器，按子节点顺序）。"""
    for child in list(div.children):
        if getattr(child, "name", None) != "p":
            continue
        cls = child.get("class") or []
        if "calibre14" in cls or "calibre15" in cls:
            yield child


def _xinjian_fs_first_line_text(div) -> str:
    for p in _iter_xinjian_fs_paragraphs(div):
        return p.get_text(separator="", strip=True)
    return ""


def _is_qa_quote_line(text: str) -> bool:
    """是否为「问：」「答：」开头的引用行（用于相邻块是否合并的判断）。"""
    t = (text or "").lstrip()
    return t.startswith("问：") or t.startswith("答：")


def _prev_adjacent_xinjian_fs(div):
    x = div.previous_sibling
    while x is not None:
        if isinstance(x, str) and not str(x).strip():
            x = x.previous_sibling
            continue
        if getattr(x, "name", None) == "div" and "xinjian-fs" in (x.get("class") or []):
            return x
        return None
    return None


def _next_adjacent_xinjian_fs(div):
    x = div.next_sibling
    while x is not None:
        if isinstance(x, str) and not str(x).strip():
            x = x.next_sibling
            continue
        if getattr(x, "name", None) == "div" and "xinjian-fs" in (x.get("class") or []):
            return x
        return None
    return None


def _collect_xinjian_fs_chains(body):
    """文档顺序下，仅相邻的 div.xinjian-fs 连成一条链（中间可有空白文本节点）。"""
    seen = set()
    chains = []
    for div in body.find_all("div", class_=lambda c: c and "xinjian-fs" in c):
        if id(div) in seen:
            continue
        head = div
        while True:
            p = _prev_adjacent_xinjian_fs(head)
            if p is None:
                break
            head = p
        chain = []
        cur = head
        while cur is not None:
            chain.append(cur)
            seen.add(id(cur))
            cur = _next_adjacent_xinjian_fs(cur)
        chains.append(chain)
    return chains


def _partition_xinjian_chain_for_blockquotes(chain):
    """
    一条相邻 xinjian-fs 链 → 多组 div 列表；每组合并为一个 <blockquote>。
    规则：若上一段首行、本段首行均为「问：」或「答：」，则拆开（不合并）；
    否则并入上一组（同一 blockquote 内多 <p>，markdownify 会输出 >…\\n>\\n>…）。
    """
    if not chain:
        return []
    groups = [[chain[0]]]
    for i in range(1, len(chain)):
        t_prev = _xinjian_fs_first_line_text(chain[i - 1])
        t_curr = _xinjian_fs_first_line_text(chain[i])
        if _is_qa_quote_line(t_prev) and _is_qa_quote_line(t_curr):
            groups.append([chain[i]])
        else:
            groups[-1].append(chain[i])
    return groups


def _wrap_xinjian_fs_as_blockquotes(soup):
    """
    div.xinjian-fs 内 p.calibre14 / p.calibre15 → <blockquote>。
    相邻 xinjian-fs：默认合并到同一 blockquote（多 <p>，导出为 > 段\\n>\\n> 段）；
    仅当「上一块首行与下一块首行均为 问：/答：」时拆成独立 blockquote（问、答各段分开）。
    """
    body = soup.find("body") or soup

    def _div_empty_or_ws(d):
        for c in d.children:
            if getattr(c, "name", None):
                return False
            if isinstance(c, str) and c.strip():
                return False
        return True

    for chain in _collect_xinjian_fs_chains(body):
        for group in _partition_xinjian_chain_for_blockquotes(chain):
            movers = []
            for div in group:
                movers.extend(list(_iter_xinjian_fs_paragraphs(div)))
            if not movers:
                for div in group:
                    if _div_empty_or_ws(div):
                        div.decompose()
                continue
            bq = soup.new_tag("blockquote")
            group[0].insert_before(bq)
            for p in movers:
                bq.append(p.extract())
            for div in group:
                if _div_empty_or_ws(div):
                    div.decompose()


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
    连续 blockquote 行（含仅 \">\" 的段间空行）整段保留，不拆成空格合并。
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

    # 0.551 标题/汇编行：underline1→下一段 **；calibre9/16→再一段 *（见 _restructure_caption_style_blocks）
    _restructure_caption_style_blocks(soup)

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

    # 0.6 引用段落：div.xinjian-fs 内 calibre14/15 → blockquote（> 引用）
    _wrap_xinjian_fs_as_blockquotes(soup)

    div = soup.find("div", class_="div") or soup.find("body") or soup

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
