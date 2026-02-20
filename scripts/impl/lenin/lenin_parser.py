import fitz
import re

# ================= 🎛️ 核心配置 =================

# 字体大小映射表：根据字号大小决定 Markdown 的前缀
# 注意：浮点数匹配允许微小误差 (±0.5)
FONT_MAP = {
    29.0: "# ",       # 一级标题（容错）
    16.6: "# ",       # 一级标题（容错）
    14.4: "# ",       # 一级标题
    13.0: "## ",      # 二级标题
    11.0: "### ",     # 三级标题
    # 11.0: "SUBTITLE",  # 副标题（会被加粗处理）也可能是 9.6
    7.4: "> ",        # 默认引用（通常用于文末出版信息，优先级低于字体检测）
    # 9.6 正文，不加前缀
}

# 页面布局参数（单位：PDF坐标点）
# measure_margin: 左侧文字边缘 90，缩进后 110 → INDENT_THRESHOLD=105
MARGIN_TOP_CUT = 110     # 顶部裁剪线：忽略此高度以上的页眉
MARGIN_BOTTOM_CUT = 520 # 底部裁剪线：忽略 Y > 520 的区域
DETECT_THRESHOLD = 40   # 全页注脚检测阈值：从此高度才开始检测注脚
INDENT_THRESHOLD = 105  # 缩进阈值：X坐标大于此值视为新段落（列宁卷1: 左90 缩进110）
CENTER_THRESHOLD = 120  # 居中阈值：X坐标大于此值且为黑体，视为三级标题 (###)


# ================= ⚙️ 解析引擎 =================
# Page（页） -> Block（块） -> Line（行） -> Span（相同样式片段） -> Char（字符）

