import fitz  # PyMuPDF
from pathlib import Path

# ================= 🎛️ 配置区域 =================

# 1. 自动定位项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

# 2. 输入文件路径
INPUT_PDF = PROJECT_ROOT / "data/raw/stalin/斯大林选集_1-4卷_诸夏怀斯社.pdf"

# 3. 输出目录 (会自动创建)
OUTPUT_DIR = PROJECT_ROOT / "data/interim/stalin/splits"

# 4. 【核心】切分点列表 (请输入 PDF 阅读器上看到的页码，1-based)
# 例子：[15, 550, 1200]
# 意思是在第15页切一刀，在第550页切一刀，在1200页切一刀。
# 结果会生成 4 个文件：
# Part 1: 1 ~ 14
# Part 2: 15 ~ 549
# Part 3: 550 ~ 1199
# Part 4: 1200 ~ 结尾
CUT_POINTS = [35, 771, 1528, 2221]


# ================= ⚙️ 执行逻辑 =================

def split_pdf():
    # 1. 检查输入
    if not INPUT_PDF.exists():
        print(f"❌ 找不到文件: {INPUT_PDF}")
        return

    # 准备目录
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"📖 打开文件: {INPUT_PDF.name}")
    src_doc = fitz.open(INPUT_PDF)
    total_pages = src_doc.page_count
    print(f"📄 总页数: {total_pages}")

    # 2. 处理切分点
    # 排序并去重
    cuts = sorted(list(set(CUT_POINTS)))

    # 转换为 0-based 索引用于编程
    # 也就是：如果用户说 15页开始，内部索引就是 14
    cut_indices = [p - 1 for p in cuts if 0 < p < total_pages]

    # 构建区间列表：[0, 14, 50, end]
    boundaries = [0] + cut_indices + [total_pages]

    print(f"✂️  准备切分为 {len(boundaries) - 1} 个部分...")

    # 3. 循环切分
    for i in range(len(boundaries) - 1):
        start_page = boundaries[i]
        end_page = boundaries[i + 1]  # 左闭右开区间

        # 创建新 PDF
        new_doc = fitz.open()

        # 插入页面 (这是最快的方法，且保留大部分链接/书签)
        new_doc.insert_pdf(src_doc, from_page=start_page, to_page=end_page - 1)

        # 生成文件名
        # 也就是 human readable 的页码 (start+1)
        part_name = f"{INPUT_PDF.stem}_part{i + 1}_p{start_page + 1}-p{end_page}.pdf"
        save_path = OUTPUT_DIR / part_name

        new_doc.save(save_path)
        print(f"✅ 保存 Part {i + 1}: {part_name} (共 {end_page - start_page} 页)")

        new_doc.close()

    print("\n🎉 全部切分完成！文件在 data/interim/stalin_splits/")


if __name__ == "__main__":
    split_pdf()