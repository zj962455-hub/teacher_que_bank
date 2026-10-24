# Lesson 07 精简注释版 · KaTeX 公式渲染

> 上一课:OCR 识别出文字 + 公式块,存了 `uploads/ocr/{task_id}.json`。
> 这一课:**把公式渲染成漂亮的数学排版** —— 不再是 `x²` 这样的纯字符,而是真正的 $x^2$。

---

## 📍 为什么这一课比看起来难

第一次以为很简单:装个 KaTeX,把 `latex` 字段渲染出来就行。

**实际做的时候发现:PaddleOCR 根本不给 latex。**

### PaddleOCR 对数学的两种输出

| 情况 | 返回 | 前端要做什么 |
|---|---|---|
| 复杂公式被识别为独立块 | `{"type":"formula", "latex":"x^{2}+2x+1"}` | 直接 KaTeX 渲染 |
| **简单公式混在文字里** | `{"type":"text", "text":"已知f(x)=x² + 2x + 1"}` | **需要先转 LaTeX** |

实测 `test-question.png`(2026-10-24)走的是**第 2 种** —— `²` 是 **Unicode 字符 U+00B2**,不是 LaTeX。

```
原始 OCR 返回:
  [{'type':'text', 'text':'已知f(x)=x² + 2x + 1'},
   {'type':'text', 'text':'求f(2)的值'}]
```

所以 lesson-07 的真正工作量是:**Unicode 数学文本 → LaTeX → 渲染**。

---

## 🧠 3 个核心概念（读 3 分钟）

### 1. KaTeX vs MathJax

| | KaTeX | MathJax |
|---|---|---|
| 渲染方式 | **同步**（直接输出 HTML） | 异步（先加载再渲染）|
| 速度 | 快,无闪烁 | 慢,加载时有空白 |
| 体积 | ~270KB + 字体 | ~1MB+ |
| 功能 | 够用(99% 场景) | 更全(动态宏包等) |

**选 KaTeX**:decisions.md 已锁。同步渲染这点很关键 —— 我们是 Vue 组件里直接 `v-html`,同步最省事。

### 2. Unicode → LaTeX 映射表

数学符号在 Unicode 里有专门的码位:

```
x²   →  x^{2}          ²  = U+00B2 SUPERSCRIPT TWO
a×b  →  a\times b      ×  = U+00D7 MULTIPLICATION SIGN
x≤y  →  x\leq y        ≤  = U+2264
π    →  \pi            π  = U+03C0 GREEK SMALL LETTER PI
A₁   →  A_{1}          ₁  = U+2081 SUBSCRIPT ONE
√x   →  \sqrt{x}       √  = U+221A
```

**关键坑:LaTeX 命令后面必须跟空格!**

```python
# ❌ 错
"a×b" → "a\timesb"    # LaTeX 把 \timesb 当成未知命令 → 报错
# ✅ 对
"a×b" → "a\\times b"  # 空格隔开
```

根号还要特殊处理:`\sqrt 2` 能渲染但 `\sqrt 2x` 会有歧义(是 √2x 还是 √(2x)?),所以用 `\sqrt{2}`。

### 3. 智能切分(最难的部分)

不能把整段文本丢给 KaTeX:

```
"已知f(x)=x² + 2x + 1"
   ↓ 整段渲染 → KaTeX 会把中文也变成斜体数学字体,非常丑
```

必须切分:**中文正常显示,只有数学片段单独渲染**。

切分规则:
1. 逐字符判断是否"数学字符"(字母数字运算符上下标希腊字母,不含汉字和中文标点)
2. 合并相邻同类片段
3. 用 `_looks_like_formula()` 做最终判定 —— 不够"像公式"的降级成普通文本

**门槛不能太低**,否则 `已知f(x)` 里的 `f(x)` 也会被拆成公式,页面全是碎片。

判定规则(满足任一):
1. 含上下标 / 希腊字母 / 特殊运算符(× ÷ ≤ √ π ∞)
2. 含 `= + < >` 且长度 ≥ 2
3. 纯数字且长度 ≥ 2

**实测效果:**
```
"已知f(x)=x² + 2x + 1"  →  [文本"已知"] [公式"f(x)=x² + 2x + 1"]
"求f(2)的值"              →  [文本"求f(2)的值"]   ← f(2) 不够像公式,保持文本
"解方程：x + 3 = 7"      →  [文本"解方程："] [公式"x + 3 = 7"]
```

---

## 🧭 2 个设计决策（老大拍板）

> 我先把建议写出来,老大看完改/确认:

