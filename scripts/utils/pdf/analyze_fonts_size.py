import fitz
from collections import defaultdict
from pathlib import Path

# ================= 配置 =================
# 自动定位路径
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
INPUT_PDF = PROJECT_ROOT / "data/raw/stalin/斯大林选集_1-4卷_诸夏怀斯社.pdf"

# 采样步长：每隔 20 页采一次样，加快速度
STEP = 20

# =======================================

def analyze_fonts():
    doc = fitz.open(INPUT_PDF)
    print(f"📖 正在分析字体大小（字号）分布: {INPUT_PDF.name}")
    print(f"📄 总页数: {doc.page_count} (采样步长: {STEP})")

    # 存储结构: {size: count}
    font_counts = defaultdict(int)
    # 存储结构: {size: "example text"}
    font_examples = {}

    # 开始采样
    for page_num in range(0, doc.page_count, STEP):
        page = doc[page_num]

        # 获取页面所有文本块 (dict模式包含字体信息)
        blocks = page.get_text("dict")["blocks"]

        for b in blocks:
            if "lines" not in b: continue
            for line in b["lines"]:
                for span in line["spans"]:
                    # 获取字号，保留1位小数 (避免 10.001 和 10.0 算两种)
                    size = round(span["size"], 1)
                    text = span["text"].strip()

                    if not text: continue

                    font_counts[size] += 1

                    # 记录一个稍微长一点的样例，方便辨认
                    if size not in font_examples or len(text) > len(font_examples[size]):
                        font_examples[size] = f"p{page_num + 1} --- " + text[:30]  # 只存页码 + 前30个字

    # --- 输出报告 ---
    print("\n" + "=" * 60)
    print(f"{'字号 (pt)':<10} | {'出现次数':<10} | {'样例文本 (推测用途)'}")
    print("-" * 60)

    # 按字号从大到小排序
    sorted_sizes = sorted(font_counts.keys(), reverse=True)

    for size in sorted_sizes:
        count = font_counts[size]
        example = font_examples.get(size, "")

        # 简单推测用途
        guess = ""
        if count == max(font_counts.values()):
            guess = "<- 正文 (Body)"
        elif size < 10:  # 经验值
            guess = "<- 注脚/页眉 (Footer/Header)"
        elif count < 1000:
            guess = "<- 标题 (Header)"

        print(f"{size:<10} | {count:<10} | {example} {guess}")

    print("=" * 60)
    print("💡 提示：请根据上面的表，决定代码里的 FONT_MAPPING 字典。")


if __name__ == "__main__":
    analyze_fonts()