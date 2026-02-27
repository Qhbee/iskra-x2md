import fitz
import re
import sys
import yaml
from pathlib import Path

# Windows 控制台 UTF-8 输出，避免 UnicodeEncodeError
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# 导入我们的自定义解析器，而非官方的 pymupdf4llm
from marx_engels_parser import MarxEngelsParser
from marx_engels_parser import normalize_title

# ==================== 📜 解析规则 ====================

# 规则 A (到达指定层级)： 如果当前层级 == SPLIT_LEVEL (比如 5) -> 📄 变成文件。
# 规则 B (还没到层级，但没子级了)： 如果当前层级 < SPLIT_LEVEL (比如 3)，但它下面没有子节点了 -> 📄 变成文件 (比如“口号”、“斯大林像”的问题)。
# 规则 C (还没到层级，且有子级)： -> 📂 变成文件夹 (比如“正文”、“选自全集第一卷”)。
# 规则 D (超过层级)： -> 🔹 变成内容标题。

# ==================== 🎛️ 仪表盘配置 ====================

# 1. 路径配置 (定位到项目根目录)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
INPUT_DIR = PROJECT_ROOT / "data/raw/marx-engels/马克思恩格斯全集-文字版-带书签"
OUTPUT_BASE = PROJECT_ROOT / "data/processed/marx-engels/马克思恩格斯全集-文字版-带书签"

# 2. 安全模式
# True = 侦察模式 (只看目录结构)
# False = 执行模式 (生成最终 Markdown)
DRY_RUN = False

# 3. 切分层级
DEFAULT_SPLIT_LEVEL = 1 # 默认用 1 级
# 每个级别对应的卷（按 base_vol 分组，该卷所有分册用同一层级）
# 1: [2、3、4、7、8、9、10、11、12、13、14上、14下、15、16、17、18、19、21、22]
# 2: [1上、1下、20、26Ⅰ、26Ⅱ、26Ⅲ、42、43、44、45、46上、46下、50]
# 3: [5、6、23、24、25上、25下、31上、31下、32、33、34、35、36、37、38、39上、39下、47、48、49]
# 4: [27、28上、28下、29、30上、30下、]
# 特殊情况: [40、41]，里面有的2，有的3，待实现
_SPLIT_LEVEL_BY_VOL = {
    1: [2, 3, 4, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 21, 22],
    2: [1, 20, 26, 42, 43, 44, 45, 46, 50],
    3: [5, 6, 23, 24, 25, 31, 32, 33, 34, 35, 36, 37, 38, 39, 47, 48, 49],
    4: [27, 28, 29, 30],
}
# 运行时展开为 vol -> level 映射
VOLUME_SPLIT_LEVEL = {vol: level for level, vols in _SPLIT_LEVEL_BY_VOL.items() for vol in vols}

def get_split_level(pdf_name: str) -> int:
    """按 PDF 名称中的卷号查切分层级，未匹配则默认 1"""
    name = Path(pdf_name).stem
    m = re.search(r"第?(\d+)卷", name)
    if m:
        vol = int(m.group(1))
        if vol in VOLUME_SPLIT_LEVEL:
            return VOLUME_SPLIT_LEVEL[vol]
            # 40、41 特殊：内部有 2 有 3，暂按 2 fallback
        if vol in (40, 41):
            return 2  # TODO: 精细区分
    return DEFAULT_SPLIT_LEVEL

# 4. 黑名单
BLACKLIST = ["目录", "插图"]

# 5. 强制 md 级：以下标题无论书签层级如何，一律视为独立文件（如书签层级错误时用）
#    限制：仅适用于「父级末尾」的 force_md 子级（如附录末尾的注释、年表）。
#    若 force_md 穿插在父级中间（如附录 100-600，注释 200-300，年表 400-500），
#    边界计算会错误：父级只剩开头段，中间 force_md 会互相“吃掉”间隙。
#    因此一般只把书签最后几个层级错误的项加入本列表。
FORCE_MD_TITLES = ["前言", "注释", "译后记", "年表"]

