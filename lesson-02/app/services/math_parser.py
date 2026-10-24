# lesson-02/app/services/math_parser.py
"""数学文本 → LaTeX 转换 + block 拆分 — lesson-07

背景
----
PaddleOCR (PP-StructureV3) 对数学公式有**两种输出**：

1. 识别为独立块 → ``{"type": "formula", "latex": "x^{2}+2x+1"}``
   → 前端直接 KaTeX 渲染,无需处理

2. 混在文字里 → ``{"type": "text", "text": "已知f(x)=x² + 2x + 1"}``
   → 这里的 ``²`` 是 **Unicode 字符**,不是 LaTeX,KaTeX 渲染不了

实际测试(2026-10-24,test-question.png)走的是第 2 种。
所以要在后端把 Unicode 数学文本转成 LaTeX,并从 text block 里拆出 formula block。

为什么放后端做(而不是前端)
--------------------------
1. 映射表只写一份(Python),不用 JS/Python 双份维护
2. 拆 block 属于"数据清洗",后端是理解 OCR 语义的地方
3. lesson-09 导出 PDF 走的是后端 Playwright,转换逻辑能直接复用

核心难点
--------
不能整段丢给 KaTeX —— "已知f(x)=x²" 如果整段渲染,中文会变成斜体数学字体,很丑。
必须**智能切分**:中文/普通文字正常显示,只有数学片段单独渲染成公式。
"""

import re
from typing import Any


# === Unicode → LaTeX 映射表 ===

# 上标/下标(数学里最常见的)
SUPERSCRIPTS = {
    "⁰": "^{0}", "¹": "^{1}", "²": "^{2}", "³": "^{3}", "⁴": "^{4}",
    "⁵": "^{5}", "⁶": "^{6}", "⁷": "^{7}", "⁸": "^{8}", "⁹": "^{9}",
    "⁺": "^{+}", "⁻": "^{-}", "⁼": "^{\\pm}", "⁽": "^{(}", "⁾": ")^{}",
    # --- 字母上标(Unicode 组合上下标,求和/导数常用)---
    "ⁱ": "^{i}", "ⁿ": "^{n}", "ᵃ": "^{a}", "ᵇ": "^{b}", "ᶜ": "^{c}",
    "ᵈ": "^{d}", "ᵉ": "^{e}", "ᶠ": "^{f}", "ᵍ": "^{g}", "ʰ": "^{h}",
    "ⱼ": "^{j}", "ᵏ": "^{k}", "ˡ": "^{l}", "ᵐ": "^{m}", "ᵒ": "^{o}",
    "ᵖ": "^{p}", "ʳ": "^{r}", "ˢ": "^{s}", "ᵗ": "^{t}", "ᵘ": "^{u}",
    "ᵛ": "^{v}", "ʷ": "^{w}", "ˣ": "^{x}", "ʸ": "^{y}", "ᶻ": "^{z}",
}

SUBSCRIPTS = {
    "₀": "_{0}", "₁": "_{1}", "₂": "_{2}", "₃": "_{3}", "₄": "_{4}",
    "₅": "_{5}", "₆": "_{6}", "₇": "_{7}", "₈": "_{8}", "₉": "_{9}",
    "₊": "_{+}", "₋": "_{-}", "₌": "_{=}", "₍": "_{(}", "₎": ")_{}",
    # --- 字母下标(Unicode 组合上下标,求和下限常用)---
    "ₐ": "_{a}", "ₑ": "_{e}", "ₕ": "_{h}", "ᵢ": "_{i}", "ⱼ": "_{j}",
    "ₖ": "_{k}", "ₗ": "_{l}", "ₘ": "_{m}", "ₙ": "_{n}", "ₒ": "_{o}",
    "ₚ": "_{p}", "ᵣ": "_{r}", "ₛ": "_{s}", "ₜ": "_{t}", "ᵤ": "_{u}",
    "ᵥ": "_{v}", "ₓ": "_{x}",
}

