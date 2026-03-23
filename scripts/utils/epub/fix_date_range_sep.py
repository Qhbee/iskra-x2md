#!/usr/bin/env python3
"""
探测并修复日期范围分隔符格式问题。

规则：几年几月几日-几年几月几日、几年几月-几年几月、几年-几年、几月几日-几月几日 等，
中间应统一为一个 em dash（—），而非 ~、～、——、-、－ 等。

注意：GB/T 15834-1995（旧标）和 GB/T 15834-2011（新标）
1995 旧标
    旧标规定：连接号有四种形式：
        短横线 -（半字线）
        一字线 —
        浪纹线 ～
        长横线 ——（占两个字位置，外形与破折号相同）
    用法模糊性：旧标虽然列出了这四种形式，但没有严格规定哪种形式专门用于时间起止。因此，在 2011 年前的出版物中，常能看到用两字线（——）来表示时间跨度。
2011 新标
    新标为了解决上述混淆，做了重大修改：取消了两字线作为连接号，明确删除了连接号中的“长横线（两字线）”形式。
    明确分工：
        破折号（——）：只用于标示注释、补充说明或语意转折（占两个字）。
    连接号：只保留三种形式，并严格分工：
        短横线 -：用于化合物名、电话号码等。
        一字线 —：专门用于标示时间、地点、数目的起止。
        浪纹线 ～：专门用于标示数值范围（特别是阿拉伯数字或易产生歧义时）。
结论：依据现行国标（2011），用一字线（—）最标准，不能用两字线（——）因为它现在只能是破折号，不能表示时间跨度。

但是，引用、整理或复刻历史文献时，最好“原样保留”。
如果原始文献中用了两字线，在引用时不应擅自修改为一字线或浪纹线，以尊重历史原貌和文献的真实性。
标注：如果是学术论文或严谨的整理工作，通常会在凡例中说明：“本书标点符号用法原则上依从现行国家标准，但引用历史文献时保留原貌。”

用法：修改 DRY_RUN、DEFAULT_ROOT 常量后直接运行。
"""

import re
import sys
from pathlib import Path

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

DEFAULT_ROOT = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "data/raw/mao/毛泽东选集全七卷（官方、静火、润之赤旗三合一版）"
)
DRY_RUN = True  # True=只探测不修改，False=执行修改

EM_DASH = "—"  # U+2014，目标分隔符
# 需替换的分隔符：~ ～ —— - －
BAD_SEPS = r"[~～－\-]|——"

# 日期部分：阿拉伯数字或中文数字 + 年/月/日，可含小数点如 1908.11.19
# 〇 U+3007 为中文数字零
NUM_OR_CJK = r"[\d\u4e00-\u9fff\u3007零一二三四五六七八九十百千.]+"
# 完整日期：几年几月几日、几年几月、几年、几月几日、YYYY.MM.DD、YYYY.MM、带空格的 1902 年 10 月 12 日、简写 一九〇七
# 四年份简写仅匹配数字及中文数字字符，避免误匹配「主义性质——垄断资本」等
YEAR_DIGITS = r"[\d一二三四五六七八九〇零十百千]"
DATE = (
    rf"{NUM_OR_CJK}\s*年(?:\s*{NUM_OR_CJK}\s*月)?(?:\s*{NUM_OR_CJK}\s*日)?|"  # 几年几月几日
    rf"{NUM_OR_CJK}\s*月\s*{NUM_OR_CJK}\s*日|"  # 几月几日
    r"\d{4}\.\d{1,2}\.\d{1,2}|"  # 1908.11.19
    r"\d{4}\.\d{1,2}|"  # 1956.06（仅年+月，无日）
    rf"(?:{YEAR_DIGITS}){{4}}"  # 一九〇七、一九七一、 1956（四年份简写）（连续四个「年份用字」（含阿拉伯数字）
)

# 日期 + 错误分隔符 + 日期
PAT = re.compile(rf"({DATE})({BAD_SEPS})({DATE})")


def find_issues(text: str) -> list[tuple[int, str, str]]:
    """返回 [(start, 原片段, 修复后), ...]"""
    issues = []
    for m in PAT.finditer(text):
        start, end1, sep, end2 = m.start(), m.group(1), m.group(2), m.group(3)
        fixed = f"{end1}{EM_DASH}{end2}"
        if m.group(0) != fixed:
            issues.append((start, m.group(0), fixed))
    return issues