def _is_force_md_title(title: str) -> bool:
    """强制 md：精确匹配 FORCE_MD_TITLES，或标题含「年表」或以「索引」结尾"""
    t = title.strip()
    if t in FORCE_MD_TITLES:
        return True
    if "年表" in t or t.endswith("索引"):
        return True
    return False

# 6. 强制目录级：以下标题无论书签层级如何，一律视为文件夹（优先级低于 force_md）
# 强制目录本身：一律为 📂。
# 强制目录的直接子项：一律提升为 📄，无论层数多少。
# 更深层的：保持 🔹，不会继续向上提升。
FORCE_FOLDER_TITLES = ["附录", "补遗"]

def _is_force_folder_title(title: str) -> bool:
    """强制目录：精确匹配 FORCE_FOLDER_TITLES，或以「遗稿」结尾"""
    t = title.strip()
    if t in FORCE_FOLDER_TITLES:
        return True
    if t.endswith("遗稿"):
        return True
    return False

# 青年马克思的文学和诗歌习作

# ==================== ⚙️ 智能引擎：转换逻辑 ====================

def sanitize_surrogates(text: str) -> str:
    """移除 PDF 书签中可能出现的 surrogate 等不可见字符，避免 UnicodeEncodeError"""
    return "".join(c for c in text if not ("\ud800" <= c <= "\udfff"))


def clean_filename(text):
    """文件名清洗，去特殊字符"""
    return re.sub(r'[\\/:*?"<>|]', '_', sanitize_surrogates(text)).strip()


def extract_toc_structure(doc, split_level: int = DEFAULT_SPLIT_LEVEL):
    """
    提取书签，并计算页码范围
    核心逻辑：先保留黑名单条目用于计算页码边界，算完后再过滤。
    """
    toc = doc.get_toc()
    total_pages = doc.page_count

    # --- 第一步：构建全量列表 (标记黑名单，但不删除) ---
    full_list = []
    skipping_level = -1 # -1 表示正常状态，非负数表示需要跳过该层级及其子级

    # 1. 标记黑名单
    for item in toc:
        lvl, title, page = item[0], sanitize_surrogates(item[1]), item[2]
        is_blacklisted = False

        # 1. 递归黑名单逻辑 (如果父级是黑名单，子级也是)
        if skipping_level != -1:
            if lvl > skipping_level:
                is_blacklisted = True
            else:
                skipping_level = -1

        # 2. 自身黑名单逻辑
        if skipping_level == -1 and any(bad in title for bad in BLACKLIST):
            is_blacklisted = True
            skipping_level = lvl

        force_md = _is_force_md_title(title)
        full_list.append({
            "level": lvl,
            "title": title.strip(),
            "start": page - 1,
            "end": -1,  # 待计算
            "is_blacklisted": is_blacklisted,  # 关键标记
            "has_children": False,   # 默认为 False，稍后计算
            "force_md": force_md,
            "effective_level": split_level if force_md else lvl,  # 强制 md 视为 split_level 层级
        })

    # --- 第二步：计算 has_children ---
    for i in range(len(full_list) - 1):
        # 如果 下一个元素 的 level > 当前元素 level，说明当前元素有子节点
        if full_list[i + 1]['level'] > full_list[i]['level']:
            full_list[i]['has_children'] = True

    # --- 第三步：计算页码 (用 effective_level，force_md 子级视为同级边界，使用包含黑名单的全量列表作为参考) ---
    # 父级 end = 下一个同级/更高级节点的 start - 1。force_md 的 effective_level=SPLIT_LEVEL，
    # 会截断父级。此逻辑仅正确适用于 force_md 连续排在父级末尾的情形（见 FORCE_MD_TITLES 注释）。
    for i in range(len(full_list)):
        current = full_list[i]

        # 寻找下一个“有效同级或更高级”的节点 (作为物理边界)
        # 即使那个节点是黑名单，它也是物理存在的，必须作为边界！
        # force_md 子级（如 注释）的 effective_level=SPLIT_LEVEL，会截断父级范围
        boundary_index = -1
        for j in range(i + 1, len(full_list)):
            if full_list[j]['effective_level'] <= current['effective_level']:
                boundary_index = j
                break

        if boundary_index != -1:
            # 结束页 = 下一个边界节点的开始页 - 1
            end_page = full_list[boundary_index]['start'] - 1
        else:
            # 没找到边界，说明是全书最后
            end_page = total_pages - 1

        # 修正逻辑：不能小于 start
        if end_page < current['start']:
            end_page = current['start']

        current['end'] = end_page

    # --- 第四步：最后才执行过滤 ---
    # 只保留非黑名单的条目
    return [item for item in full_list if not item['is_blacklisted']]