# 希腊字母（大小写全覆盖 + 常见变体）
# 注意:小写 epsilon/phi/rho/theta 有两种写法,varepsilon/varphi 是印刷体
GREEK = {
    # --- 小写 ---
    "α": "\\alpha", "β": "\\beta", "γ": "\\gamma", "δ": "\\delta",
    "ε": "\\varepsilon", "ϵ": "\\epsilon", "ζ": "\\zeta", "η": "\\eta",
    "θ": "\\theta", "ϑ": "\\vartheta", "ι": "\\iota", "κ": "\\kappa",
    "λ": "\\lambda", "μ": "\\mu", "ν": "\\nu", "ξ": "\\xi",
    "ο": "\\omicron", "π": "\\pi", "ρ": "\\rho", "ϱ": "\\varrho",
    "σ": "\\sigma", "ς": "\\varsigma", "τ": "\\tau", "υ": "\\upsilon",
    "φ": "\\varphi", "ϕ": "\\phi", "χ": "\\chi", "ψ": "\\psi",
    "ω": "\\omega",
    # --- 大写 ---
    "Α": "\\Alpha", "Β": "\\Beta", "Γ": "\\Gamma", "Δ": "\\Delta",
    "Ε": "\\Epsilon", "Ζ": "\\Zeta", "Η": "\\Eta", "Θ": "\\Theta",
    "Ι": "\\Iota", "Κ": "\\Kappa", "Λ": "\\Lambda", "Μ": "\\Mu",
    "Ν": "\\Nu", "Ξ": "\\Xi", "Ο": "\\Omicron", "Π": "\\Pi",
    "Ρ": "\\Rho", "Σ": "\\Sigma", "Τ": "\\Tau", "Υ": "\\Upsilon",
    "Φ": "\\Phi", "Χ": "\\Chi", "Ψ": "\\Psi", "Ω": "\\Omega",
}

# 运算符与符号
OPERATORS = {
    "×": "\\times", "÷": "\\div", "±": "\\pm", "∓": "\\mp",
    "≤": "\\leq", "≥": "\\geq", "≠": "\\neq", "≈": "\\approx",
    "≡": "\\equiv", "∞": "\\infty", "∂": "\\partial",
    "∇": "\\nabla", "∫": "\\int", "∑": "\\sum", "∏": "\\prod",
    "√": "\\sqrt", "∠": "\\angle", "∥": "\\parallel", "⊥": "\\perp",
    "∈": "\\in", "∉": "\\notin", "⊆": "\\subseteq", "∅": "\\emptyset",
    "∪": "\\cup", "∩": "\\cap", "⊂": "\\subset", "⊃": "\\supset",
    "→": "\\rightarrow", "←": "\\leftarrow", "⇒": "\\Rightarrow",
    "⇔": "\\Leftrightarrow", "∀": "\\forall", "∃": "\\exists",
    "¬": "\\neg", "∧": "\\land", "∨": "\\lor",
    "°": "^\\circ", "％": "\\%", "‰": "\\permil",
    # --- 双字符形式(逻辑/集合常用) ---
    "⇒": "\\Rightarrow", "⇐": "\\Leftarrow", "⇔": "\\Leftrightarrow",
    "↔": "\\leftrightarrow", "⇅": "\\Updownarrow",
    "≪": "\\ll", "≫": "\\gg", "≶": "\\lessgtr", "≷": "\\gtrless",
    # --- 集合/逻辑补充 ---
    "∴": "\\therefore", "∵": "\\because",
    "⊙": "\\odot", "⊗": "\\otimes", "⊕": "\\oplus",
    "⊤": "\\top", "⊥": "\\perp", "⊣": "\\dashv",
    # --- 省略号 ---
    "⋯": "\\cdots", "⋮": "\\vdots", "⋱": "\\ddots",
    # --- 撇号(导数) ---
    "′": "^\\prime", "″": "^{\\prime\\prime}",
    # --- 其他常用 ---
    "ℝ": "\\mathbb{R}", "ℕ": "\\mathbb{N}", "ℤ": "\\mathbb{Z}",
    "ℚ": "\\mathbb{Q}", "ℂ": "\\mathbb{C}",
}

# === Unicode 分数( vulgar fraction )===
# 这些字符本身就是"分子/分母"的形式,直接转成 \frac
FRACTIONS = {
    "½": "\\frac{1}{2}", "⅓": "\\frac{1}{3}", "⅔": "\\frac{2}{3}",
    "¼": "\\frac{1}{4}", "¾": "\\frac{3}{4}",
    "⅕": "\\frac{1}{5}", "⅖": "\\frac{2}{5}", "⅗": "\\frac{3}{5}",
    "⅘": "\\frac{4}{5}", "⅙": "\\frac{1}{6}", "⅚": "\\frac{5}{6}",
    "⅐": "\\frac{1}{7}", "⅛": "\\frac{1}{8}", "⅜": "\\frac{3}{8}",
    "⅝": "\\frac{5}{8}", "⅞": "\\frac{7}{8}",
}

# 希腊字母也要能被识别为"数学字符"
GREEK_CHARS = "".join(GREEK.keys())

