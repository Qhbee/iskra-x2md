#!/usr/bin/env python3
"""
启发式规范化 <p class="sign">…</p> 内的空白与人名用字间距（直接改三合一毛选解压 xhtml）。

----------------------------------------------------------------------
常见 Unicode 空白字符速查（改 TITLE_NAME_GAP / 常量 SP、EDGE_STRIP 时可对照）

  写法：码点记作 U+XXXX；在 Python 源码里用「反斜杠 + u + 四位十六进制」放在引号内表示该字符
        （勿写假的 \\uXXXX 占位，否则解释器会当转义而报错）。U+0020 可直接写半角空格 ' '。
  U+200B 等零宽字符引号内看不见，属正常现象。

  U+0020 ' ' SPACE（ASCII 空格）。可视。西文词间、通用半角空格，比例字体里通常较窄。
  U+00A0 ' ' NO-BREAK SPACE（不换行空格，HTML &nbsp;）。可视，宽常同 U+0020，但该处不换行。
  U+2002 ' ' EN SPACE。可视。约半 em。
  U+2003 ' ' EM SPACE。可视。约 1 em（常近一字宽，随字体变）。
  U+2004 ' ' THREE-PER-EM SPACE。可视。
  U+2005 ' ' FOUR-PER-EM SPACE。可视。
  U+2006 ' ' SIX-PER-EM SPACE。可视。
  U+2007 ' ' FIGURE SPACE。可视。与等宽数字同宽。
  U+2008 ' ' PUNCTUATION SPACE。可视。与连接号等标点同宽（依字体）。
  U+2009 ' ' THIN SPACE。可视。很窄，常用于数字与单位之间。
  U+200A ' ' HAIR SPACE。可视。比 THIN 更窄。
  U+200B '​' ZERO WIDTH SPACE。零宽不可视。断行/分词用，勿当排版空格。
  U+202F ' ' NARROW NO-BREAK SPACE。可视。窄且不换行。
  U+205F ' ' MEDIUM MATHEMATICAL SPACE。可视。数学排版中等宽。
  U+3000 '　' IDEOGRAPHIC SPACE（全角空格）。可视。与汉字等宽（东亚排版「一格」）。
  U+FEFF '﻿' ZERO WIDTH NO-BREAK SPACE（亦作 BOM）。零宽；UTF-8 文件开头常见，正文内较少当空格用。

  本脚本当前：职务与姓名之间压成 TITLE_NAME_GAP（默认 U+3000）。
  SP / EDGE_STRIP 还认：U+00A0、U+2002–U+200B、U+202F、U+205F、U+3000、U+2003、U+FEFF（首尾）等，与 probe_em_space.py 探测集合对齐（不含 U+0020 单独列入 SP，用 [ \\t]）。
----------------------------------------------------------------------

规则概要：
- 只处理 class 含 sign 的 <p>（可带其它 class）。
- 首尾去掉各类空白（见下方 _WS_EXTRA：NBSP、U+2002–U+200B、窄不换行、MMSP、全角、EM、BOM 等 + 半角空白）。
- 先按固定模式合并常见姓名：毛·泽·东、周·恩·来、林·彪、中·央、朱·德、彭·德·怀（·表示任意允许空白）。
- 再扫描「CJK — 空白 — CJK」：
  - 若整段前缀以职务/头衔后缀结尾（见 TITLE_SUFFIXES），则该处连续空白压成 **一个 U+3000**（全角空格，与中文书中「主席　毛泽东」常见排法一致）。
  - 若左侧连续 CJK 块长度 ≤1（单字），则去掉中间空白（单字间不留空）。
  - 否则保持原样（保守分支：左连续汉字≥2 且未命中职务后缀则不动）。理论上可防「日期中间被插空白」
    等误合并；在三合一毛选全库 p.sign 里几乎不触发，仅见疑似坏数据如 Section11051「九月 日」。

内联 HTML（<br/>、<span> 等）：按标签切段，只对纯文本段做上述处理，标签原样保留。

用法：
    编辑本文件顶部常量 WRITE_CHANGES（False=仅探测，True=写回 xhtml）；
    需要时改 DEFAULT_ROOT。然后：python fix_sign_spacing.py
"""

from __future__ import annotations

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

