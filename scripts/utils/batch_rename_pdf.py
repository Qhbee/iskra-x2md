"""
批量重命名 PDF 文件（马克思、恩格斯等全集）。

用法：
    修改脚本内 EXECUTE = False（侦察）或 True（执行），然后运行：
    python scripts/utils/batch_rename_pdf.py

示例：
    马克思恩格斯全集第二版 文字版 带书签 1上 (马克思恩格斯) (z-library.sk, 1lib.sk, z-lib.sk).pdf
    ➡️ 马克思恩格斯全集 1上.pdf

注意：USE_GIT_MV = True 时使用 git mv 重命名，确保 Git 正确识别变更（Windows 下 Path.rename 可能不被 git 感知）。
"""
import re
import subprocess
import sys
from pathlib import Path

# 避免 Windows 控制台 GBK 输出导致 UnicodeEncodeError
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TARGET_DIR = PROJECT_ROOT / "data/raw/marx-engels/马克思恩格斯全集-文字版-带书签"

# 是否实际执行（True=执行重命名，False=仅侦察）
EXECUTE = False

# 使用 git mv 重命名（确保 Git 正确识别变更，避免 Windows 下 Path.rename 后 git 无反应）
USE_GIT_MV = True


def do_rename(old_path: Path, new_path: Path) -> None:
    """执行重命名，优先使用 git mv 以让 Git 正确识别"""
    if USE_GIT_MV and (PROJECT_ROOT / ".git").exists():
        try:
            subprocess.run(
                ["git", "mv", str(old_path), str(new_path)],
                cwd=PROJECT_ROOT,
                check=True,
                capture_output=True,
            )
            return
        except subprocess.CalledProcessError:
            pass
    old_path.rename(new_path)


def clean_marx_engels_name(old: str) -> str | None:
    """
    将马克思全集类文件名简化为「马克思恩格斯全集 {卷次}.pdf」
    若无法匹配则返回 None。
    """
    if not old.lower().endswith(".pdf"):
        return None
    stem = old[:-4]  # 去掉 .pdf
    # 去除末尾的 (...)(...) 括号组（可能多组）
    stem = re.sub(r"\s*\([^)]*\)(?=\s*\([^)]*\)|\s*$)", "", stem)
    stem = re.sub(r"\s*\([^)]*\)\s*$", "", stem)
    stem = stem.strip()
    # 马克思恩格斯全集第二版 文字版 带书签 1上 → 马克思恩格斯全集 1上
    m = re.match(r"马克思恩格斯全集第二版\s*文字版\s*带书签\s+(.+)", stem)
    if m:
        vol = m.group(1).strip()
        return f"马克思恩格斯全集 {vol}.pdf"
    return None


def main():
    if not TARGET_DIR.exists():
        print(f"❌ 目录不存在: {TARGET_DIR}")
        return 1

    files = sorted(TARGET_DIR.glob("*.pdf"))
    if not files:
        print(f"📂 目录下无 PDF: {TARGET_DIR}")
        return 0

    print(f"📂 目录: {TARGET_DIR}")
    print(f"📄 共 {len(files)} 个 PDF\n")

    renamed = 0
    skipped = []
    for f in files:
        new_name = clean_marx_engels_name(f.name)
        if new_name and new_name != f.name:
            if EXECUTE:
                new_path = f.parent / new_name
                if new_path.exists() and new_path != f:
                    print(f"⚠️️️  跳过（目标已存在）: {f.name} ➡️ {new_name}")
                    skipped.append(f.name)
                    continue
                do_rename(f, new_path)
                print(f"✅ {f.name}")
                print(f"➡️ {new_name}\n")
                renamed += 1
            else:
                print(f"🎯 {f.name}")
                print(f"➡️ {new_name}\n")
                renamed += 1
        else:
            if new_name is None:
                print(f"⏭️  未匹配规则，跳过: {f.name}")

    if not EXECUTE and renamed > 0:
        print("=" * 50)
        print("📢 侦察结束。要执行重命名，请将脚本内 EXECUTE 改为 True 后重新运行。")
    elif EXECUTE:
        print(f"✅ 共重命名 {renamed} 个文件")

    return 0


if __name__ == "__main__":
    sys.exit(main())
