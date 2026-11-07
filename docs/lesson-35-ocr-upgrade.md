# 课 35 · OCR 识别率问题（灰度实测 2026-11-07）

> 结论先行：**当前识别结果的错，主要不是「模型不够聪明」，而是两个具体原因** ——
> ① 上传截图分辨率太低（短边只有 90~330 像素），小符号（∠ ⊥ 分数）直接检测不到；
> ② mobile rec 模型把这些符号认成别的字（∠→Z、⊥→I/L、60°→6O°）。
> 修法是「先放大再识别 + 后端纠错规则」，先不上换模型。

## 一、实测样本（老师 2026-11-07 15:37~15:44 上传的真实截图）

| 样本 | 尺寸 | 内容 | mobile rec 实际输出 |
|---|---|---|---|
| A | 639×239 | △ABC 中 ∠B=∠C=60°，DE⊥AB，求 CE | B=ZC=60°（∠→Z） |
| B | 644×205 | 已知 OC 平分 ∠AOB，PD⊥OA，∠AOB=30° | ZAOB、PDLOA（∠→Z、⊥→L） |
| C | 627×91 | ①∠A+∠B=∠C ②∠A:∠B:∠C=1:2:3 ③∠A=90°-∠B ④∠A=∠B=1/2∠C | ZA+ZB=ZC，分数整段丢失 |
| D | 650×326 | 等边△ABC，BQ⊥AD，求证 PQ=1/2BP（含三角形图） | BQIAD（⊥→I），分数变成散块 |
| E | 436×90 | 具备下列条件的△ABC中…（含三角形符号） | A.A=B=3C（∠ 整个消失） |

## 二、根因（已实测验证）

1. **分辨率太低**：这 5 张截图短边只有 90~326 像素，检测框在这一层根本找不到
   竖式分数和 ∠。放大 2~3 倍后，样本 D 的分数变成可识别的两个小块
   （分子 1、分母 2），样本 C 的分数分子 1 也被找回。
2. **mobile rec 不认数学符号**：∠ 被读成 Z 或直接丢失，⊥ 被读成 I / L，
   60° 被读成 6O°。
3. **「公式块」其实是后端伪造的**：线上跑的是 paddleocr **2.7.3**，它
   **不支持** PP-StructureV3（SUPPORT_OCR_MODEL_VERSION 只有 PP-OCR~v4），
   而 ocr.py 里的 _iter_formulas / _iter_tables 按 3.x 的
   page["res"]["blocks"] 结构取数据 —— 永远取不到。
   所以历史记录里那些 type=formula 块，全是后端 enrich_blocks
   把文本按数学字符切出来的伪公式（所以会出现 A.A=B=3C 这种）。

## 三、本轮落地的修复

| 修复 | 位置 | 作用 |
|---|---|---|
| 小图放大 | deploy/paddleocr/app/ocr.py（_preprocess） | 短边 < OCR_MIN_SIDE（默认 350）时整体放大 OCR_UPSCALE 倍（默认 2），长边 ≥ OCR_MAX_LONG（默认 2400）不放大；bbox 按倍数缩回原图坐标，前端高亮框不错位 |
| 符号纠错 | lesson-02/app/services/ocr_fixups.py（fix_math_symbols） | ∠（Z/7/L 开头）、⊥（I/l/1/L）、60°（6O°）自动还原；只在「像数学文本」时生效，英文单词不受影响 |
| 竖式分数重建 | lesson-02/app/services/ocr_fixups.py（rebuild_fractions） | 分子/分母两块靠 bbox 几何拼回一个分数公式块；条件不满足宁可不拼 |
| 接入点 | lesson-02/app/services/math_parser.py（enrich_blocks） | 顺序：先纠错 → 再重建分数 → 再切 text/formula |
| 单测 | lesson-02/tests/test_ocr_fixups.py | 符号 9 类 + 分数合并/不误合 + 集成用例 |

## 四、还没做（需要老大拍板）

- **换识别模型**：ModelScope 上有 PaddlePaddle/PP-OCRv5_server_rec 和
  公式模型 PaddlePaddle/PP-FormulaNet-S。但实测 v4 server rec 对 ∠ 这类符号
  **更差**（直接吞掉，变成 A+B=C），CPU 上还慢 3~5 倍（2~6s/张）。
  真正能解决公式的是 **PP-FormulaNet**（直接输出 LaTeX），但它需要
  paddleocr 3.x 的 PP-StructureV3 pipeline，属于换引擎级改造 ——
  内存峰值约 2~3GB，当前机器 2C4G 刚好卡线。
- **图形本身无法 OCR**：题目里的三角形示意图，OCR 只能读出旁边的小字母
  （B、D 这类标签）。图必须靠老师自己补，或后续接多模态模型描述。

## 五、复测口径

改动后用同一批 5 张样本再跑一遍，对比：
① ∠/⊥/° 是否还原；② 分数是否拼成分数块；③ 单张耗时（放大后变慢多少）；
④ 前端高亮框是否还对得上原图。