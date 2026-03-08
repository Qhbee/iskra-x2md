"""
探测 EPUB 中指定 class 的每一次出现，打印完整行，便于查看 class 如何组合使用。

用法：
    直接运行：使用下方 DEFAULT_CLASS、DEFAULT_DIR
    命令行：  python probe_one_css_class.py [class名] [EPUB解压目录]
"""
import re
import sys
from pathlib import Path

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


# ================= 配置 =================
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DEFAULT_CLASS = "a0"
DEFAULT_DIR = PROJECT_ROOT / "data/raw/mao/毛泽东选集（1-7卷 静火版）V1.20 2019最新版"
# =======================================


def _find_html_files(base: Path) -> list[Path]:
    """查找所有 HTML/XHTML 文件"""
    exts = {".html", ".htm", ".xhtml"}
    return sorted(p for p in base.rglob("*") if p.suffix.lower() in exts and p.is_file())


def _class_in_attr(class_attr: str, target: str) -> int:
    """检查 target 是否在 class 属性中，返回出现次数。按整词匹配。"""
    tokens = class_attr.split()
    return sum(1 for t in tokens if t.strip() == target)


def probe_one_class(base: Path, target_class: str) -> int:
    if not base.exists():
        print(f"❌ 目录不存在: {base}")
        return 1

    html_files = _find_html_files(base)
    if not html_files:
        print(f"❌ 未找到 HTML 文件")
        return 1

    # class="xxx" 或 class='xxx'
    class_re = re.compile(r'\bclass\s*=\s*["\']([^"\']+)["\']', re.I)
    total = 0

    print(f"📖 {base.name}")
    print(f"🔍 探测 class: .{target_class}\n")
    print("=" * 80)

    for hp in html_files:
        try:
            lines = hp.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception as e:
            print(f"⚠️ 读取失败 {hp}: {e}")
            continue

        rel = hp.relative_to(base) if base in hp.parents or hp.parent == base else hp.name
        rel_str = str(rel).replace("\\", "/")
        file_has_match = False

        for i, line in enumerate(lines, 1):
            line_count = 0
            for m in class_re.finditer(line):
                line_count += _class_in_attr(m.group(1), target_class)
            if line_count > 0:
                if not file_has_match:
                    print(f"\n--- {rel_str} ---")
                    file_has_match = True
                total += line_count
                stripped = line.strip()
                suffix = f"  (x{line_count})" if line_count > 1 else ""
                print(f"  {i:4d} | {stripped}{suffix}")

        if file_has_match:
            print()

    print("=" * 80)
    print(f"共 {total} 处 .{target_class}")
    return 0


def main():
    # 命令行参数覆盖默认值
    target = sys.argv[1].strip() if len(sys.argv) >= 2 else DEFAULT_CLASS
    base = Path(sys.argv[2]) if len(sys.argv) >= 3 else DEFAULT_DIR

    if not target:
        print("❌ class 名不能为空")
        return 1
    if base.suffix.lower() == ".epub":
        print("⚠️ 请传入解压后的目录，而非 .epub 文件")
        return 1

    return probe_one_class(base, target)


if __name__ == "__main__":
    sys.exit(main())
