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

    def test_formula_block_untouched(self):
        original = {"type": "formula", "latex": "x^2"}
        self.assertEqual(split_text_block_into_blocks(original), [original])

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