| # | 决策点 | 选项 | 建议 | 理由 |
|---|---|---|---|---|
| 1 | **转换逻辑放哪** | 前端 JS / 后端 Python | **后端 Python** | 映射表只写一份;拆 block 属于数据清洗;lesson-09 导出 PDF 走后端 Playwright 能直接复用 |
| 2 | 渲染范围 | 只渲染 formula block / 也渲染文本内嵌 `$...$` | **两个都渲染** | PaddleOCR 常把公式和文字混在一个 block 里 |

**老大 2026-10-24 10:14 拍板:走「后端转换 + 拆 block」方案(C)。**

### 为什么放后端(老大问的时候详细说了)

1. **映射表只写一份(Python)** —— 不用 JS/Python 双份维护,改符号只改一处
2. **拆 block 属于数据清洗** —— 后端是"理解 OCR 语义"的地方,前端只管渲染
3. **lesson-09 导出 PDF 复用** —— 那节是后端 Playwright 渲染 PDF,转换逻辑直接能用

---

## 📁 本课最终改动

```
teacher_que_bank/
├── lesson-02/                              ← 后端(转换 + 拆 block)
│   └── app/services/
│       ├── math_parser.py                  ← 新增:Unicode↔LaTeX + 切分
│       └── paddleocr.py                    ← 改:recognize() 返回前调 enrich_blocks()
└── lesson-03/                              ← 前端(渲染)
    ├── package.json                        ← 改:+katex 0.19.1
    ├── src/main.js                         ← 改:import 'katex/dist/katex.min.css'
    ├── src/utils/mathRenderer.js           ← 新增:renderLatex / renderMathText / renderBlock
    ├── src/components/OcrBlockList.vue     ← 改:block 内容走 KaTeX
    └── src/components/QuestionEditor.vue   ← 改:预览走 KaTeX(替掉旧的 ^2→² 转义)
```

---

## 🚀 步骤

### 步骤 1: 装 KaTeX

```bash
cd lesson-03
npm install katex
```
⚠️ **必须同时引入 CSS**,否则公式挤成一团:
```js
// src/main.js
import 'katex/dist/katex.min.css'
```
(Vite 会自动把 woff2 字体打包进 dist,实测验证过)

### 步骤 2: 后端 math_parser.py

核心函数:
```python
unicode_to_latex(text)              # Unicode → LaTeX
split_math_segments(text)           # 切分 → [(片段, 是否公式)]
split_text_block_into_blocks(block)  # 单 block → 多个 block
enrich_blocks(result)                # 整个结果 → 就地拆
```

### 步骤 3: 后端接入

```python
# app/services/paddleocr.py
from app.services.math_parser import enrich_blocks

# recognize() 里,成功路径:
enrich_blocks(data)   # ← 就地改 data["blocks"]
return data
```

### 步骤 4: 前端 mathRenderer.js

```js
renderLatex(latex, displayMode)   # 单个公式
renderMathText(text)               # 文本里的 $...$ 混排
renderBlock(block)                 # 按 type 分派
renderBlocks(blocks)               # 一组
stripMathMarkers(text)             # 去掉 $ 标记(复制用)
```

---

## 🔒 安全:为什么 v-html 是安全的

KaTeX 输出的是 HTML 字符串,必须 `v-html` 才能显示 → 有 XSS 风险。

**三道防线:**
1. `trust: false`(默认)—— 禁用 `\href` `\url` `\includegraphics` 等危险命令
2. `strict: "error"` —— 未知命令直接报错,不静默输出
3. `throwOnError: false` —— 单个公式出错时降级显示原文,不炸整段

**实测验证(2026-10-24):**
```
\href{javascript:alert(1)}{click}
  → 无 <a> 标签 ✅
  → 属性里无 javascript: ✅（仅作为纯文本出现在红色错误提示里）
  → 无 <script> / on*= 事件 ✅

\url{javascript:alert(1)}         → 安全 ✅
\includegraphics{http://x.png}      → 安全 ✅
\htmlClass{evil}{x}              → 安全 ✅
```

---

## ⚠️ 踩过的坑

### 坑 1: LaTeX 命令缺空格
```
"a×b" → "a\timesb"   # LaTeX 认不出 \timesb
✅ 修: 所有命令类替换带尾随空格
```

### 坑 2: 根号要花括号
```
"√2" → "\sqrt 2"    # 能渲染,但 "\sqrt 2x" 有歧义
✅ 修: 正则捕获根号后一个字符 → "\sqrt{2}"
```

### 坑 3: v-for 第二个参数别叫 indexOf
```vue
v-for="(b, indexOf) in blocks"   # ❌ 跟 Array.prototype.indexOf 撞名
v-for="(b, blockIndex) in blocks" # ✅
```
报错:`indexOf is not a function`(Vue 模板编译作用域问题)

### 坑 4: uvicorn --reload 没热重载
改了 `paddleocr.py` 后,`--reload` 没重新加载(可能 watchfiles 延迟)。
**解法**:`kill -HUP <PID>` 强制重载。