def fix_text(text: str) -> tuple[str, list[tuple[int, str, str]]]:
    """替换并返回 (新文本, issues)"""
    issues = find_issues(text)
    if not issues:
        return text, []
    result = text
    for start, orig, fixed in reversed(issues):
        result = result[:start] + fixed + result[start + len(orig) :]
    return result, issues


def probe_xhtml(path: Path) -> list[tuple[int, str, str, str]]:
    """返回 [(行号, 原片段, 修复后, 上下文), ...]"""
    text = path.read_text(encoding="utf-8")
    lines = text.split("\n")
    results = []
    offset = 0
    for line_no, line in enumerate(lines, 1):
        for start, orig, fixed in find_issues(line):
            ctx_start = max(0, start - 25)
            ctx_end = min(len(line), start + len(orig) + 25)
            ctx = line[ctx_start:ctx_end]
            results.append((line_no, orig, fixed, ctx))
        offset += len(line) + 1
    return results


def fix_xhtml(path: Path) -> list[tuple[int, str, str]]:
    """修复并返回 [(行号, 原片段, 修复后), ...]"""
    text = path.read_text(encoding="utf-8")
    new_text, issues = fix_text(text)
    if not issues:
        return []
    line_offsets = [0]
    for line in text.split("\n"):
        line_offsets.append(line_offsets[-1] + len(line) + 1)
    results = []
    for start, orig, fixed in issues:
        line_no = 1
        for i in range(len(line_offsets) - 1):
            if line_offsets[i] <= start < line_offsets[i + 1]:
                line_no = i + 1
                break
        results.append((line_no, orig, fixed))
    path.write_text(new_text, encoding="utf-8")
    return results


def probe_toc_ncx(path: Path) -> list[tuple[str, str, str]]:
    """探测 toc.ncx"""
    text = path.read_text(encoding="utf-8")
    results = []
    for m in re.finditer(r"<text>([^<]*)</text>", text):
        for _, orig, fixed in find_issues(m.group(1)):
            results.append(("<text>", orig, fixed))
    return results


def fix_toc_ncx(path: Path) -> list[tuple[str, str, str]]:
    """修复 toc.ncx"""
    text = path.read_text(encoding="utf-8")
    results = []

    def repl(m: re.Match) -> str:
        content = m.group(1)
        new_content, issues = fix_text(content)
        for _, orig, fixed in issues:
            results.append(("<text>", orig, fixed))
        return f"<text>{new_content}</text>"

    new_text = re.sub(r"<text>([^<]*)</text>", repl, text)
    if results:
        path.write_text(new_text, encoding="utf-8")
    return results


def main() -> int:
    root = DEFAULT_ROOT.resolve()
    if not root.is_dir():
        print(f"错误：{root} 不是目录", flush=True)
        return 1

    text_dir = root / "OEBPS" / "Text"
    toc_path = root / "toc.ncx"
    if not text_dir.exists():
        print(f"错误：未找到 {text_dir}", flush=True)
        return 1

    print(f"目录: {root}")
    print(f"模式: {'探测（DRY_RUN=True，不修改）' if DRY_RUN else '执行修复'}\n")

    total = 0

    print("=== OEBPS/Text/*.xhtml ===")
    for f in sorted(text_dir.glob("*.xhtml")):
        if DRY_RUN:
            items = probe_xhtml(f)
            for line_no, orig, fixed, ctx in items:
                total += 1
                print(f"\n  {f.name}  L{line_no}")
                print(f"    原: {repr(orig)}")
                print(f"    改: {repr(fixed)}")
                print(f"    上下文: {repr(ctx)}")
        else:
            items = fix_xhtml(f)
            for line_no, orig, fixed in items:
                total += 1
                print(f"\n  {f.name}  L{line_no}")
                print(f"    {repr(orig)} → {repr(fixed)}")

    print("\n=== toc.ncx ===")
    if toc_path.exists():
        if DRY_RUN:
            items = probe_toc_ncx(toc_path)
        else:
            items = fix_toc_ncx(toc_path)
        for loc, orig, fixed in items:
            total += 1
            print(f"\n  {loc}")
            print(f"    原: {repr(orig)}")
            print(f"    改: {repr(fixed)}")

    print(f"\n--- 汇总 ---")
    print(f"  共 {total} 处")
    if not DRY_RUN and total > 0:
        print("  已保存修改")
    return 0


if __name__ == "__main__":
    sys.exit(main())
