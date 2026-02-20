import fitz  # PyMuPDF
import pymupdf4llm
import re
import yaml
from pathlib import Path

# ==================== 📜 解析规则 ====================

# 规则 A (到达指定层级)： 如果当前层级 == SPLIT_LEVEL (比如 5) -> 📄 变成文件。
# 规则 B (还没到层级，但没子级了)： 如果当前层级 < SPLIT_LEVEL (比如 3)，但它下面没有子节点了 -> 📄 变成文件 (比如“口号”、“斯大林像”的问题)。
# 规则 C (还没到层级，且有子级)： -> 📂 变成文件夹 (比如“正文”、“选自全集第一卷”)。
# 规则 D (超过层级)： -> 🔹 变成内容标题。

# ==================== 🎛️ 仪表盘 ====================

# 1. 路径配置 (定位到项目根目录)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
INPUT_PDF = PROJECT_ROOT / "data/raw/stalin/斯大林选集_1-4卷_诸夏怀斯社.pdf"
OUTPUT_DIR = PROJECT_ROOT / "data/processed/stalin/斯大林选集_1-4卷_诸夏怀斯社"

# 2. 安全模式 (True=侦察, False=执行)
# 建议先用 True 跑一次，检查是否符合预期结构。
# True = 只打印书签结构，不生成文件。
# False = 正式开跑，生成 Markdown 文件。
DRY_RUN = True

# 3. 核心切分层级 (SPLIT_LEVEL)
# 你的PDF里，真正的文章在 L5。
# 逻辑：到达 L5 必切分；不到 L5 但没有子节点的，也切分。
SPLIT_LEVEL = 5

# 4. 页面裁剪 (由 measure_margin.py 测出来)
# (左, 上, 右, 下)
# 斯大林选集：顶部切 82 去页眉，底部留 0 保注脚
MARGINS = (0, 82, 0, 0)

# 5. 黑名单 (遇到这些书签先记录下来，特别是用页码定位，最后再删掉)
BLACKLIST = ["示例黑名单", "斯大林历史档案选", "选自全集档案附卷"]


# ==================== ⚙️ 智能引擎 (黑名单修复版) ====================

def clean_filename(text):
    """文件名清洗，把不能做文件名的字符(如?, :)换成下划线"""
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
    skipping_level = -1  # 用于处理黑名单的子节点

    for item in toc:
        lvl, title, page = item[0], item[1], item[2]

        is_blacklisted = False

        # 1. 递归黑名单逻辑 (如果父级是黑名单，子级也是)
        if skipping_level != -1:
            if lvl > skipping_level:
                is_blacklisted = True
            else:
                skipping_level = -1  # 归位

        # 2. 自身黑名单逻辑
        if skipping_level == -1 and any(bad in title for bad in BLACKLIST):
            is_blacklisted = True
            skipping_level = lvl

        # PyMuPDF页码从0开始，PDF书签从1开始 -> 减1
        full_list.append({
            "level": lvl,
            "title": title.strip(),
            "start": page - 1,
            "end": -1,  # 待计算
            "is_blacklisted": is_blacklisted,  # 关键标记
            "has_children": False  # 默认为 False，稍后计算
        })

    # --- 第二步：计算 has_children ---
    for i in range(len(full_list) - 1):
        # 如果 下一个元素 的 level > 当前元素 level，说明当前元素有子节点
        if full_list[i + 1]['level'] > full_list[i]['level']:
            full_list[i]['has_children'] = True

    # --- 第三步：计算页码 (使用包含黑名单的全量列表作为参考) ---
    for i in range(len(full_list)):
        current = full_list[i]

        # 寻找下一个“同级或更高级”的节点 (作为物理边界)
        # 即使那个节点是黑名单，它也是物理存在的，必须作为边界！
        boundary_index = -1
        for j in range(i + 1, len(full_list)):
            if full_list[j]['level'] <= current['level']:
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
    final_toc = [item for item in full_list if not item['is_blacklisted']]

    return final_toc


def main():
    print(f"📖 读取: {INPUT_PDF.name}")
    try:
        doc = fitz.open(INPUT_PDF)
    except Exception as e:
        print(f"❌ 无法打开: {e}")
        return

    toc = extract_toc_structure(doc)
    print(f"🔍 有效书签: {len(toc)} 个 (SPLIT_LEVEL={SPLIT_LEVEL})\n")

    # 路径栈和标题栈
    path_stack = {0: OUTPUT_DIR}
    title_stack = {}

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

        indent = "  " * (lvl - 1)

        # ========== 🧠 智能判定逻辑 ==========

        # 判定 1: 这是一个文件吗？
        # 条件 A: 刚好到达切分层级 (L5)
        # 条件 B: 还没到层级 (L3, L4)，但是它没有子节点了 (光杆司令，如"口号")
        is_file = (lvl == SPLIT_LEVEL) or (lvl < SPLIT_LEVEL and not has_children)

        # 判定 2: 这是一个文件夹吗？
        # 条件: 还没到层级，且有子节点 (容器，如"正文")
        is_folder = (lvl < SPLIT_LEVEL and has_children)

        # 判定 3: 它是文件里的标题吗？
        # 条件: 超过了层级 (L6+)
        is_content = (lvl > SPLIT_LEVEL)

        # ========== 🚧 执行动作 ==========

        # --- 模式 A: 侦察模式 (DRY_RUN = True) ---

        if DRY_RUN:
            if is_folder:
                print(f"{indent}📂 {title}")
            elif is_file:
                # 区分一下是因为到了层级切分，还是因为是孤儿节点切分
                reason = "[层级达标]" if lvl == SPLIT_LEVEL else "[无子节点]"
                page_count = end - start + 1
                # 重点关注这里的页数变化
                print(f"{indent}📄 {title} {reason} (p{start + 1}-p{end + 1}, 共{page_count}页)")
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
            file_name = f"{clean_filename(title)}.md"
            file_path = parent / file_name

            # 确保父目录存在 (防止跳级情况)
            if not parent.exists():
                parent.mkdir(parents=True, exist_ok=True)

            # YAML
            cats = [title_stack[k] for k in sorted(title_stack.keys()) if k < lvl]
            front_matter = {
                "title": title,
                "order": start + 1,
                "category": "/".join(cats),
                "book": INPUT_PDF.stem
            }

            print(f"{indent}🚀 转换: {title} ({start + 1}-{end + 1})...")

            try:
                pages = list(range(start, end + 1))
                if pages:
                    md_text = pymupdf4llm.to_markdown(
                        doc,
                        pages=pages,
                        margins=MARGINS,
                        show_progress=False
                    )
                    # 简单清洗一下图片标记（可选）
                    # md_text = md_text.replace("![]()", "")

                    final_content = "---\n" + yaml.dump(front_matter, allow_unicode=True) + "---\n\n" + md_text

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