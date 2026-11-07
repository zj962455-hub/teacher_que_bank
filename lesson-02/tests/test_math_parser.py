"""math_parser 单元测试 — lesson-07

跑法（零依赖,标准库 unittest）:
    cd lesson-02
    python3 -m unittest discover tests -v

为什么不用 pytest:
    项目里没装,lesson-08 之前不引入额外依赖。
    unittest 是标准库,零成本。
"""

import sys
import unittest
from pathlib import Path

# 让 tests/ 目录下的测试能 import 到 app 包
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.math_parser import (  # noqa: E402
    unicode_to_latex,
    split_math_segments,
    split_text_block_into_blocks,
    enrich_blocks,
    normalize_math_spacing,
    latex_to_plain,
)


class TestUnicodeToLatex(unittest.TestCase):
    """Unicode 数学字符 → LaTeX"""

    def test_superscript(self):
        self.assertEqual(unicode_to_latex("x²"), "x^{2}")
        self.assertEqual(unicode_to_latex("A₁"), "A_{1}")

    def test_command_needs_trailing_space(self):
        """LaTeX 命令后面必须跟空格,否则 \timesb 会被当成未知命令"""
        self.assertEqual(unicode_to_latex("a×b"), "a\\times b")
        self.assertEqual(unicode_to_latex("x≤y"), "x\\leq y")

    def test_greek(self):
        self.assertEqual(unicode_to_latex("πr²"), "\\pi r^{2}")
        self.assertEqual(unicode_to_latex("Ω"), "\\Omega ")

    def test_sqrt_uses_braces(self):
        """根号必须带花括号,否则 \\sqrt 2x 有歧义"""
        self.assertEqual(unicode_to_latex("√2"), "\\sqrt{2}")

    def test_fractions(self):
        self.assertEqual(unicode_to_latex("½"), "\\frac{1}{2}")
        self.assertEqual(unicode_to_latex("¼"), "\\frac{1}{4}")

    def test_combined_script_sequences(self):
        """组合上下标必须整体转,逐字符转会产生 Double subscript 错误"""
        self.assertEqual(unicode_to_latex("xₖ₊₁"), "x_{k+1}")
        self.assertEqual(unicode_to_latex("∑ᵢ₌₁ⁿ"), "\\sum _{i=1}^{n}")

    def test_empty(self):
        self.assertEqual(unicode_to_latex(""), "")


class TestSplitMathSegments(unittest.TestCase):
    """智能切分:中文保持文本,数学片段单独拆出"""

    def _split(self, text):
        return [(s, is_math) for s, is_math in split_math_segments(text)]

    def test_chinese_stays_text(self):
        segs = self._split("已知f(x)=x² + 2x + 1")
        self.assertEqual(segs[0], ("已知", False))
        self.assertTrue(any(m for _, m in segs), "应该有公式片段")

    def test_simple_expression_stays_text(self):
        """f(2) 不够"像公式",应该保持文本,否则页面全是碎片"""
        segs = self._split("求f(2)的值")
        self.assertFalse(any(m for _, m in segs), "不应该拆出公式")

    def test_equation_split(self):
        segs = self._split("解方程：x + 3 = 7")
        self.assertEqual(segs[0][0], "解方程：")
        self.assertTrue(segs[1][1], "x + 3 = 7 应该是公式")

    def test_new_symbols(self):
        segs = self._split("已知½+¼")
        self.assertTrue(any(m for _, m in segs), "分数应被识别为公式")

    def test_empty(self):
        self.assertEqual(split_math_segments(""), [])


class TestSplitBlocks(unittest.TestCase):
    """block 拆分"""

    def test_text_block_split(self):
        blocks = split_text_block_into_blocks({
            "type": "text", "text": "已知f(x)=x²", "confidence": 0.9,
        })
        self.assertEqual(len(blocks), 2)
        self.assertEqual(blocks[0]["type"], "text")
        self.assertEqual(blocks[1]["type"], "formula")
        self.assertEqual(blocks[1]["latex"], "f(x)=x^{2}")

    def test_formula_block_cleaned_not_split(self):
        """lesson-35: 公式块不再「原样返回」

        以前 formula block 直接透传，导致两件事：
        - 强模型把中文包进公式 → KaTeX 报错吐红字
        - "C E=" 这种字母间空格原样进库
        现在公式块会做清理（压空格 / 拆中文），但干净的公式
        仍然是一个公式块，latex 不变。
        """
        blocks = split_text_block_into_blocks({"type": "formula", "latex": "x^2"})
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0]["type"], "formula")
        self.assertEqual(blocks[0]["latex"], "x^2")

    def test_table_block_untouched(self):
        original = {"type": "table", "html": "<table></table>"}
        self.assertEqual(split_text_block_into_blocks(original), [original])

    def test_bbox_preserved(self):
        """拆出来的 block 要保留 bbox,否则 lesson-04 的原图高亮会失效"""
        blocks = split_text_block_into_blocks({
            "type": "text", "text": "已知x²", "bbox": [1, 2, 3, 4], "confidence": 0.9,
        })
        for b in blocks:
            self.assertEqual(b["bbox"], [1, 2, 3, 4])


