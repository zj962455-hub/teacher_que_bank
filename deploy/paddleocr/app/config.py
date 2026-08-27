"""
从环境变量读配置。
systemd 通过 EnvironmentFile=/etc/paddleocr/api.env 注入。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class Settings:
    api_keys: set[str] = field(default_factory=set)
    max_image_bytes: int = 10 * 1024 * 1024  # 10MB
    ocr_model: str = "PP-StructureV3"
    ocr_lang: str = "ch"

    @classmethod
    def load(cls) -> "Settings":
        s = cls()

        # API keys(逗号分隔)
        keys = os.getenv("OCR_API_KEYS", "").strip()
        if keys:
            s.api_keys = {k.strip() for k in keys.split(",") if k.strip()}

        # 图片大小上限
        if mb := os.getenv("OCR_MAX_IMAGE_MB"):
            try:
                s.max_image_bytes = int(mb) * 1024 * 1024
            except ValueError:
                pass

        # 模型选择
        s.ocr_model = os.getenv("OCR_MODEL", s.ocr_model)
        s.ocr_lang = os.getenv("OCR_LANG", s.ocr_lang)

        return s


settings = Settings.load()