def process_one_pdf(input_pdf: Path, output_dir: Path):
    """处理单个 PDF 的转换逻辑"""
    split_level = get_split_level(input_pdf.name)
    print(f"📖 读取: {input_pdf.name} [切分层级: {split_level}]")
    try:
        doc = fitz.open(input_pdf)
    except Exception as e:
        print(f"❌ 无法打开 {input_pdf.name}: {e}")
        return

    toc = extract_toc_structure(doc, split_level)
    print(f"🔍 有效书签: {len(toc)} 个\n")

    # 路径栈和标题栈
    path_stack = {0: output_dir}
    title_stack = {}
    force_folder_levels = set()  # 记录哪些层级是强制目录，用于子项提升
    # 每个父目录下文章的序号（用于 01. 02. 前缀）
    article_idx_per_parent = {}

    # 初始化自定义解析器
    # 传入输出目录
    parser = MarxEngelsParser(output_dir)

    # 遍历书签
    for item in toc:
        lvl = item['level']
        title = normalize_title(item['title'])
        start = item['start']
        end = item['end']
        has_children = item['has_children']

        # 维护父级标题栈 (用于 Category)
        title_stack[lvl] = title
        # 清除更深层的旧标题和强制目录记录
        for k in list(title_stack.keys()):
            if k > lvl: del title_stack[k]
        force_folder_levels = {k for k in force_folder_levels if k <= lvl}

        # force_md 用 effective_level 控制缩进，与父级同级显示
        indent = "  " * (item.get("effective_level", lvl) - 1)

        # ========== 🧠 智能判定逻辑 ==========

        # 判定 0: 强制 md 级（书签层级错误时覆盖）
        force_md = item.get("force_md", False)  # 已在 extract_toc_structure 中计算

        # 判定 0.5: 强制目录级（优先级低于 force_md）
        force_folder = not force_md and _is_force_folder_title(title)

        # 判定 1: 这是一个文件吗？
        # 条件 X: 强制 md 级
        # 条件 A: 刚好到达切分层级
        # 条件 B: 还没到层级，但是它没有子节点了 (光杆司令，如"口号")
        is_file = force_md or (lvl == split_level) or (lvl < split_level and not has_children)
        if force_folder:
            is_file = False

        # 判定 2: 这是一个文件夹吗？
        # 条件: 非强制 md，还没到层级，且有子节点 (容器，如"正文")；或强制目录级
        is_folder = force_folder or (not force_md and (lvl < split_level and has_children))

        # 判定 3: 它是文件里的标题吗？
        # 条件: 非强制 md，且超过了层级
        is_content = not force_md and (lvl > split_level)

        # 提升逻辑：仅当「直接父级」是强制目录时，才将 🔹 提升为 📄
        # 否则会递归提升：小册子...（暴力在历史中的子级）被错误提升
        parent_levels = [k for k in title_stack.keys() if k < lvl]
        direct_parent_lvl = max(parent_levels) if parent_levels else None
        is_direct_child_of_force_folder = direct_parent_lvl is not None and direct_parent_lvl in force_folder_levels
        if is_content and is_direct_child_of_force_folder:
            is_content = False
            is_file = True  # 只提升一层，一律为 📄；子级保持 🔹

        # 关键：只要标题是强制目录，无论 DRY_RUN 与否，都必须更新 force_folder_levels，
        # 否则后续子项的 inside_force_folder 判断会失败
        if is_folder and _is_force_folder_title(title):
            force_folder_levels.add(lvl)

        # ========== 🚧 执行动作 ==========

        # --- 模式 A: 侦察模式 (DRY_RUN = True) ---

        if DRY_RUN:
            # 如果想统计页码，可以加上 (p{start + 1}-p{end + 1}, 共{end - start + 1}页)
            if is_file:
                print(f"{indent}📄 {title}")
            elif is_folder:
                print(f"{indent}📂 {title}")
            else:
                print(f"{indent}🔹 {title}")
            continue

        # --- 模式 B: 执行模式 (DRY_RUN = False) ---

        if is_folder:
            safe_name = clean_filename(title)
            parent = path_stack.get(lvl - 1, output_dir)
            # 同一父目录下按 toc 顺序加 01. 02. 前缀（与文件共用计数）
            key = str(parent)
            article_idx_per_parent[key] = article_idx_per_parent.get(key, 0) + 1
            idx = article_idx_per_parent[key]
            current_path = parent / f"{idx:02d}. {safe_name}"

            if not current_path.exists():
                current_path.mkdir(parents=True, exist_ok=True)

            path_stack[lvl] = current_path
            # force_folder_levels 已在上方统一更新
            print(f"{indent}📂 创建目录: {title}")

        elif is_file:
            parent = path_stack.get(lvl - 1, output_dir)
            # 同一父目录下按 toc 顺序加 01. 02. 前缀
            key = str(parent)
            article_idx_per_parent[key] = article_idx_per_parent.get(key, 0) + 1
            idx = article_idx_per_parent[key]
            article_dir = parent / f"{idx:02d}. {clean_filename(title)}"
            file_path = article_dir / "index.md"

            # 确保文章目录和父目录存在 (防止跳级情况)
            if not article_dir.exists():
                article_dir.mkdir(parents=True, exist_ok=True)

            # YAML
            cats = [title_stack[k] for k in sorted(title_stack.keys()) if k < lvl]
            front_matter = {
                "title": title,
                "order": start + 1,
                "category": "/".join(cats),
                "book": input_pdf.stem
            }

            # 采用 Page Bundles 模式
            print(f"{indent}🚀 转换“文章包” 📦 : {title} ({start + 1}-{end + 1})...")

            try:
                # === 关键：传入页码列表，使用 MarxEngelsParser 一次性处理整节，而非逐页解析 ===
                pages_to_process = list(range(start, end + 1))
                if not pages_to_process: continue

                # 调用 parse_chapter_pages
                md_content = parser.parse_chapter_pages(doc, pages_to_process, article_dir, title)

                final_content = "---\n" + yaml.dump(front_matter, allow_unicode=True) + "---\n\n" + md_content

                # 写入文件
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(final_content)

            except Exception as e:
                print(f"{indent}❌ 失败: {e}")

    doc.close()


