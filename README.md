# iskra-x2md

[![Python](https://img.shields.io/badge/python-3.14+-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
![Status](https://img.shields.io/badge/Status-Active-success)

---

`iskra-x2md` 为 [iskra-data](https://github.com/Qhbee/iskra-data) 提供内容，将其需要的各种格式的资料转换为机器友好的、语义清晰的 **Markdown** 格式。

**Input:** PDF, DOCX, EPUB, HTML, TXT and more  
**Output:** clean, structured GitHub Flavored Markdown (GFM)

---

## TODO & BUG


### 马克思、恩格斯

- ✅ Z-library 的 pdf，说是第二版，其实只有第一卷是第二版，其余为同中马库，但是多了书签
- 🔄 中马库 [马克思恩格斯全集（文字版）](https://www.marxists.org/chinese/marx-engels/index.htm) 共 50 卷，不全
- 🔄 中马库 [马克思恩格斯全集·Ⅰ版（文字版PDF）](https://www.marxists.org/chinese/pdf/me-old.htm) 共 50 卷
- ⬜ 中马库 [马克思恩格斯全集·Ⅱ版（文字版PDF）](https://www.marxists.org/chinese/pdf/me-2.htm) 有增删，翻译质量更好，卷数更多，但是没出完，不全
- ⬜ 中马库 [《马克思恩格斯文集》10卷本PDF（2009年版）](https://www.marxists.org/chinese/pdf/me-2.htm) 共 10 卷，非文字版，需要 OCR

### 列宁

- ❌ Z-library 的 epub （尝试后发现，实际来源是“中马库” [列宁全集（文字网页版）](https://www.marxists.org/chinese/lenin-cworks/index.htm) 的 旧版 HTML，而且缺少）
- ✅ Z-library 的 pdf，同中马库，但是多了书签
- ⬜ 中马库 [列宁全集（中文第二版-文字版PDF）](https://www.marxists.org/chinese/pdf/lenin-old.htm)，从文字版 PDF 解析，但是缺少第54-第60卷，以及《列宁全集补遗》
- ⬜ 中马库 [列宁全集（中文第二版-图像版PDF）](https://www.marxists.org/chinese/pdf/lenin.htm)，以后 OCR 第54-第60卷
- ⬜ 中马库 [列宁全集（版本II-2017年增订版-图像版PDF）](https://www.marxists.org/chinese/pdf/lenin-2017.htm)，有书签，需要 OCR，第一卷末尾有《列宁全集》第二版增订版新增文献一览表，还可以补充“人名索引”和“文献索引”
- ⬜ 列宁全集补遗两卷，属于第一版，但只找到第一卷，没有第二卷
- ⬜ 两种注释问题，作者/俄国编者注释是右上角圆圈①和页脚注，中国译者注释是右上角全角数字１和书末尾单独的注释章节
- ⬜ 中国译者注释右上角全角数字１要不要替换为 ⁰ ¹ ² ³ ⁴ ⁵ ⁶ ⁷ ⁸ ⁹
- ⬜ 中国译者注释目前单独成章节，要不要拆分到每篇文章里？如果不拆分的话怎么方便找到？考虑方案：
  - 拆分文章后，用 `[^cn-1]` 与 `[^1]` 区分两种注释，标签是语义化的，为“编号”而非“顺序”，插哪里都不会影响其他注脚！无论用哪种写法，最终渲染出来都是数字（1, 2, 3...）
  - 拆分文章后，用 `{#编者注1}` 锚点（或自定义语法），不通用
  - 不拆分文章，用 `[Foo bar]: </path/to/article.md> 'title'` 相对路径链接，但是在不同环境下表现不同，比如 IDE / Nuxt Content 静态博客

### 斯大林

- 🔄 诸夏怀斯社版-斯大林全集20卷，文字版 PDF，但很可能有一些错误的多余的
- 🔄 诸夏怀斯社版-斯大林全集附卷10卷，文字版 PDF，但很可能有一些错误的多余的
- ✅ 诸夏怀斯社版-斯大林选集4卷，文字版 PDF，已经解析
- ⬜ 斯大林吧-斯大林文论.doc，应该校对过，去掉了一些错误
- ⬜ 行内注释为宋体但是整行被视为引用换行了，eg. 四卷本新编《斯大林选集》【合集】/03四卷本新编《斯大林选集》第3卷/正文/选自全集第十五卷/论辩证唯物主义和历史唯物主义
- ⬜ 一个句号单独另起一行，eg. 四卷本新编《斯大林选集》【合集】/01四卷本新编《斯大林选集》第1卷/正文/选自全集第一卷/无政府主义还是社会主义？

### 毛泽东
- ✅ 毛泽东选集（1-7卷 静火版）V1.20 2019最新版.epub
- ❌ 毛泽东选集第六卷（润之赤旗版）.epub，被新增三合一版包含，放弃单独解析（唯一的一点好处是书签层级更细致到文章内小节，但是应该不需要）
- ❌ 毛泽东选集第七卷（润之赤旗版）.epub，被新增三合一版包含，放弃单独解析（唯一的一点好处是书签层级更细致到文章内小节，但是应该不需要）
- 🔄 毛泽东选集全七卷（官方、静火、润之赤旗三合一版）.epub，排版精美，但仍有少量错误，需要校对
- ⬜ 毛泽东选集（1-7：原版五卷+静火+赤旗+草堂）.pdf
- ⬜ 毛泽东文集-中共中央文献研究室.epub
- ⬜ 毛泽东年谱（全九卷_正常目录）.epub
- ⬜ 中马库 [建国以来毛泽东文稿，第一版共13册](https://www.marxists.org/chinese/maozedong/#7)，都是 PDF ，1-11 是文字版，12、13 是黑白扫描版
- ⬜ 毛泽东博览网 [建国以来毛泽东文稿，第二版共20册](https://mzdbl.org/xin1)，图像叠加 OCR 的高清扫描版 PDF，符号 OCR 效果疑似不佳，14、15 可能有权限限制
- ⬜ Z-library 的 epub 建国以来毛泽东文稿，第一版共13册
- ⬜ Z-library 的 pdf 建国以来毛泽东文稿，第二版共20册，可能 OCR 质量好一点

### 共运史
- ⬜ 中马库
- ⬜ 九评苏共中央的公开信
- ⬜ Z-library 的 epub 或者 pdf

### 通用问题

- ⬜ 对于注释，RAG 场景下，通常是按 chunk 检索，长文章的脚注靠近引用比“全堆在文末”更好。 更合适的方式：
  - 方案 A：脚注紧跟引用——在引用所在的段落后面紧接着写 [^1]: ...，让引用和脚注在同一 chunk 里
  - 方案 B：检索时做“引用补齐”——chunk 里出现 [^1] 时，在送入模型前自动把对应的 [^1]: 内容拼进该 chunk
  - 方案 C：chunk 边界智能切分——切 chunk 时，如果某段有脚注引用，优先把对应脚注一起包含进同一个 chunk