### 坑 5: Python 脚本替换 HTML 模板时属性写到了标签外
```vue
<!-- ❌ 改成了这样 -->
<div style="...">
  class="editor-preview"     <!-- 变成纯文本节点了 -->
  v-html="previewHtml"
></div>

<!-- ✅ 属性要在 > 之前 -->
<div style="..." class="editor-preview" v-html="previewHtml"></div>
```

---

## 📚 速查表

### Unicode → LaTeX 常用对照

| Unicode | LaTeX | 说明 |
|---|---|---|
| ² ³ ¹ | `^{2}` `^{3}` `^{1}` | 上标 |
| ₀ ₁ ₂ | `_{0}` `_{1}` `_{2}` | 下标 |
| × ÷ ± ∓ | `\times` `\div` `\pm` `\mp` | 运算符 |
| ≤ ≥ ≠ ≈ ≡ | `\leq` `\geq` `\neq` `\approx` `\equiv` | 比较 |
| √ ∑ ∏ ∫ | `\sqrt` `\sum` `\prod` `\int` | 根号/求和/连乘/积分 |
| α β γ π | `\alpha` `\beta` `\gamma` `\pi` | 希腊字母 |
| ∞ ∂ ∇ | `\infty` `\partial` `\nabla` | 其他 |
| → ← ⇒ | `\rightarrow` `\leftarrow` `\Rightarrow` | 箭头 |
| ∈ ∉ ⊆ ∪ ∩ | `\in` `\notin` `\subseteq` `\cup` `\cap` | 集合 |
| ° ％ | `^\circ` `\%` | 角度/百分号 |

### KaTeX 渲染选项

```js
katex.renderToString(latex, {
  throwOnError: false,   // 公式错时不抛,降级显示
  strict: 'error',       // 未知命令报错
  trust: false,          // 禁用危险命令(默认)
  displayMode: true,     // 块级(独立成行居中)
  macros: { '\\R': '\\mathbb{R}' },  // 常用宏
})
```

### 混排约定

| 写法 | 效果 |
|---|---|
| `$x^2$` | 行内公式 |
| `$$x^2$$` | 块级公式(独立成行居中) |
| `\$100` | 转义的美元符号(不渲染) |

---

## 🧠 这一课的"为什么"多说一句

前 6 课都在处理**数据** —— 传图片、拿文字、存结果。
这一课是**第一次处理"表现"** —— 同样的数据,`x²` 和 $\displaystyle x^2$ 给老师的感觉完全不同。

而这个转折点逼出了一个重要设计决策:**转换逻辑放后端**。

因为一旦涉及"渲染",就要考虑:
- 同一份数据可能渲染到多个地方(网页预览、PDF 导出、以后可能的打印)
- 每处都自己写一遍转换 → 迟早不一致

**所以 lesson-07 不只是"加个 KaTeX",它是把"数学文本"这件事的定义权收拢到后端。**
lesson-09 导出 PDF 时,这个决定会直接省掉一半工作量。

---

## 🎁 动手做任务

### 任务 1: 扩充 Unicode 映射表

现在映射表覆盖了常见符号。补上这些:
- 分数:`½ ⅓ ¼` → `\frac{1}{2}` `\frac{1}{3}` `\frac{1}{4}`
- 希腊字母大小写全覆盖(现在只有部分)
- 集合/逻辑符号:`∀ ∃ ∨ ∧ ¬ → ⇔` 的双字符形式(`⇒ ⇐ ⇔`)

### 任务 2: 公式转纯文本(给复制用)

现在「复制纯文本」按钮复制的是 OCR 原文(`已知f(x)=x² + 2x + 1`)。
但老师复制到 Word 里时,想要的是**带公式排版的纯文本**:
```
已知f(x) = x² + 2x + 1
求 f(2) 的值
```
在 `math_parser.py` 加一个 `latex_to_plain(latex)`,把 `x^{2}` → `x²`,`\frac{1}{2}` → `1/2`。

### 任务 3: 公式编辑(下节课预告)

现在公式是只读的。
加个"点击公式可以编辑 LaTeX 源码"的交互,改完实时预览。
这是 lesson-09 导出 PDF 前的必要步骤 —— 老师总得能修正 OCR 认错的公式。

---

## 🔗 相关文件

- 进度:`../docs/learning-path.md` · 决策:`../docs/decisions.md`(公式 = KaTeX,已锁)
- 上一课:`lesson-06-notes.md`(OCR + 持久化 + 编辑器)
- 后端模块:`lesson-02/app/services/{paddleocr,ocr_store,math_parser}.py`
- 前端模块:`lesson-03/src/{utils/mathRenderer.js,components/OcrBlockList.vue,components/QuestionEditor.vue}`
