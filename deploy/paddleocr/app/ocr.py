"""
PaddleOCR 引擎封装。
模型加载、识别、结构化输出都在这里。
"""
from __future__ import annotations

import asyncio
import io
import logging
from typing import Literal

from PIL import Image
from paddleocr import PaddleOCR

from schemas import Block

logger = logging.getLogger("paddleocr-api.ocr")


class PaddleOCREngine:
    """PaddleOCR 单例,内部锁保证并发安全。"""

    def __init__(self, model_name: str = "PP-StructureV3", lang: str = "ch"):
        self.model_name = model_name
        self.lang = lang
        self._ocr: PaddleOCR | None = None
        self._lock = asyncio.Lock()  # 单进程 + 单 GPU/CPU,串行识别

    def _ensure_loaded(self):
        if self._ocr is None:
            logger.info(f"Loading PaddleOCR model: {self.model_name} lang={self.lang}")
            self._ocr = PaddleOCR(
                use_angle_cls=True,
                lang=self.lang,
                show_log=False,
                # PP-StructureV3 是新版 pipeline,会自动启用版面分析
                # 见 https://github.com/PaddlePaddle/PaddleOCR/blob/release/2.7/doc/doc_ch/PP-StructureV3_introduction.md
            )

    def warmup(self):
        """预热:跑一张 1x1 假图,让模型加载到内存。"""
        self._ensure_loaded()
        # 1x1 黑色 PNG
        tiny = io.BytesIO(self._tiny_png())
        img = Image.open(tiny)
        try:
            self._ocr.ocr(img, cls=True)
        except Exception as e:
            logger.warning(f"Warmup run failed (non-fatal): {e}")

    async def recognize(self, image_bytes: bytes) -> list[Block]:
        """异步识别。CPU 阻塞跑在默认 executor 里,加锁串行。"""
        async with self._lock:
            return await asyncio.get_event_loop().run_in_executor(
                None, self._recognize_sync, image_bytes
            )

    def _recognize_sync(self, image_bytes: bytes) -> list[Block]:
        self._ensure_loaded()

        # 解码图片
        try:
            img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        except Exception as e:
            raise ValueError(f"Invalid image: {e}")

        # 跑 OCR(structure 模式输出结构化结果)
        # PaddleOCR 2.7.x 用 ocr(img, cls=True),3.x 才用 predict()
        # ocr() 期待 np.ndarray,不是 PIL.Image
        import numpy as np
        img_np = np.array(img)
        result = self._ocr.ocr(img_np, cls=True)

        blocks: list[Block] = []
        if not result:
            return blocks

        # PP-StructureV3 返回结构化解析结果
        # 兼容不同 paddleocr 版本的返回结构
        page_result = result[0] if isinstance(result, list) else result

        # 1. 文本块
        for line in self._iter_text_lines(page_result):
            blocks.append(Block(
                type="text",
                text=line["text"],
                bbox=line["bbox"],
                confidence=line["confidence"],
            ))

        # 2. 公式块(PP-StructureV3 支持)
        for formula in self._iter_formulas(page_result):
            blocks.append(Block(
                type="formula",
                latex=formula["latex"],
                bbox=formula["bbox"],
                confidence=formula["confidence"],
            ))

        # 3. 表格块
        for table in self._iter_tables(page_result):
            blocks.append(Block(
                type="table",
                html=table["html"],
                bbox=table["bbox"],
                confidence=table["confidence"],
            ))

        return blocks

    # ---- 内部迭代器(适配不同 paddleocr 版本返回值) ----

    def _iter_text_lines(self, page):
        """从 page_result 抽出文本行。
        PaddleOCR 2.7 ocr() 返回: [[[bbox_points], (text, conf)], ...]
        其中 page 是顶层 list 里的第一个元素(单页)
        """
        if not page:
            return
        # page 可能是 list(单页)或者 list of lists(多页)
        lines = page if (page and isinstance(page[0], list) and len(page) > 0
                         and isinstance(page[0], (list, tuple)) and len(page[0]) == 2
                         and isinstance(page[0][1], (tuple, list))) else None
        if lines is None:
            return
        for line in lines:
            try:
                bbox_pts = line[0]
                text_conf = line[1]
                text = text_conf[0] if isinstance(text_conf, (list, tuple)) else text_conf
                conf = text_conf[1] if isinstance(text_conf, (list, tuple)) and len(text_conf) > 1 else 0.0
                # bbox 转 [x1, y1, x2, y2]
                xs = [p[0] for p in bbox_pts]
                ys = [p[1] for p in bbox_pts]
                bbox = [min(xs), min(ys), max(xs), max(ys)]
                yield {"text": text, "bbox": bbox, "confidence": conf}
            except (IndexError, TypeError):
                continue

    def _iter_formulas(self, page):
        """抽出公式块。"""
        try:
            for block in page["res"]["blocks"]:
                if block.get("type") in ("formula", "equation"):
                    yield {
                        "latex": block.get("latex", "") or "",
                        "bbox": block.get("bbox", [0, 0, 0, 0]),
                        "confidence": block.get("score", 0.0),
                    }
        except (KeyError, TypeError):
            pass

    def _iter_tables(self, page):
        """抽出表格块(HTML 形式)。"""
        try:
            for block in page["res"]["blocks"]:
                if block.get("type") == "table":
                    yield {
                        "html": block.get("html", "") or "",
                        "bbox": block.get("bbox", [0, 0, 0, 0]),
                        "confidence": block.get("score", 0.0),
                    }
        except (KeyError, TypeError):
            pass

    @staticmethod
    def _tiny_png() -> bytes:
        """1x1 黑色 PNG(预热用)。"""
        import base64
        return base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkAAIAAAoAAv/lxKUAAAAASUVORK5CYII="
        )