class TestEnrichBlocks(unittest.TestCase):
    """整体处理"""

    def test_enrich_in_place(self):
        result = {"blocks": [
            {"type": "text", "text": "已知f(x)=x² + 2x + 1", "confidence": 0.85},
            {"type": "text", "text": "求f(2)的值", "confidence": 0.99},
        ]}
        enrich_blocks(result)
        types = [b["type"] for b in result["blocks"]]
        self.assertIn("formula", types)
        self.assertEqual(len(result["blocks"]), 3)

    def test_no_math_no_change(self):
        """没有数学内容的 text block 不该被拆"""
        original = {"blocks": [{"type": "text", "text": "求f(2)的值"}]}
        result = {"blocks": [{"type": "text", "text": "求f(2)的值"}]}
        enrich_blocks(result)
        self.assertEqual(len(result["blocks"]), len(original["blocks"]))

    def test_invalid_input(self):
        self.assertEqual(enrich_blocks({}), {})
        self.assertEqual(enrich_blocks({"blocks": "not a list"}), {"blocks": "not a list"})



class TestLesson35FormulaCleanup(unittest.TestCase):
    """lesson-35：公式块清理

    背景（老师报「识别不准」，实际是三个不同根因）：
    1. 强模型把「OB 于 E,\angle AOB=30^{\circ}」整段包进 $...$
       → 公式里混了中文 → KaTeX 渲染报错 → 页面吐一行红字源码
    2. OCR 的字母间噪声空格：A E=C D / C E=
    3. 角度单位 ^{\circ} 在转纯文本时被丢掉 → "30^"
    """

    def test_normalize_spacing_single_uppercase_letters(self):
        self.assertEqual(normalize_math_spacing("A E=C D"), "AE=CD")
        self.assertEqual(normalize_math_spacing("C E="), "CE=")

    def test_normalize_spacing_keeps_real_segments(self):
        """AB CD 是两个线段，不能压成 ABCD"""
        self.assertEqual(normalize_math_spacing("AB CD"), "AB CD")
        self.assertEqual(normalize_math_spacing("AD=1,BC=6"), "AD=1,BC=6")
        self.assertEqual(normalize_math_spacing(""), "")

    def test_formula_with_cjk_is_split(self):
        blocks = split_text_block_into_blocks({
            "type": "formula",
            "latex": "OB 于 E,\\angle AOB=30^{\\circ}",
        })
        types = [b["type"] for b in blocks]
        self.assertIn("text", types)
        self.assertIn("formula", types)
        # 中文必须不在 formula 块里 —— KaTeX 渲染不了
        for b in blocks:
            if b["type"] == "formula":
                self.assertNotIn("于", b["latex"])

    def test_formula_plain_keeps_degree(self):
        blocks = split_text_block_into_blocks({
            "type": "formula",
            "latex": "E,\\angle AOB=30^{\\circ}",
        })
        formula = [b for b in blocks if b["type"] == "formula"][0]
        self.assertEqual(formula["plain"], "E,∠AOB=30°")

    def test_enrich_blocks_normalizes_and_splits(self):
        result = {"blocks": [
            {"type": "formula", "latex": "OB 于 E,\\angle AOB=30^{\\circ}"},
            {"type": "formula", "latex": "C E="},
        ]}
        enrich_blocks(result)
        types = [b["type"] for b in result["blocks"]]
        self.assertIn("text", types)
        lates = [b["latex"] for b in result["blocks"] if b["type"] == "formula"]
        self.assertIn("CE=", lates)
        self.assertTrue(all("于" not in l for l in lates))

    def test_latex_to_plain_degree(self):
        self.assertEqual(latex_to_plain("30^{\\circ}"), "30°")


if __name__ == "__main__":
    unittest.main(verbosity=2)

