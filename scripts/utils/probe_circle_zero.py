"""
探测 ○ (U+25CB) 与 〇 (U+3007) 在毛选解析 MD 目录中的出现位置。

区别：
- ○ U+25CB WHITE CIRCLE：几何符号，用于隐私遮蔽（如○○○）、列表标记
- 〇 U+3007 IDEOGRAPHIC NUMBER ZERO：中文数字零，如二〇〇九年、一百〇八

用法：python scripts/utils/probe_circle_zero.py [目录]
默认扫描毛选解析 MD 目录
"""
import sys
from pathlib import Path

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# U+25CB ○ 几何空心圆
CIRCLE_25CB = "\u25cb"
# U+3007 〇 中文数字零
ZERO_3007 = "\u3007"

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_DIR = PROJECT_ROOT / "data/processed/mao/毛泽东选集（1-7卷 静火版）V1.20 2019最新版"
EXTENSIONS = {
    # ".html",
    # ".htm",
    # ".xhtml",
    # ".txt",
    ".md"
}


def probe(base: Path):
    base = Path(base)
    if not base.exists():
        print(f"❌ 目录不存在: {base}")
        return 1

    found_25cb = []  # (path, line_no, line, indices)
    found_3007 = []  # (path, line_no, line, indices)

    for path in sorted(base.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in EXTENSIONS:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            print(f"⚠️ 读取失败 {path}: {e}")
            continue
        rel = path.relative_to(base) if base in path.parents or path.parent == base else path.name
        for i, line in enumerate(text.splitlines(), 1):
            idx_25cb = [j for j, c in enumerate(line) if c == CIRCLE_25CB]
            idx_3007 = [j for j, c in enumerate(line) if c == ZERO_3007]
            if idx_25cb:
                found_25cb.append((str(rel), i, line.strip(), idx_25cb))
            if idx_3007:
                found_3007.append((str(rel), i, line.strip(), idx_3007))

    # 输出
    print(f"📂 扫描: {base}")
    print()
    print("=" * 70)
    print(f"【○ U+25CB WHITE CIRCLE】共 {len(found_25cb)} 处")
    print("=" * 70)
    for rel, ln, content, _ in found_25cb[:100]:
        preview = content[:150] + "…" if len(content) > 150 else content
        print(f"  {rel}:{ln}  {preview}")
    if len(found_25cb) > 100:
        print(f"  ... 还有 {len(found_25cb) - 100} 处")

    print()
    print("=" * 70)
    print(f"【〇 U+3007 IDEOGRAPHIC NUMBER ZERO】共 {len(found_3007)} 处")
    print("=" * 70)
    for rel, ln, content, _ in found_3007[:100]:
        preview = content[:150] + "…" if len(content) > 150 else content
        print(f"  {rel}:{ln}  {preview}")
    if len(found_3007) > 100:
        print(f"  ... 还有 {len(found_3007) - 100} 处")

    print()
    print("=" * 70)
    print("【说明】")
    print("  ○ U+25CB：几何符号，隐私遮蔽、列表等")
    print(" 〇 U+3007：中文数字零，如二〇〇九年")
    print("  若文中表示年份/数字的「零」误用了 ○，可考虑替换为 〇")
    print("  若为隐私遮蔽（○○○）或列表符号，应保留 ○")
    return 0


def main():
    base = Path(sys.argv[1]) if len(sys.argv) >= 2 else DEFAULT_DIR
    return probe(base)


if __name__ == "__main__":
    sys.exit(main())