def main():
    if not INPUT_DIR.exists():
        print(f"❌ 输入目录不存在: {INPUT_DIR}")
        return

    pdf_files = sorted(INPUT_DIR.glob("*.pdf"))
    if not pdf_files:
        print(f"❌ 目录下无 PDF 文件: {INPUT_DIR}")
        return

    OUTPUT_BASE.mkdir(parents=True, exist_ok=True)
    print(f"📂 输入目录: {INPUT_DIR}")
    print(f"📂 输出目录: {OUTPUT_BASE}")
    print(f"📄 共 {len(pdf_files)} 个 PDF\n")

    for i, input_pdf in enumerate(pdf_files):
        output_dir = OUTPUT_BASE / input_pdf.stem
        print("=" * 60)
        print(f"📖 [{i + 1}/{len(pdf_files)}] {input_pdf.name}")
        print("=" * 60)
        process_one_pdf(input_pdf, output_dir)
        if not DRY_RUN and i < len(pdf_files) - 1:
            print()

    if DRY_RUN:
        print("\n📢 --- 侦察结束 ---")
        print("请检查上面的输出：")
        print("1. 标有 📂 的是你想要的分类文件夹吗？")
        print("2. 标有 📄 的是你想要独立出来的文件吗？")
        print("3. 标有 🔹 的是你想要的内容标题吗？")
        print("如果是，请将 DRY_RUN 改为 False 正式执行。")
    else:
        print("\n✅ 全部转换完成！")


if __name__ == "__main__":
    main()