# 数学片段里可能出现的字符
# 注意:这里刻意不含普通汉字,也不含中英文标点
MATH_CHARS = (
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789"
    "+-*/=<>()[]{}.,:;'\"!|"
    " "  # 空格(公式内部)
    + "".join(SUPERSCRIPTS.keys())
    + "".join(SUBSCRIPTS.keys())
    + "".join(FRACTIONS.keys())
    + GREEK_CHARS
    + "".join(OPERATORS.keys())
)


# === 组合上下标序列的正则 ===
# Unicode 的组合上下标(如 ∑ 的下限 "ᵢ₌₁") 是一整组字符,
# 逐字符转换会得到 "_{i}_{=}_{1}" → LaTeX 报 "Double subscript"。
# 所以要先识别连续序列, 整体包成一个 _{...} / ^{...}。
_SUPERSCRIPT_SEQ_RE = re.compile(f"[{re.escape(''.join(SUPERSCRIPTS.keys()))}]+")
_SUBSCRIPT_SEQ_RE = re.compile(f"[{re.escape(''.join(SUBSCRIPTS.keys()))}]+")


def _merge_script_sequences(text: str) -> str:
    """把连续的上下标字符合并成一个组

    "ᵢ₌₁" → "_{i=1}"
    "ⁿ"   → "^{n}"
    "xₖ₊₁" → "x_{k+1}"
    """

    def sup_repl(m: re.Match) -> str:
        content = "".join(
            SUPERSCRIPTS[c][2:-1] if c in SUPERSCRIPTS else c  # 去掉 ^{ } 包装
            for c in m.group(0)
        )
        return "^{" + content + "}"

    def sub_repl(m: re.Match) -> str:
        content = "".join(
            SUBSCRIPTS[c][2:-1] if c in SUBSCRIPTS else c  # 去掉 _{ } 包装
            for c in m.group(0)
        )
        return "_{" + content + "}"

    text = _SUPERSCRIPT_SEQ_RE.sub(sup_repl, text)
    text = _SUBSCRIPT_SEQ_RE.sub(sub_repl, text)
    return text


def unicode_to_latex(text: str) -> str:
    """把 Unicode 数学字符转成 LaTeX

    >>> unicode_to_latex("x²")
    'x^{2}'
    >>> unicode_to_latex("a×b")
    'a\\\\times b'
    """
    if not text:
        return text

    result = text
    # ⚠️ 第一步:先合并组合上下标序列
    # "ᵢ₌₁" 这种连续上下标必须整体转, 逐字符转会产生 "_{i}_{=}_{1}" → Double subscript 错误
    result = _merge_script_sequences(result)
    # 顺序有讲究:先替换组合符号(√ ∑ 等),再替换希腊字母,最后上下标
    #
    # ⚠️ 关键:命令类替换必须带尾随空格
    # -----------------------------------
    # LaTeX 里 \timesb 会被当成"名为 timesb 的未知命令"→ 渲染报错。
    # 所以 \times 后面要跟空格:a\times b。
    # 上下标标记 ^{} _{} 自带花括号,后面直接跟字母是合法的,不用加空格。
    # 分数:½ → \frac{1}{2}(先处理,含花括号,后面跟字符不会歧义)
    for ch, latex in FRACTIONS.items():
        result = result.replace(ch, latex)

    # 根号要特殊处理:\sqrt{x} 而不是 \sqrt x
    # (\sqrt 2 在 LaTeX 里能渲染,但 \sqrt 2x 的根号范围会歧义 —— 是 √2x 还是 √(2x)?)
    result = re.sub(r"√\s*([^\s,.;:!?()\[\]{}+*=<>-])", r"\\sqrt{\1}", result)

    for ch, latex in OPERATORS.items():
        if ch == "√":
            continue  # 已单独处理
        result = result.replace(ch, latex + " ")
    for ch, latex in GREEK.items():
        result = result.replace(ch, latex + " ")
    for ch, latex in SUPERSCRIPTS.items():
        result = result.replace(ch, latex)
    for ch, latex in SUBSCRIPTS.items():
        result = result.replace(ch, latex)

    return result


def _is_math_char(ch: str) -> bool:
    """判断字符是否属于数学片段"""
    return ch in MATH_CHARS


