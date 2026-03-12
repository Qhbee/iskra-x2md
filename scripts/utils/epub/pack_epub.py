"""
将解压后的 EPUB 目录打包为 .epub 文件。
mimetype 必须第一个且不压缩，符合 EPUB 规范。

通用逻辑：自动打包根目录下所有内容，兼容多种结构：
- content.opf 在根目录或 OEBPS/、EPUB/ 等子目录
- OEBPS / EPUB / 其他目录名均可
- 不依赖固定目录结构，由 container.xml 指向的路径决定

用法：直接运行，使用下方默认目录常量。或 python pack_epub.py <输入目录> <输出.epub>
"""
import sys
import zipfile
from pathlib import Path

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


# ================= 配置 =================
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
INPUT_DIR = PROJECT_ROOT / "data/raw/mao/毛泽东选集全七卷（官方、静火、润之赤旗三合一版）"
OUTPUT_EPUB = PROJECT_ROOT / "data/processed/mao/毛泽东选集全七卷（官方、静火、润之赤旗三合一版）.epub"
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
        # 1. mimetype 必须第一个，且不压缩（EPUB OCF 强制要求）
        zf.write(mimetype_path, "mimetype", compress_type=zipfile.ZIP_STORED)

        # 2. 根目录下其余所有内容（文件 + 目录），按路径排序保证可复现
        # 兼容：content.opf 在根 / OEBPS/ / EPUB/；OEBPS、EPUB 等任意目录名
        entries = sorted(root.iterdir())
        for p in entries:
            if p.name == "mimetype":
                continue
            if p.is_file():
                zf.write(p, p.name)
            else:
                for fp in sorted(p.rglob("*")):
                    if fp.is_file():
                        arcname = fp.relative_to(root).as_posix()
                        zf.write(fp, arcname)

    print(f"✅ {out}")
    return 0


def main():
    if len(sys.argv) >= 3:
        return pack_epub(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve())
    return pack_epub(INPUT_DIR, OUTPUT_EPUB)


if __name__ == "__main__":
    sys.exit(main())
