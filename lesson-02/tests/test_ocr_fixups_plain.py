import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.math_parser import split_text_block_into_blocks  # noqa: E402


class TestSymbolFixInPlainTextBlock(unittest.TestCase):
    """整块文本（没有可拆公式）也必须带上修好的符号"""

    def test_plain_block_keeps_fixed_symbols(self):
        out = split_text_block_into_blocks({
            "type": "text",
            "text": "BQIAD于点Q.",
            "bbox": [0, 0, 10, 10],
            "confidence": 0.9,
        })
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["text"], "BQ⊥AD于点Q.")


if __name__ == "__main__":
    unittest.main()