def _looks_like_formula(chunk: str) -> bool:
    """判断一个数学片段是否值得单独渲染成公式

    门槛不能太低 —— 否则 "已知 f(x)" 里的 f(x) 也会被拆成公式,页面全是碎片。
    规则(满足任一):
      1. 含上下标/希腊字母/特殊运算符 → 明确是公式
      2. 含运算符(= + - × ÷ < > 等)且长度 ≥ 2
      3. 纯数字且长度 ≥ 2(多位数)
    """
    if not chunk:
        return False

    stripped = chunk.strip()
    if not stripped:
        return False

    # 规则 1:明确数学符号
    if any(c in chunk for c in SUPERSCRIPTS) or any(c in chunk for c in SUBSCRIPTS):
        return True
    if any(c in chunk for c in FRACTIONS):
        return True
    if any(c in chunk for c in GREEK):
        return True
    if any(c in OPERATORS for c in chunk):
        # 但单独的 "a-b" 这种可能是英文单词里的连字符,要求有真正的运算符
        for op in ("×", "÷", "≤", "≥", "≠", "≈", "√", "∑", "∫", "∏", "π", "∞"):
            if op in chunk:
                return True

    # 规则 2:含等号/加号等,且不是单个字母
    if len(stripped) >= 2 and any(c in chunk for c in "=+<>≤≥"):
        return True

    # 规则 3:多位数
    if len(stripped) >= 2 and stripped.replace(".", "").isdigit():
        return True

    return False


def split_math_segments(text: str) -> list[tuple[str, bool]]:
    """把一段文本切成 [(片段, 是否公式), ...]

    例子:
      "已知f(x)=x² + 2x + 1"
      → [("已知", False), ("f(x)=", True), ("x", False), ("2", False),
         (" + ", False), ("2x", True), (" + ", False), ("1", False)]

      实际实现里会合并相邻的同类型片段。
    """
    if not text:
        return []

    segments: list[tuple[str, bool]] = []
    buffer = ""
    buffer_is_math = False

    for ch in text:
        is_math = _is_math_char(ch)

        if not buffer:
            buffer = ch
            buffer_is_math = is_math
            continue

        if is_math == buffer_is_math:
            buffer += ch
        else:
            segments.append((buffer, buffer_is_math))
            buffer = ch
            buffer_is_math = is_math

    if buffer:
        segments.append((buffer, buffer_is_math))

    # 合并相邻同类型,并用 _looks_like_formula 做最终判定
    merged: list[tuple[str, bool]] = []
    for seg, is_math in segments:
        if merged and merged[-1][1] == is_math:
            merged[-1] = (merged[-1][0] + seg, is_math)
        else:
            merged.append((seg, is_math))

    # 逐个判定:数学片段如果不够"像公式",降级成普通文本
    result: list[tuple[str, bool]] = []
    for seg, is_math in merged:
        if is_math and not _looks_like_formula(seg):
            is_math = False
        if result and result[-1][1] == is_math:
            result[-1] = (result[-1][0] + seg, is_math)
        else:
            result.append((seg, is_math))

    return result


def split_text_block_into_blocks(block: dict[str, Any]) -> list[dict[str, Any]]:
    """把一个 text block 拆成 text / formula 多个 block

    已经是 formula 或 table 的 block 原样返回。

    >>> split_text_block_into_blocks({"type":"text","text":"求x²","confidence":0.9})
    [{'type': 'text', 'text': '求'}, {'type': 'formula', 'latex': 'x^{2}', ...}]
    """
    if not isinstance(block, dict):
        return []

    block_type = block.get("type")

    # formula / table 原样返回
    if block_type in ("formula", "table"):
        return [block]

    if block_type != "text":
        return [block]

    text = block.get("text", "")
    if not text:
        return [block]

    segments = split_math_segments(text)

    # 没有可拆的部分 → 原样返回
    if not any(is_math for _, is_math in segments):
        return [block]

    out: list[dict[str, Any]] = []
    for seg, is_math in segments:
        if not seg:
            continue
        if is_math:
            out.append({
                "type": "formula",
                "latex": unicode_to_latex(seg.strip()),
                "bbox": block.get("bbox"),
                "confidence": block.get("confidence"),
            })
        else:
            out.append({
                "type": "text",
                "text": seg,
                "bbox": block.get("bbox"),
                "confidence": block.get("confidence"),
            })

    return out


def enrich_blocks(result: dict[str, Any]) -> dict[str, Any]:
    """把 OCR 结果里的 text block 拆成 text/formula 混合

    就地修改 result["blocks"],返回同一个 dict。
    """
    if not isinstance(result, dict):
        return result

    blocks = result.get("blocks")
    if not isinstance(blocks, list):
        return result

    new_blocks: list[dict[str, Any]] = []
    for block in blocks:
        new_blocks.extend(split_text_block_into_blocks(block))

    result["blocks"] = new_blocks
    return result
