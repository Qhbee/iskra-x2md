"""
统计指定目录下所有 md 文件中的五级标题（##### 开头）。
输出：文件路径、行号、标题文本。

用法：
    python scripts/utils/count_h5_headings.py
    python scripts/utils/count_h5_headings.py <目录路径>
"""
import sys
from pathlib import Path

# 避免 Windows 控制台 GBK 输出导致 UnicodeEncodeError
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_DIR = (
    PROJECT_ROOT
    / "data/processed/marx-engels"
    / "马克思恩格斯全集-文字版-带书签"
)


def scan_h5_headings(root: Path) -> list[tuple[Path, int, str]]:
    """扫描目录下所有 md 文件，返回 [(文件路径, 行号, 标题文本), ...]"""
    results = []
    for md_path in root.rglob("*.md"):
        try:
            text = md_path.read_text(encoding="utf-8")
        except Exception as e:
            print(f"[跳过] {md_path}: 读取失败 - {e}", file=sys.stderr)
            continue
        for i, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("##### "):
                title_text = stripped[6:].strip()  # 去掉 "##### "
                results.append((md_path, i, title_text))
    return results


def main() -> None:
    if len(sys.argv) > 1:
        root = Path(sys.argv[1])
    else:
        root = DEFAULT_DIR

    if not root.exists():
        print(f"目录不存在: {root}")
        sys.exit(1)

    results = scan_h5_headings(root)
    total = len(results)

    # 统计
    print(f"目录: {root}")
    print(f"五级标题 (#####) 总数: {total}")
    print("-" * 60)

    if not results:
        print("未找到五级标题。")
        return

    # 按文件分组输出
    by_file: dict[Path, list[tuple[int, str]]] = {}
    for path, line_no, text in results:
        by_file.setdefault(path, []).append((line_no, text))

    for path in sorted(by_file.keys(), key=lambda p: str(p)):
        rel = path.relative_to(root) if root in path.parents or path == root else path
        items = by_file[path]
        print(f"\n【{rel}】 共 {len(items)} 个")
        for line_no, text in items:
            preview = text[:50] + "..." if len(text) > 50 else text
            print(f"  行 {line_no:>6}: {preview}")


if __name__ == "__main__":
    main()