# False：只打印变更；True：把修改写回 xhtml（无命令行参数，改此布尔即可）
WRITE_CHANGES = False

TEXT_SUFFIXES = {".xhtml", ".html", ".htm"}

# 各类非常规空白 + 半角空白（不含换行，避免跨段误合并）；与 probe_em_space.py 一致
_WS_EXTRA = "\u00a0\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u200b\u202f\u205f\u3000"
EDGE_STRIP = re.compile(
    rf"^[\s{_WS_EXTRA}\ufeff]+|[\s{_WS_EXTRA}\ufeff]+$",
    re.MULTILINE,
)
SP = rf"(?:[ \t]|{_WS_EXTRA}|\ufeff)+"
# 职务与姓名之间的单一分隔符（全角空格，与汉字等宽）
TITLE_NAME_GAP = "\u3000"

# 职务/头衔后缀：越长越优先匹配（用于「主席……　姓名」）
TITLE_SUFFIXES: tuple[str, ...] = (
    "常务委员会委员长",
    "人民革命军事委员会主席",
    "革命军事委员会主席",
    "中央委员会主席",
    "中央委员会副主席",
    "中国人民解放军总司令",
    "国务院总理",
    "国防部部长",
    "委员会主席",
    "委员会副主席",
    "总司令",
    "委员长",
    "副主席",
    "主席",
    "总理",
    "部长",
    "书记",
    "军长",
    "司令员",
    "司令",
)

CJK_PAIR = re.compile(rf"([\u4e00-\u9fff])({SP})([\u4e00-\u9fff])")
TAG_SPLIT = re.compile(r"(<[^>]+>)")

# <p ... class="..." ...> 含 sign
P_SIGN_OPEN = re.compile(
    r'(<p\b[^>]*\bclass\s*=\s*["\'])([^"\']*)(["\'][^>]*>)',
    re.IGNORECASE,
)


def _has_sign_class(class_attr: str) -> bool:
    parts = re.split(r"\s+", class_attr.strip())
    return "sign" in parts


def _iter_sign_paragraphs(html: str) -> list[tuple[int, int, str]]:
    """返回 [(p 起始, p 结束, inner_html), ...]。sign 段内一般无嵌套 <p>，取首个 </p>。"""
    out: list[tuple[int, int, str]] = []
    i = 0
    while True:
        m = P_SIGN_OPEN.search(html, i)
        if not m:
            break
        if not _has_sign_class(m.group(2)):
            i = m.end()
            continue
        open_end = m.end()
        close_m = re.search(r"</p\s*>", html[open_end:], re.IGNORECASE)
        if not close_m:
            break
        j = open_end + close_m.start()
        inner = html[open_end:j]
        end_full = open_end + close_m.end()
        out.append((m.start(), end_full, inner))
        i = end_full
    return out


def _cjk_run_len_ending_at(s: str, idx: int) -> int:
    c = 0
    k = idx
    while k >= 0 and "\u4e00" <= s[k] <= "\u9fff":
        c += 1
        k -= 1
    return c


def _prefix_ends_with_title(prefix: str) -> bool:
    for suf in TITLE_SUFFIXES:
        if prefix.endswith(suf):
            return True
    return False


def _apply_known_names(s: str) -> str:
    pairs: list[tuple[re.Pattern[str], str]] = [
        (re.compile(rf"毛{SP}泽{SP}东"), "毛泽东"),
        (re.compile(rf"周{SP}恩{SP}来"), "周恩来"),
        (re.compile(rf"林{SP}彪"), "林彪"),
        (re.compile(rf"中{SP}央"), "中央"),
        (re.compile(rf"朱{SP}德"), "朱德"),
        (re.compile(rf"彭{SP}德{SP}怀"), "彭德怀"),
    ]
    prev = None
    while prev != s:
        prev = s
        for pat, rep in pairs:
            s = pat.sub(rep, s)
    return s


