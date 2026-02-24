"""
探测 PDF 某一页的图片：原始格式、bbox、是否被裁剪、是否切分/丢失
用法：修改 TARGET_PAGE，运行查看 PyMuPDF 如何提取图片
"""
import fitz
from pathlib import Path

# ================= 配置 =================
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
INPUT_PDF = PROJECT_ROOT / "data/raw/lenin/列宁全集（版本II-文字版）（完整书签版）/列宁全集 第1卷（1893年—1894年）.pdf"

# 要探测的页码（1-based）
TARGET_PAGE = 4

# 是否保存图片到本地（用正确扩展名）便于对比
SAVE_IMAGES = True
OUTPUT_DIR = PROJECT_ROOT / "data/interim/lenin/probe_images"

# 模拟 lenin_parser 的裁剪框（用于对比哪些图片会被切掉）
MARGIN_TOP_CUT = 110
MARGIN_BOTTOM_CUT = 520

# =======================================


def detect_image_format(data: bytes) -> str:
    """从二进制头检测图片格式"""
    if not data or len(data) < 8:
        return "unknown"
    if data[:2] == b"\xff\xd8":
        return "jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if data[:2] == b"BM":
        return "bmp"
    if data[:4] in (b"II*\x00", b"MM\x00*"):
        return "tiff"
    return "unknown"


def main():
    if not INPUT_PDF.exists():
        print(f"❌ 找不到: {INPUT_PDF}")
        return

    doc = fitz.open(INPUT_PDF)
    if TARGET_PAGE < 1 or TARGET_PAGE > doc.page_count:
        print(f"⚠️ 页码 {TARGET_PAGE} 超出范围 (1-{doc.page_count})")
        doc.close()
        return

    page = doc[TARGET_PAGE - 1]
    page_rect = page.rect
    clip_rect = fitz.Rect(0, MARGIN_TOP_CUT, page_rect.width, min(MARGIN_BOTTOM_CUT, page_rect.height))

    if SAVE_IMAGES:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        print(f"📁 图片将保存到: {OUTPUT_DIR}\n")

    print("=" * 90)
    print(f"  📃 第 {TARGET_PAGE} 页 · 图片探测")
    print("=" * 90)
    print(f"  整页 bbox: y=0 ~ {page_rect.height:.1f}")
    print(f"  lenin_parser clip: y={MARGIN_TOP_CUT} ~ {MARGIN_BOTTOM_CUT} (超出此范围会被裁剪)")
    print()

    # --- 1. get_text("dict") 的图片块 ---
    data_dict = page.get_text("dict", clip=page.rect)  # 不裁剪，看全页
    data_dict_clipped = page.get_text("dict", clip=clip_rect)  # 模拟 parser 的裁剪

    img_blocks_full = [b for b in data_dict.get("blocks", []) if "image" in b or b.get("type") == 1]
    img_blocks_clipped = [b for b in data_dict_clipped.get("blocks", []) if "image" in b or b.get("type") == 1]

    print("--- 1. get_text('dict') 图片块（按页面出现顺序）---")
    print(f"  全页 clip: {len(img_blocks_full)} 个图片块")
    print(f"  parser clip: {len(img_blocks_clipped)} 个图片块")
    if len(img_blocks_full) != len(img_blocks_clipped):
        print(f"  ⚠️ 裁剪后少了 {len(img_blocks_full) - len(img_blocks_clipped)} 个!")
    print()

    for i, block in enumerate(img_blocks_full):
        bbox = block.get("bbox", (0, 0, 0, 0))
        x0, y0, x1, y1 = bbox
        img_data = block.get("image", b"")
        ext = block.get("ext", "?")
        width = block.get("width", 0)
        height = block.get("height", 0)
        size = block.get("size", len(img_data))

        detected = detect_image_format(img_data)
        r = fitz.Rect(bbox)
        in_clip = clip_rect.intersects(r)
        fully_in_clip = clip_rect.contains(r)

        print(f"  Block[{i}] bbox=({x0:.0f},{y0:.0f},{x1:.0f},{y1:.0f}) w×h={width}×{height} size={len(img_data)} bytes")
        print(f"           ext={ext} (PyMuPDF) | 头部检测={detected}")
        print(f"           在 parser clip 内: {'完全' if fully_in_clip else ('部分' if in_clip else '否，会丢失')}")

        if SAVE_IMAGES and img_data:
            suf = ext if ext and ext != "?" else detected
            if suf == "unknown":
                suf = "bin"
            path = OUTPUT_DIR / f"p{TARGET_PAGE}_dict_{i}.{suf}"
            path.write_bytes(img_data)
            print(f"           已保存: {path.name}")

        print()

    # --- 2. get_images() + extract_image：PDF 内嵌图片（xref）---
    print("--- 2. page.get_images() 引用图片（xref）---")
    img_refs = page.get_images()
    print(f"  共 {len(img_refs)} 个图片引用 (xref)")

    for i, item in enumerate(img_refs):
        xref = item[0]
        smask = item[1]
        try:
            info = doc.extract_image(xref)
            ext = info.get("ext", "?")
            w = info.get("width", 0)
            h = info.get("height", 0)
            img_bytes = info.get("image", b"")
            print(f"  xref={xref} smask={smask} ext={ext} {w}×{h} size={len(img_bytes)} bytes")

            if SAVE_IMAGES and img_bytes:
                suf = ext if ext else detect_image_format(img_bytes)
                path = OUTPUT_DIR / f"p{TARGET_PAGE}_xref_{xref}.{suf}"
                path.write_bytes(img_bytes)
                print(f"    已保存: {path.name}")
        except Exception as e:
            print(f"  xref={xref} 提取失败: {e}")
        print()

    # --- 3. rawdict（parser 实际用的）---
    print("--- 3. get_text('rawdict') 图片块（parser 实际使用）---")
    data_raw = page.get_text("rawdict", clip=clip_rect)
    img_blocks_raw = [b for b in data_raw.get("blocks", []) if "image" in b]

    print(f"  parser clip 下 rawdict: {len(img_blocks_raw)} 个图片块")

    for i, block in enumerate(img_blocks_raw):
        bbox = block.get("bbox", (0, 0, 0, 0))
        img_data = block.get("image", b"")
        detected = detect_image_format(img_data)
        ext = block.get("ext", "?")
        print(f"  Block[{i}] bbox=({bbox[0]:.0f},{bbox[1]:.0f},{bbox[2]:.0f},{bbox[3]:.0f}) "
              f"ext={ext} 头部={detected} size={len(img_data)} bytes")
        if "ext" not in block or not block["ext"]:
            print(f"           ⚠️ rawdict 可能无 ext，parser 统一存 .png 可能不对（若原为 jpeg）")
    print()

    doc.close()
    print("✅ 完成")


if __name__ == "__main__":
    main()