class LeninParser:
    def __init__(self, output_base_dir):
        """
        初始化解析器
        :param output_base_dir: 基础目录 (pathlib.Path 对象)
        """
        self.output_base_dir = output_base_dir
        self.img_counter = 0
        self.assets_dir = None  # 由 parse_chapter_pages 按文章设置

        # === 状态变量 ===
        self.global_note_id = 1    # 全局注脚计数器 [^1], [^2]...
        self.all_footnotes = []    # 存储当页提取出的注脚内容
        self.body_buffer = []      # 存储正文段落
        self.current_para = ""     # 当前正在拼接的段落缓存

    def is_cjk(self, char):
        """检测字符是否为中日韩文字（用于判断是否需要加空格）"""
        if not char: return False
        return '\u4e00' <= char <= '\u9fff'

    def clean_text(self, text):
        """
        基础文本清洗
        [注意] 这里不再使用 .strip() 去除首尾空格！
        原因：我们需要保留 span 之间的原始空格，以便在 process_spans_in_line
        中通过正则智能识别 '## 一 几点说明' 这种带序号的标题。
        """
        # 移除 PDF 中的换页标记
        text = re.sub(r'\[\s*接\s*上\s*页\s*\]', '', text)
        text = re.sub(r'\[\s*转\s*下\s*页\s*\]', '', text)
        return text

    def get_split_y(self, page):
        """
        计算正文和注脚的分割线 (Split Line) Y坐标
        列宁全集：用矢量横线（从下往上第一条）
        逻辑：
        1. 优先找 get_drawings 中的横线（宽 60–75），非连续破折号 block，取从下往上第一条
        2. 其次找 '接上页' 这种全页注脚标记
        """
        blocks = page.get_text("blocks")
        page_height = page.rect.height

        # 1. 矢量横线（从下往上第一条）
        # 页眉线：宽度>200；正文/注脚分割线：宽度约 60–75
        drawings = page.get_drawings()
        h_lines = []
        for d in drawings:
            r = d.get("rect")
            # 特征匹配
            if not r or r.height >= 5:
                continue
            w = r.width
            if 60 <= w <= 75:
                h_lines.append(r.y0)
        if h_lines:
            return max(h_lines) - 2  # 稍微往上提一点作为分界线

        # 2. 扫描全页注脚标记
        check_count = 0
        for b in blocks:
            y0 = b[1]
            text = b[4].strip()
            if y0 > DETECT_THRESHOLD:
                if re.search(r'接\s*上\s*页', text):
                    return y0 - 1
                check_count += 1
                if check_count >= 5: break # 只检查顶部几个块，避免误判

        return page_height # 没找到分割线，说明全是正文

    def process_spans_in_line(self, line, page_note_queue):
        """
        [核心函数] 处理单行内的所有 span（片段），负责：
        1. 字体语义识别（黑体->粗体，楷体->斜体，仿宋->引用）
        2. 标题层级判定
        3. 注脚符号替换
        4. 智能去空（修复标题空格）
        """
        spans = line["spans"]
        formatted_text = ""

        line_max_size = 0
        has_fangsong = False
        has_kaiti = False
        has_heiti = False

        # --- 步骤 1: 预扫描整行特征 ---
        for span in spans:
            if span["size"] > line_max_size: line_max_size = span["size"]
            font_lower = span["font"].lower()

            # 模糊匹配字体名
            if "fang" in font_lower:    # 仿宋 -> 引用
                has_fangsong = True
            elif "kai" in font_lower:   # 楷体 -> 斜体
                has_kaiti = True
            elif "hei" in font_lower or "bold" in font_lower: # 黑体/粗体 -> 加粗
                has_heiti = True

        # --- 步骤 2: 决定整行的前缀 (Markdown Syntax) ---
        line_prefix = ""
        mapped_prefix = ""

        # 先看字号映射
        if FONT_MAP:
            closest_size = min(FONT_MAP.keys(), key=lambda k: abs(k - line_max_size))
            if abs(closest_size - line_max_size) < 0.5:
                mapped_prefix = FONT_MAP[closest_size]

        # 判定优先级：
        # 1. 字号巨大的标题 (#, ##)
        if mapped_prefix.startswith("#"):
            line_prefix = mapped_prefix
        # 2. 居中的黑体 -> 强制视为三级标题 (###)
        elif has_heiti and line["bbox"][0] > CENTER_THRESHOLD:
            line_prefix = "### "
        # 3. 仿宋字体 -> 引用块
        elif has_fangsong:
            line_prefix = "> "
        # 4. 14号小字 -> 引用块 (排除楷体和黑体，避免误伤注脚或强调文本)
        elif mapped_prefix == "> " and not has_kaiti and not has_heiti:
            line_prefix = "> "

        # 如果有前缀，先拼接到结果中
        if line_prefix.strip().startswith("#") or line_prefix.strip().startswith(">"):
            formatted_text += line_prefix

        # 记录当前行的类型，用于防粘连逻辑
        last_type = None
        if line_prefix.strip().startswith("#"):
            last_type = "header"
        elif line_prefix.strip().startswith(">"):
            last_type = "blockquote"
        else:
            last_type = "body"

        # --- 步骤 3: 逐个处理 span (内容拼接 & 行内样式) ---
        for span in spans:
            text = span["text"]
            size = span["size"]
            flags = span["flags"]
            font_lower = span["font"].lower()

            text = self.clean_text(text)
            if not text: continue # 空内容跳过

            current_type = "body"
            if size in FONT_MAP:
                span_closest = min(FONT_MAP.keys(), key=lambda k: abs(k - size))
                if abs(span_closest - size) < 0.5:
                    p = FONT_MAP[span_closest]
                    if p.startswith("#"): current_type = "header"

            clean_t = text.strip()
            # 判断是否为纯标点（用于防止标题因标点被切断）
            is_punctuation = len(clean_t) == 1 and not self.is_cjk(clean_t) and not clean_t.isalnum()

            # [逻辑] 标题防粘连检测
            # 如果从 Header 变成了 Body，且不是标点 -> 通常需要插入空行切断
            should_split = (last_type == "header" and current_type == "body" and not is_punctuation)
            if should_split:
                # [豁免 1] 如果是三级标题 (###)，允许紧接内容
                if line_prefix.strip() == "###": should_split = False
                # [豁免 2] 如果是注脚符号 ([^1] 或 ①)，允许紧接标题，不切断
                if re.match(r'^([\u2460-\u2469]|\d+)$', clean_t): should_split = False
                # [豁免 3] 若整行是标题行 (#/##)，标题与内容应一体，不切断（避免 "# \n\n 内容"）
                if line_prefix.strip() in ("#", "##"): should_split = False

            if should_split:
                formatted_text += "\n\n"

            if not is_punctuation:
                last_type = current_type

            # SUBTITLE (副标题) 特殊处理：加粗
            span_prefix = ""
            if FONT_MAP:
                closest = min(FONT_MAP.keys(), key=lambda k: abs(k - size))
                if abs(closest - size) < 0.5:
                    span_prefix = FONT_MAP[closest]

            if span_prefix == "SUBTITLE":
                if formatted_text and not formatted_text.endswith("\n"):
                    formatted_text += "\n\n"
                text = f"**{text.strip()}**"

            # 替换注脚符号为 Markdown 格式 [^n]
            def replace_ref_body(_match):
                note_id = self.global_note_id
                self.global_note_id += 1
                page_note_queue.append(note_id)
                return f"[^{note_id}]"

            # 正则匹配 ① 到 ⑩ (\u2460 - \u2469)
            text = re.sub(r'[\u2460-\u2469]', replace_ref_body, text)

            # [逻辑] 应用行内样式 (加粗/斜体)
            # 只有当这一行不是标题时才应用，避免 ### **Title** 这种冗余
            if not line_prefix.startswith("#"):
                # PyMuPDF flags: 通过二进制位来存储信息的 int。用位运算来解读它：
                # 0=普通，1=上标，2=斜体，4=衬线，8=无衬线，16=粗体，32=等宽，相加可以组合
                is_bold = flags & 16
                is_italic = flags & 2

                if "hei" in font_lower or "bold" in font_lower: is_bold = True
                if "kai" in font_lower: is_italic = True

                if is_bold or is_italic:
                    # [关键修复]：只包裹核心文字，不包裹首尾空格
                    # 避免 "**    Text**" -> 导致无法 strip 掉缩进
                    # 改为 "    **Text**" -> 最后的 strip() 可以去掉缩进

                    if not text.strip():
                        pass  # 如果全是空格，就不加粗了
                    else:
                        # 1. 提取左边空格
                        l_stripped = text.lstrip()
                        prefix_space = text[:len(text) - len(l_stripped)]

                        # 2. 提取右边空格
                        r_stripped = text.rstrip()
                        suffix_space = text[len(r_stripped):]

                        # 3. 提取核心文字
                        content = text.strip()

                        # 4. 包裹核心文字
                        if is_bold and is_italic:
                            content = f"***{content}***"
                        elif is_bold:
                            content = f"**{content}**"
                        elif is_italic:
                            content = f"*{content}*"

                        # 5. 拼回去
                        text = prefix_space + content + suffix_space

            formatted_text += text

        # --- 步骤 4: 智能后处理 (去空 & 缩进清洗) ---
        formatted_text = formatted_text.strip()  # 在这里统一进行整体去空

        if line_prefix.strip().startswith("#"):
            # [核心修复] 标题智能去空
            # 目标：保留序号后的空格 (如 "一 几点说明")，删除排版用的空格 (如 "编 辑 部")
            prefix_len = len(line_prefix)
            content = formatted_text[prefix_len:]
            content_norm = content.replace("　", " ") # 归一化全角空格
            # 正则匹配：数字/中文序号 + 空格 + 内容
            match_num = re.match(r'^([0-9\.]+|[一二三四五六七八九十百]+[、\.]?)\s+(.*)', content_norm)

            if match_num:
                # 命中序号结构 -> 保留一个标准空格
                num_part = match_num.group(1)
                text_part = match_num.group(2).replace(" ", "")
                content = f"{num_part} {text_part}"
            else:
                # 未命中 -> 暴力清理所有空格
                content = content.replace(" ", "").replace("　", "")

            formatted_text = line_prefix + content

        elif line_prefix.strip().startswith(">"):
            # [核心修复] 引用块去缩进
            # 强制去除引用内容前的空白，防止 Markdown 将其渲染为代码块
            prefix_len = len(line_prefix)
            content = formatted_text[prefix_len:].strip()
            formatted_text = line_prefix + content

        return formatted_text, line_prefix

    def append_to_buffer(self, clean_line, is_new_para):
        """
        将处理好的单行文本追加到缓冲区，处理跨行拼接逻辑
        """
        # 1. 引用拼接逻辑
        # 如果是同类型引用续行，去掉 "> " 前缀直接拼，防止每行都断开
        # is_quote_continuation = False # 变量虽未使用但逻辑保留
        if clean_line.startswith("> ") and not is_new_para and self.current_para.startswith("> "):
            # is_quote_continuation = True
            clean_line = clean_line[2:]

        # 2. 标题续行拼接：上一段是标题且本行也是标题续行，去掉 "#" 前缀再拼
        if not is_new_para and self.current_para and re.match(r'^#+\s', self.current_para) and re.match(r'^#+\s', clean_line):
            clean_line = re.sub(r'^#+\s*', '', clean_line)

        if is_new_para:
            # 新段落：将旧段落推入 buffer，开始记录新段落
            if self.current_para:
                self.body_buffer.append(self.current_para)
            self.current_para = clean_line
        else:
            # 续行：拼接到当前段落
            if self.current_para:
                merged = False

                # [核心修复] 粗体融合 (Bold Fusion)
                # 场景：Line1: "**开始**" + Line2: "**结束**" -> "**开始结束**"
                # 避免出现 "**开始****结束**" 导致渲染断裂
                if self.current_para.endswith("**") and clean_line.startswith("**"):
                    raw_last = self.current_para[:-2][-1].replace("*", "").replace("`", "")
                    raw_curr = clean_line[2:][0].replace("*", "").replace("`", "")
                    if self.is_cjk(raw_last) and self.is_cjk(raw_curr):
                        self.current_para = self.current_para[:-2] + clean_line[2:]
                        merged = True

                # [核心修复] 斜体融合 (Italic Fusion)
                # 场景：Line1: "*（笑声*" + Line2: "*，鼓掌）*" -> "*（笑声，鼓掌）*"
                elif self.current_para.endswith("*") and clean_line.startswith("*") and not self.current_para.endswith(
                        "**") and not clean_line.startswith("**"):
                    raw_last = self.current_para[:-1][-1].replace("*", "").replace("`", "")
                    raw_curr = clean_line[1:][0].replace("*", "").replace("`", "")
                    if self.is_cjk(raw_last) and self.is_cjk(raw_curr):
                        self.current_para = self.current_para[:-1] + clean_line[1:]
                        merged = True

                if not merged:
                    # 普通文本拼接：汉字之间不加空格，西文之间加空格
                    last_char = self.current_para[-1].replace("*", "").replace("`", "")
                    curr_char = clean_line[0].replace("*", "").replace("`", "")

                    if self.is_cjk(last_char) and self.is_cjk(curr_char):
                        self.current_para += clean_line
                    else:
                        self.current_para += " " + clean_line
            else:
                self.current_para = clean_line

    def parse_chapter_pages(self, doc, page_indices, article_output_dir):
        """
        [主入口] 解析指定章节的页面列表(跨页流式处理)
        :param doc: PyMuPDF Document
        :param page_indices: 这一章包含的页码列表 (0-based)
        :param article_output_dir: 本篇文章的输出目录，图片保存在其 assets 子目录
        """
        # 设置本篇文章的 assets 目录
        self.assets_dir = article_output_dir / "assets"
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        self.img_counter = 0

        # 重置状态 (每章开始)
        self.global_note_id = 1
        self.all_footnotes = []
        self.body_buffer = []
        self.current_para = ""

        # 遍历章节里的每一页并解析
        for p_idx in page_indices:
            page = doc[p_idx]
            page_num = page.number + 1  # 人类阅读页码 (1-based)
            # 获取分割线位置，区分正文和注脚
            split_y = self.get_split_y(page)
            # 计算裁剪框：去掉页眉
            actual_top_cut = min(MARGIN_TOP_CUT, split_y)
            # 去掉底部有干扰信息的区域
            clip_bottom = min(MARGIN_BOTTOM_CUT, page.rect.height)
            # 获取内容
            clip_rect = fitz.Rect(0, actual_top_cut, page.rect.width, clip_bottom)
            data = page.get_text("dict", clip=clip_rect)

            body_lines_raw = [] # 正文区域
            foot_lines_raw = [] # 脚注区域
            page_note_queue = [] # 当前页面的注脚号队列 (Body 生产 ID -> Footer 消费 ID)

            # 遍历块，分流图片、正文行、注脚行
            for block in data["blocks"]:
                # --- 图片处理 ---
                if "image" in block:
                    self.img_counter += 1
                    img_filename = f"img_{self.img_counter}.png"
                    img_path = self.assets_dir / img_filename
                    try:
                        with open(img_path, "wb") as f:
                            f.write(block["image"])
                        self.append_to_buffer(f"![img](assets/{img_filename})", is_new_para=True)
                    except Exception as e:
                        print(f"⚠️ 图片保存失败 p{page_num}: {e}")
                    continue

                # --- 文本处理 ---
                if "lines" not in block:
                    continue

                # 根据 Y 坐标划分区域，分流
                if block["bbox"][1] >= split_y:
                    foot_lines_raw.extend(block["lines"])
                else:
                    body_lines_raw.extend(block["lines"])

            # === Pass 1: 处理正文区域 ===
            last_line_prefix = ""
            for line in body_lines_raw:
                line_text, prefix = self.process_spans_in_line(line, page_note_queue)
                # [注意] strip() 在这里调用，去除 Raw 字符串里的物理缩进
                clean_line = self.clean_text(line_text).strip()

                if not clean_line:
                    continue
                if re.search(r'[—_]{8,}', clean_line):
                    continue # 跳过分割线

                # 智能分段判断（last_line_prefix 为上一行的 prefix，用于标题续行判定）
                is_new = False

                # [判定 1] 物理缩进 -> 新段落
                if line["bbox"][0] > INDENT_THRESHOLD:
                    is_new = True
                # [判定 2] 空格缩进 (全角/半角) -> 新段落
                raw_text = "".join([s["text"] for s in line["spans"]])
                if raw_text.startswith("　") or raw_text.startswith("  "):
                    is_new = True

                # [判定 3] 标题强制换段（但连续多行同标题视为续行，合并为一行）
                if prefix.startswith("#"):
                    if last_line_prefix.strip().startswith("#"):
                        # 上一行也是标题 -> 标题续行，不换段
                        is_new = False
                    else:
                        is_new = True

                # [判定 4] 引用块逻辑
                if prefix.startswith(">"):
                    # [核心修复] 正文/引用防粘连
                    # 如果上一段是正文(不带>)，这一段是引用(带>) -> 强制换段 (如文末出版信息)
                    if self.current_para and not self.current_para.startswith("> "):
                        is_new = True
                    elif not is_new:  # 如果是引用接引用，且无缩进 -> 视为续行
                        is_new = False

                # [核心修复] 注脚跟随 (去掉 $)
                # 允许注脚符号后跟文字 (如 "[^1]。内容") 紧接上一行
                if re.match(r'^\s*\[\^\d+\]', clean_line):
                    is_new = False

                self.append_to_buffer(clean_line, is_new)
                last_line_prefix = prefix

            # === Pass 2: 处理页底注脚区域 ===
            # 列宁的：每行都缩进，只有 ① 序号突出。只用序号判断新注脚，不用缩进。（斯大林的：需用缩进判断，因正文与注脚布局类似）
            current_foot_para = ""
            for line in foot_lines_raw:
                raw_text = "".join([s["text"] for s in line["spans"]])
                clean_line = self.clean_text(raw_text).strip()
                if not clean_line:
                    continue
                if re.search(r'[—_]{8,}', clean_line):
                    continue

                # 检测注脚开头是否有符号：① 或 [^1]
                match = re.match(r'^[\u2460-\u2469]', clean_line)
                is_new_foot = False

                if match:
                    is_new_foot = True
                    # 将 PDF 的圈圈数字替换为 Markdown 的 [^n]
                    if page_note_queue:
                        # 从队列领号
                        note_id = page_note_queue.pop(0)
                        # 替换符号
                        clean_line = clean_line.replace(match.group(), f"[^{note_id}]: ", 1)
                    else:
                        # 异常情况：页底有圈圈，但正文没引用？
                        # 兜底：生成一个随机ID或保留原样
                        clean_line = clean_line.replace(match.group(), f"[^x]: ", 1)

                # 拼接注脚文本（续行直接拼，不加换行）
                if is_new_foot:
                    if current_foot_para:
                        self.all_footnotes.append(current_foot_para)
                    current_foot_para = clean_line
                else:
                    if current_foot_para:
                        current_foot_para += clean_line
                    elif self.all_footnotes:
                        self.all_footnotes[-1] += clean_line
                    else:
                        current_foot_para = clean_line

            # 本页最后一个注脚段落
            if current_foot_para:
                self.all_footnotes.append(current_foot_para)

        # 刷新最后的正文缓存
        if self.current_para:
            self.body_buffer.append(self.current_para)

        # === [核心修复] 引用块智能合并 (Quote Merger) ===
        # 将连续的两个独立引用块 (中间有空行) 合并为一个块
        merged_buffer = []
        for block in self.body_buffer:
            if not merged_buffer:
                merged_buffer.append(block)
                continue

            prev_block = merged_buffer[-1]
            # 条件：前一块是引用 AND 这一块也是引用
            if prev_block.startswith("> ") and block.startswith("> "):
                # 使用 "\n>\n" 作为粘合剂，保持视觉上的分段但逻辑上是一体
                merged_buffer[-1] = prev_block + "\n>" + "\n" + block
            else:
                merged_buffer.append(block)

        # 最终组装全文
        full_md = "\n\n".join(merged_buffer)

        if self.all_footnotes:
            full_md += "\n\n" + "\n\n".join(self.all_footnotes)

        return full_md