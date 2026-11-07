"""ocr_fixups 单元测试 —— 2026-11-07 灰度实测发现的符号误识别 + 分数重建"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.ocr_fixups import (  # noqa: E402
    fix_math_symbols,
    looks_like_math,
    rebuild_fractions,
)
from app.services.math_parser import enrich_blocks  # noqa: E402


class TestFixMathSymbols(unittest.TestCase):

    def test_angle_from_z(self):
        self.assertEqual(fix_math_symbols("①ZA+ZB=ZC"), "①∠A+∠B=∠C")

    def test_angle_from_z_with_multi_letter(self):
        self.assertEqual(fix_math_symbols("已知OC平分ZAOB"), "已知OC平分∠AOB")

    def test_angle_from_leading_l(self):
        self.assertEqual(fix_math_symbols("已知OC平分LAOB"), "已知OC平分∠AOB")

    def test_perp_from_i(self):
        self.assertEqual(fix_math_symbols("BQIAD于点Q."), "BQ⊥AD于点Q.")

    def test_perp_from_l_and_one(self):
        self.assertEqual(fix_math_symbols("已知PDLOA于D"), "已知PD⊥OA于D")
        self.assertEqual(fix_math_symbols("点D在AB边上，DEIAB，并与AC边交于点E"),
                         "点D在AB边上，DE⊥AB，并与AC边交于点E")

    def test_degree_zero(self):
        self.assertEqual(fix_math_symbols("B=ZC=6O°"), "B=∠C=60°")

    def test_english_not_broken(self):
        self.assertEqual(fix_math_symbols("Zoom In"), "Zoom In")
        self.assertEqual(fix_math_symbols("ICBC bank"), "ICBC bank")

    def test_plain_chinese_untouched(self):
        self.assertEqual(fix_math_symbols("已知ABC是三角形"), "已知ABC是三角形")

    def test_looks_like_math(self):
        self.assertTrue(looks_like_math("∠A=∠B"))
        self.assertTrue(looks_like_math("BQIAD于点Q."))
        self.assertFalse(looks_like_math("纯中文描述，没有数学内容"))


class TestRebuildFractions(unittest.TestCase):

    def _blocks(self):
        return [
            {"type": "text", "text": "（2）求证：PQ=", "bbox": [12, 265, 125, 283], "confidence": 0.97},
            {"type": "text", "text": "1", "bbox": [130, 255, 136, 265], "confidence": 0.9},
            {"type": "text", "text": "2", "bbox": [130, 268, 136, 278], "confidence": 0.9},
            {"type": "text", "text": "BP", "bbox": [140, 265, 160, 283], "confidence": 0.9},
        ]

    def test_fraction_merged(self):
        out = rebuild_fractions(self._blocks())
        latex = [b.get("latex") for b in out if b.get("type") == "formula"]
        self.assertIn("\\frac{1}{2}", latex)
        self.assertEqual(len(out), 3)

    def test_no_false_merge(self):
        blocks = [
            {"type": "text", "text": "A.1个", "bbox": [6, 66, 45, 81], "confidence": 0.9},
            {"type": "text", "text": "B.2个", "bbox": [153, 64, 196, 82], "confidence": 0.9},
        ]
        out = rebuild_fractions(blocks)
        self.assertEqual(len(out), 2)
        self.assertTrue(all(b.get("type") == "text" for b in out))


class TestEnrichIntegration(unittest.TestCase):

    def test_enrich_blocks_fixes_symbols(self):
        result = {"blocks": [{"type": "text", "text": "①ZA+ZB=ZC",
                               "bbox": [0, 0, 1, 1], "confidence": 0.9}]}
        out = enrich_blocks(result)
        joined = "".join(b.get("text") or b.get("latex") or "" for b in out["blocks"])
        self.assertIn("angle", joined)  # ∠ 已转成 LaTeX 的 \angle


if __name__ == "__main__":
    unittest.main()
