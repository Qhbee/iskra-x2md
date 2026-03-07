"""
将 ○ (U+25CB) 替换为 〇 (U+3007)，支持两种模式：

1. --all：全部替换
2. --safe（默认）：仅替换前或后邻接汉字数字的 ○，如一九○五、一九○○、一○七师

用法：
  python scripts/utils/replace_circle_zero.py [目录]        # 保险模式
  python scripts/utils/replace_circle_zero.py [目录] --all  # 全部替换
  python scripts/utils/replace_circle_zero.py [目录] --dry  # 仅预览，不写入

默认仅修改 processed/mao 下的 MD，不修改 raw。
"""
import argparse
import sys
from pathlib import Path

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

CIRCLE_25CB = "\u25cb"
ZERO_3007 = "\u3007"
# 汉字数字 + 〇 + ○（○ 用于一九○○ 等连续情况）
NUM_CTX = set("一二三四五六七八九十〇" + CIRCLE_25CB)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_DIR = PROJECT_ROOT / "data/processed/mao/毛泽东选集（1-7卷 静火版）V1.20 2019最新版"
EXTENSIONS = {
    # ".html", 
    # ".htm", 
    # ".xhtml", 
    # ".txt",
    ".md"
}


def replace_safe(text: str) -> str:
    """仅替换前或后邻接汉字数字的 ○"""
    result = []
    for i, c in enumerate(text):
        if c == CIRCLE_25CB:
            prev = text[i - 1] if i > 0 else ""
            nxt = text[i + 1] if i < len(text) - 1 else ""
            if prev in NUM_CTX or nxt in NUM_CTX:
                result.append(ZERO_3007)
            else:
                result.append(c)
        else:
            result.append(c)
    return "".join(result)


def replace_all(text: str) -> str:
    """全部替换"""
    return text.replace(CIRCLE_25CB, ZERO_3007)


def run(base: Path, mode: str, dry_run: bool):
    base = Path(base)
    if not base.exists():
        print(f"❌ 目录不存在: {base}")
        return 1

    replace_fn = replace_all if mode == "all" else replace_safe
    mode_desc = "全部替换" if mode == "all" else "保险模式（仅数字语境）"
    changed = 0

    for path in sorted(base.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in EXTENSIONS:
            continue
        try:
            orig = path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            print(f"⚠️ 读取失败 {path}: {e}")
            continue
        if CIRCLE_25CB not in orig:
            continue
        new_text = replace_fn(orig)
        if new_text != orig:
            changed += 1
            rel = path.relative_to(base) if base in path.parents or path.parent == base else path.name
            print(f"  {'[dry] ' if dry_run else ''}{rel}")
            if not dry_run:
                path.write_text(new_text, encoding="utf-8")

    print(f"\n📂 {base}")
    print(f"   模式: {mode_desc}")
    print(f"   修改: {changed} 个文件" + (" (dry run，未写入)" if dry_run else ""))
    return 0


def main():
    ap = argparse.ArgumentParser(description="○ → 〇 替换")
    ap.add_argument("dir", nargs="?", default=str(DEFAULT_DIR), help="扫描目录")
    ap.add_argument("--all", action="store_true", help="全部替换")
    ap.add_argument("--dry", action="store_true", help="仅预览，不写入")
    args = ap.parse_args()
    mode = "all" if args.all else "safe"
    return run(Path(args.dir), mode, args.dry)


if __name__ == "__main__":
    sys.exit(main())
