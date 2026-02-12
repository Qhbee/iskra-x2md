import fitz  # PyMuPDF
from pathlib import Path

# ================= 配置区域 =================
# 1. 路径设置 (使用 pathlib 更优雅，且不依赖运行目录)
# 自动定位到项目根目录 (即 scripts 的上一级)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
# 拼接路径 (现在看起来是不是清爽多了？)
INPUT_PDF  = PROJECT_ROOT / "data/raw/stalin/斯大林选集_1-4卷_诸夏怀斯社.pdf"
OUTPUT_PDF = PROJECT_ROOT / "data/interim/stalin/斯大林选集_1-4卷_诸夏怀斯社_ruler.pdf"

# 2. 要测试的页码列表 (直接填 PDF 阅读器上看到的数字，支持多个)
# 例如：想看封面、目录、第52页正文
TEST_PAGES = [2, 3, 5, 52, 88, 93, 192]

# ===========================================

def create_ruler():
    # 1. 检查文件是否存在
    if not INPUT_PDF.exists():
        print(f"❌ 错误：找不到输入文件:\n   {INPUT_PDF}")
        return

    try:
        doc = fitz.open(INPUT_PDF)
        print(f"📖 打开文件成功，共 {doc.page_count} 页")
    except Exception as e:
        print(f"❌ 无法打开 PDF: {e}")
        return

    # 2. 遍历你指定的每一页
    pages_processed = 0

    for page_num in TEST_PAGES:
        # 转换逻辑：用户输入的 52 -> 程序索引 51
        page_idx = page_num - 1

        # 越界检查
        if page_idx < 0 or page_idx >= doc.page_count:
            print(f"⚠️ 跳过第 {page_num} 页：页码超出范围 (1-{doc.page_count})")
            continue

        page = doc[page_idx]

        # --- 画标尺逻辑 ---
        shape = page.new_shape()

        # 红色线，蓝色字
        red = (1, 0, 0)
        blue = (0, 0, 1)

        # 在 x=40 到 x=120 之间画线，步长 10
        for x in range(40, 120, 10):
            # 画竖线
            shape.draw_line((x, 0), (x, page.rect.height))
            shape.finish(color=red, width=0.5)

            # 写坐标数字 (字号8)
            page.insert_text((x - 2, page.rect.height - x + 20), f"x={x}", color=blue, fontsize=8)

        # 在 y=20 到 y=120 之间画线，步长 10
        for y in range(20, 120, 10):
            # 画横线
            shape.draw_line((0, y), (page.rect.width, y))
            shape.finish(color=red, width=0.5)

            # 写坐标数字 (字号8)
            page.insert_text((10, y - 2), f"y={y}", color=blue, fontsize=8)

        shape.commit()
        pages_processed += 1
        print(f"✅ 已在第 {page_num} 页画上标尺")

    # 3. 保存文件
    if pages_processed > 0:
        # 自动创建父文件夹 (如果不存在)
        OUTPUT_PDF.parent.mkdir(parents=True, exist_ok=True)

        try:
            doc.save(OUTPUT_PDF)
            print(f"\n🎉 全部完成！请打开以下文件查看红线：\n   {OUTPUT_PDF}")
        except Exception as e:
            print(f"❌ 保存失败: {e}")
    else:
        print("\n⚠️ 没有处理任何页面，未保存文件。")


if __name__ == "__main__":
    create_ruler()