"""
请求/响应 Pydantic 模型。
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Block(BaseModel):
    """一个 OCR 识别的块(文本/公式/表格)。"""

    type: Literal["text", "formula", "table"]
    # type=text 时填
    text: str | None = None
    # type=formula 时填
    latex: str | None = None
    # type=table 时填
    html: str | None = None
    # 通用
    bbox: list[float] = Field(default_factory=list, description="[x1, y1, x2, y2]")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class OCRResponse(BaseModel):
    ok: bool = True
    blocks: list[Block]
    stats: dict = Field(default_factory=dict, description="{elapsed_ms, model}")


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded", "down"]
    model: str
    version: str


class ErrorResponse(BaseModel):
    detail: str