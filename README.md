# iskra-x2md

[![Python](https://img.shields.io/badge/python-3.14+-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
![Status](https://img.shields.io/badge/Status-Active-success)

---

`iskra-x2md` 为 [iskra-data](https://github.com/Qhbee/iskra-data) 提供内容，将其需要的各种格式的资料转换为机器友好的、语义清晰的 **Markdown** 格式。

**Input:** PDF, DOCX, EPUB, HTML, TXT and more  
**Output:** clean, structured GitHub Flavored Markdown (GFM)

---

## TODO

### 马克思、恩格斯

- 🔄 Z-library 的 pdf，说是第二版，其实只有第一卷是第二版，其余为同中马库，但是多了书签
- 🔄 中马库 [马克思恩格斯全集（文字版）](https://www.marxists.org/chinese/marx-engels/index.htm) 共 50 卷，不全
- 🔄 中马库 [马克思恩格斯全集·Ⅰ版（文字版PDF）](https://www.marxists.org/chinese/pdf/me-old.htm) 共 50 卷
- ⬜ 中马库 [马克思恩格斯全集·Ⅱ版（文字版PDF）](https://www.marxists.org/chinese/pdf/me-2.htm) 有增删，翻译质量更好，卷数更多，但是没出完，不全
- ⬜ 中马库 [《马克思恩格斯文集》10卷本PDF（2009年版）](https://www.marxists.org/chinese/pdf/me-2.htm) 共 10 卷，非文字版，需要 OCR

### 列宁

- ❌ Z-library 的 epub （尝试后发现，实际来源是“中马库” [列宁全集（文字网页版）](https://www.marxists.org/chinese/lenin-cworks/index.htm) 的 旧版 HTML，而且缺少）
- 🔄 Z-library 的 pdf，同中马库，但是多了书签
- ⬜ 中马库 [列宁全集（中文第二版-文字版PDF）](https://www.marxists.org/chinese/pdf/lenin-old.htm)，从文字版 PDF 解析，但是缺少第54-第60卷，以及《列宁全集补遗》
- ⬜ 中马库 [列宁全集（中文第二版-图像版PDF）](https://www.marxists.org/chinese/pdf/lenin.htm)，以后 OCR 第54-第60卷
- ⬜ 中马库 [列宁全集（版本II-2017年增订版-图像版PDF）](https://www.marxists.org/chinese/pdf/lenin-2017.htm)，有书签，需要 OCR
- ⬜ 列宁全集补遗两卷，属于第一版，但只找到第一卷，没有第二卷

### 斯大林

- 🔄 诸夏怀斯社版-斯大林全集20卷，文字版 PDF，但很可能有一些错误的多余的
- 🔄 诸夏怀斯社版-斯大林全集附卷10卷，文字版 PDF，但很可能有一些错误的多余的
- ✅ 诸夏怀斯社版-斯大林选集4卷，文字版 PDF，已经解析
- ⬜ 斯大林吧-斯大林文论.doc，应该校对过，去掉了一些错误

### 毛泽东
- 🔄 毛泽东选集（1-7卷_静火版）.epub
- ⬜ 毛泽东选集（1-7：原版五卷+静火+赤旗+草堂）.pdf
- ⬜ 毛泽东文集-中共中央文献研究室.epub
- ⬜ 毛泽东年谱（全九卷_正常目录）.epub

### 共运史
- ⬜ 中马库
- ⬜ Z-library 的 epub 或者 pdf

