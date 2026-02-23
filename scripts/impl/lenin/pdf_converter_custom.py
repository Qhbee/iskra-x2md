import fitz
import re
import yaml
from pathlib import Path

# 导入我们的自定义解析器，而非官方的 pymupdf4llm
from lenin_parser import LeninParser

# ==================== 📜 解析规则 ====================

# 规则 A (到达指定层级)： 如果当前层级 == SPLIT_LEVEL (比如 5) -> 📄 变成文件。
# 规则 B (还没到层级，但没子级了)： 如果当前层级 < SPLIT_LEVEL (比如 3)，但它下面没有子节点了 -> 📄 变成文件 (比如“口号”、“斯大林像”的问题)。
# 规则 C (还没到层级，且有子级)： -> 📂 变成文件夹 (比如“正文”、“选自全集第一卷”)。
# 规则 D (超过层级)： -> 🔹 变成内容标题。

# ==================== 🎛️ 仪表盘配置 ====================

# 1. 路径配置 (定位到项目根目录)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
INPUT_PDF = PROJECT_ROOT / "data/raw/lenin/列宁全集（版本II-文字版）（完整书签版）/列宁全集 第1卷（1893年—1894年）.pdf"
OUTPUT_DIR = PROJECT_ROOT / "data/processed/lenin/列宁全集（版本II-文字版）（完整书签版）/列宁全集 第1卷（1893年—1894年）"

# 2. 安全模式
# True = 侦察模式 (只看目录结构)
# False = 执行模式 (生成最终 Markdown)
DRY_RUN = False

# 3. 切分层级
SPLIT_LEVEL = 1

# 4. 黑名单
BLACKLIST = ["目录"]

# 5. 强制 md 级：以下标题无论书签层级如何，一律视为独立文件（如书签层级错误时用）
#    限制：仅适用于「父级末尾」的 force_md 子级（如附录末尾的注释、年表）。
#    若 force_md 穿插在父级中间（如附录 100-600，注释 200-300，年表 400-500），
#    边界计算会错误：父级只剩开头段，中间 force_md 会互相“吃掉”间隙。
#    因此一般只把书签最后几个层级错误的项加入本列表。
FORCE_MD_TITLES = ["注释", "年表"]


# ==================== ⚙️ 智能引擎：转换逻辑 ====================

def clean_filename(text):
    """文件名清洗，去特殊字符"""
    return re.sub(r'[\\/:*?"<>|]', '_', text).strip()


def extract_toc_structure(doc):
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
        lvl, title, page = item[0], item[1], item[2]
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

        force_md = bool(FORCE_MD_TITLES and title.strip() in FORCE_MD_TITLES)
        full_list.append({
            "level": lvl,
            "title": title.strip(),
            "start": page - 1,
            "end": -1,  # 待计算
            "is_blacklisted": is_blacklisted,  # 关键标记
            "has_children": False,   # 默认为 False，稍后计算
            "force_md": force_md,
            "effective_level": SPLIT_LEVEL if force_md else lvl,  # 强制 md 视为 SPLIT_LEVEL 层级
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


def main():
    print(f"📖 读取: {INPUT_PDF.name}")
    try:
        doc = fitz.open(INPUT_PDF)
    except Exception as e:
        print(f"❌ 无法打开: {e}")
        return

    toc = extract_toc_structure(doc)
    print(f"🔍 有效书签: {len(toc)} 个\n")

    # 路径栈和标题栈
    path_stack = {0: OUTPUT_DIR}
    title_stack = {}

    # 初始化自定义解析器
    # 传入输出目录
    parser = LeninParser(OUTPUT_DIR)

    # 遍历书签
    for item in toc:
        lvl = item['level']
        title = item['title']
        start = item['start']
        end = item['end']
        has_children = item['has_children']

        # 维护父级标题栈 (用于 Category)
        title_stack[lvl] = title
        # 清除更深层的旧标题
        for k in list(title_stack.keys()):
            if k > lvl: del title_stack[k]

        # force_md 用 effective_level 控制缩进，与父级同级显示
        indent = "  " * (item.get("effective_level", lvl) - 1)

        # ========== 🧠 智能判定逻辑 ==========

        # 判定 0: 强制 md 级（书签层级错误时覆盖）
        force_md = item.get("force_md", False)  # 已在 extract_toc_structure 中计算

        # 判定 1: 这是一个文件吗？
        # 条件 X: 强制 md 级
        # 条件 A: 刚好到达切分层级 (L5)
        # 条件 B: 还没到层级 (L3, L4)，但是它没有子节点了 (光杆司令，如"口号")
        is_file = force_md or (lvl == SPLIT_LEVEL) or (lvl < SPLIT_LEVEL and not has_children)

        # 判定 2: 这是一个文件夹吗？
        # 条件: 非强制 md，还没到层级，且有子节点 (容器，如"正文")
        is_folder = not force_md and (lvl < SPLIT_LEVEL and has_children)

        # 判定 3: 它是文件里的标题吗？
        # 条件: 非强制 md，且超过了层级 (L6+)
        is_content = not force_md and (lvl > SPLIT_LEVEL)

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
            parent = path_stack.get(lvl - 1, OUTPUT_DIR)
            current_path = parent / safe_name

            if not current_path.exists():
                current_path.mkdir(parents=True, exist_ok=True)

            path_stack[lvl] = current_path
            print(f"{indent}📂 创建目录: {title}")

        elif is_file:
            parent = path_stack.get(lvl - 1, OUTPUT_DIR)
            article_dir = parent / clean_filename(title)
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
                "book": INPUT_PDF.stem
            }

            # 采用 Page Bundles 模式
            print(f"{indent}🚀 转换“文章包” 📦 : {title} ({start + 1}-{end + 1})...")

            try:
                # === 关键：传入页码列表，使用 LeninParser 一次性处理整节，而非逐页解析 ===
                pages_to_process = list(range(start, end + 1))
                if not pages_to_process: continue

                # 调用 parse_chapter_pages
                md_content = parser.parse_chapter_pages(doc, pages_to_process, article_output_dir=article_dir)

                final_content = "---\n" + yaml.dump(front_matter, allow_unicode=True) + "---\n\n" + md_content

                # 写入文件
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(final_content)

            except Exception as e:
                print(f"{indent}❌ 失败: {e}")

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