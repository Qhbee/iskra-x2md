"""
比较两个 Markdown 文件是否有差异，若有则标出差异位置。
用法：
    python scripts/utils/compare_md.py <file1> <file2>
    python scripts/utils/compare_md.py              # 使用默认路径（index.bak.md vs index.md）
    python scripts/utils/compare_md.py --init       # 若 file1 不存在，从 file2 复制创建后再比较
"""
import difflib
import io
import sys
from pathlib import Path

# 避免 Windows 控制台 GBK 输出导致 UnicodeEncodeError
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# 默认目录：列宁全集第1卷 -> 什么是"人民之友"...
DEFAULT_DIR = (
    PROJECT_ROOT
    / "data/processed/lenin"
    / "列宁全集（版本II-文字版）（完整书签版）"
    / "列宁全集 第1卷（1893年—1894年）"
    / '什么是“人民之友”以及 他们如何攻击社会民主党人？'
)
DEFAULT_FILE_A = DEFAULT_DIR / "index.bak.md"
DEFAULT_FILE_B = DEFAULT_DIR / "index.md"


def load_lines(path: Path) -> tuple[list[str], str | None]:
    """读取文件行，返回 (行列表, 错误信息)"""
    try:
        text = path.read_text(encoding="utf-8")
        return text.splitlines(keepends=True), None
    except FileNotFoundError:
        return [], f"文件不存在: {path}"
    except Exception as e:
        return [], f"读取失败: {e}"


def compare_files(path_a: Path, path_b: Path, init_if_missing: bool = False) -> None:
    """比较两个文件，输出差异信息。若 init_if_missing 且 path_a 不存在、path_b 存在，则复制 path_b→path_a 后比较。"""
    lines_a, err_a = load_lines(path_a)
    lines_b, err_b = load_lines(path_b)

    if err_a and init_if_missing and not err_b:
        import shutil

        try:
            shutil.copy2(path_b, path_a)
            print(f"已从 {path_b.name} 复制创建 {path_a.name}，作为备份基准。\n")
            lines_a, err_a = load_lines(path_a)
        except Exception as e:
            print(f"复制失败: {e}")
            return

    if err_a:
        print(err_a)
        if init_if_missing and "不存在" in str(err_a):
            print("提示: 使用 --init 可在 file1 不存在时，从 file2 复制创建。")
        return
    if err_b:
        print(err_b)
        return

    print(f"文件 A: {path_a}")
    print(f"文件 B: {path_b}")
    print(f"A 行数: {len(lines_a)}, B 行数: {len(lines_b)}")
    print("-" * 60)

    if lines_a == lines_b:
        print("结果: 两个文件完全相同，无差异。")
        return

    print("结果: 存在差异。差异位置如下：\n")

    # 逐行对比，标出差异行
    diff = list(difflib.unified_diff(lines_a, lines_b, fromfile=str(path_a.name), tofile=str(path_b.name), lineterm=""))

    if not diff:
        # unified_diff 有时对完全相同行返回空
        print("（逐行比较有差异，但 unified diff 无输出，可能为编码/换行差异）")
        return

    # 解析 diff 输出，整理成更易读的摘要
    changed_blocks = []
    current_block = []
    for line in diff:
        if line.startswith("@@"):
            if current_block:
                changed_blocks.append(current_block)
            current_block = [line]
        elif current_block and line and not line.startswith("---") and not line.startswith("+++"):
            current_block.append(line)

    if current_block:
        changed_blocks.append(current_block)

    # 输出差异行号与上下文
    print("【差异概要】")
    for i, block in enumerate(changed_blocks, 1):
        if not block:
            continue
        header = block[0]
        # 解析 @@ -start_a,count_a +start_b,count_b @@
        if header.startswith("@@"):
            print(f"\n--- 差异块 {i} ---")
            print(header)
            for ln in block[1:11]:  # 每块最多显示 10 行
                print(ln.rstrip())
            if len(block) > 11:
                print(f"... 省略 {len(block) - 11} 行")

    # 完整 unified diff（可选，便于复制到 patch）
    print("\n" + "=" * 60)
    print("【完整 unified diff】（前 80 行）")
    full_diff = list(
        difflib.unified_diff(
            lines_a,
            lines_b,
            fromfile=str(path_a.name),
            tofile=str(path_b.name),
            lineterm="",
        )
    )
    for ln in full_diff[:80]:
        print(ln)
    if len(full_diff) > 80:
        print(f"... 共 {len(full_diff)} 行 diff，已省略后续")


def main():
    if len(sys.argv) >= 3:
        path_a = Path(sys.argv[1])
        path_b = Path(sys.argv[2])
    else:
        path_a = DEFAULT_FILE_A
        path_b = DEFAULT_FILE_B
        print("未指定参数，使用默认路径。")
        print("用法: python compare_md.py <file1> <file2>\n")

    compare_files(path_a, path_b)


if __name__ == "__main__":
    main()