def normalize_sign_plain_text(s: str) -> str:
    s = EDGE_STRIP.sub("", s)
    s = _apply_known_names(s)
    # 多轮：合并后可能产生新的 CJK 邻接
    for _ in range(64):
        new_parts: list[str] = []
        pos = 0
        changed = False
        while pos < len(s):
            m = CJK_PAIR.search(s, pos)
            if not m:
                new_parts.append(s[pos:])
                break
            a, b, c = m.start(), m.end(), m.groups()
            left, mid, right = c[0], c[1], c[2]
            new_parts.append(s[pos:a])
            prefix = s[: a + 1]
            whole = m.group(0)
            if _prefix_ends_with_title(prefix):
                repl = left + TITLE_NAME_GAP + right
            elif _cjk_run_len_ending_at(s, a) <= 1:
                repl = left + right
            else:
                # 左连续 CJK≥2 且非职务后缀：不改（语料里极少；例：日期瑕疵「月 日」）
                # Section11051.xhtml	一九六八年九月 日（月 和 日 之间有个空格）
                repl = whole
            if repl != whole:
                changed = True
            new_parts.append(repl)
            pos = b
        s = "".join(new_parts)
        s = EDGE_STRIP.sub("", s)
        if not changed:
            break
    return s


def normalize_sign_inner_html(inner: str) -> str:
    parts = TAG_SPLIT.split(inner)
    out: list[str] = []
    for p in parts:
        if not p:
            continue
        if p.startswith("<"):
            out.append(p)
        else:
            out.append(normalize_sign_plain_text(p))
    return "".join(out)


def process_xhtml_text(raw: str, *, fix: bool) -> tuple[str, list[tuple[str, str, str]]]:
    """
    返回 (新全文, 变更列表)。
    每项 (文件内片段说明, before, after) — 仅 sign 内文摘要。
    """
    changes: list[tuple[str, str, str]] = []
    segs = _iter_sign_paragraphs(raw)
    if not segs:
        return raw, changes
    chunks: list[str] = []
    last = 0
    for start, end, inner in segs:
        chunks.append(raw[last:start])
        # 从 raw[start:end] 取出 <p...> 与 </p>
        block = raw[start:end]
        open_m = re.match(r"(<p\b[^>]*>)", block, re.IGNORECASE)
        if not open_m:
            chunks.append(block)
            last = end
            continue
        open_tag = open_m.group(1)
        close_tag = "</p>"
        if not block.lower().endswith(close_tag.lower()):
            chunks.append(block)
            last = end
            continue
        inner_old = inner
        inner_new = normalize_sign_inner_html(inner_old)
        if inner_new != inner_old:
            brief = inner_old.replace("\n", "↵")
            if len(brief) > 120:
                brief = brief[:117] + "..."
            changes.append((brief, inner_old, inner_new))
        new_block = open_tag + inner_new + close_tag
        chunks.append(new_block)
        last = end
    chunks.append(raw[last:])
    new_raw = "".join(chunks)
    if fix:
        return new_raw, changes
    return raw, changes


def _iter_xhtml_files(root: Path) -> list[Path]:
    out: list[Path] = []
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in TEXT_SUFFIXES:
            out.append(p)
    return sorted(out)


def main() -> int:
    root = DEFAULT_ROOT.resolve()
    if not root.is_dir():
        print(f"❌ 不是目录: {root}", flush=True)
        return 1

    files = _iter_xhtml_files(root)
    total_changes = 0
    total_files = 0

    print(f"📖 {root}")
    print(f"模式: {'写回 (WRITE_CHANGES=True)' if WRITE_CHANGES else '仅探测 (WRITE_CHANGES=False)'}\n")
    print("=" * 80)

    for fp in files:
        try:
            raw = fp.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            print(f"⚠️ 跳过 {fp}: {e}", flush=True)
            continue
        new_raw, chg = process_xhtml_text(raw, fix=WRITE_CHANGES)
        if not chg:
            continue
        total_files += 1
        total_changes += len(chg)
        try:
            rel = fp.relative_to(root)
        except ValueError:
            rel = fp
        print(f"\n--- {rel.as_posix()} --- {len(chg)} 处 p.sign")
        for brief, before, after in chg:
            print(f"  摘要: {repr(brief)}")
            print(f"  前: {repr(before)}")
            print(f"  后: {repr(after)}")
        if WRITE_CHANGES and new_raw != raw:
            fp.write_text(new_raw, encoding="utf-8")

    print("\n" + "=" * 80)
    print(f"汇总: {total_changes} 处 p.sign 变更，涉及 {total_files} 个文件")
    if not WRITE_CHANGES and total_changes:
        print("（未写回；将文件顶部 WRITE_CHANGES 改为 True 后重跑）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
