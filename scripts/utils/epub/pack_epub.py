"""
将解压后的 EPUB 目录打包为 .epub 文件。
mimetype 必须第一个且不压缩，符合 EPUB 规范。

用法：直接运行，使用下方常量。
"""
import sys
import zipfile
from pathlib import Path

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


# ================= 配置 =================
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
INPUT_DIR = PROJECT_ROOT / "data/raw/mao/毛泽东选集（1-7卷 静火版）V1.20 2019最新版"
OUTPUT_EPUB = PROJECT_ROOT / "data/processed/mao/毛泽东选集（1-7卷 静火版）V1.20 2019最新版.epub"
# =======================================


def pack_epub(root: Path, out: Path) -> int:
    if not root.exists():
        print(f"❌ 目录不存在: {root}")
        return 1

    mimetype_path = root / "mimetype"
    if not mimetype_path.is_file():
        print(f"❌ 未找到 mimetype: {mimetype_path}")
        return 1

    out.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        # 1. mimetype 必须第一个，且不压缩
        zf.write(mimetype_path, "mimetype", compress_type=zipfile.ZIP_STORED)

        # 2. META-INF、OEBPS），按路径排序保证可复现
        for top in ("META-INF", "OEBPS"):
            top_path = root / top
            if not top_path.is_dir():
                continue
            for p in sorted(top_path.rglob("*")):
                if p.is_file():
                    arcname = p.relative_to(root).as_posix()
                    zf.write(p, arcname)

    print(f"✅ {out}")
    return 0


def main():
    return pack_epub(INPUT_DIR, OUTPUT_EPUB)


if __name__ == "__main__":
    sys.exit(main())
