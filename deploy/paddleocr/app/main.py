"""
PaddleOCR API 服务 · FastAPI 主入口
部署位置:阿里云 ECS /opt/paddleocr-deploy/app/main.py
监听:0.0.0.0:8080(由 systemd 启动,nginx 反代)
"""
from __future__ import annotations

import logging
import time
from typing import Annotated

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from ocr import PaddleOCREngine
from schemas import HealthResponse, OCRResponse, ErrorResponse

# 日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("paddleocr-api")

app = FastAPI(
    title="PaddleOCR API",
    version="0.1.0",
    description="阿里云 ECS 部署的 PaddleOCR 服务,统一给 teacher-question-bank 调用",
)

# CORS(只允许本地 + 域名)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://lanhu-lab.top",
        "http://localhost:5173",  # Vue 3 本地开发
    ],
    allow_credentials=True,
    allow_methods=["POST", "GET"],
    allow_headers=["X-API-Key", "Content-Type"],
)

# OCR 引擎单例(模型大,启动慢)
engine = PaddleOCREngine()


# ========== 依赖 ==========

async def verify_api_key(x_api_key: Annotated[str | None, Header()] = None):
    """验证 X-API-Key header。空 key 表示禁用鉴权(仅 dev 用)。"""
    if not settings.api_keys:
        # 没配 key → 放行(开发模式)
        return "anonymous"
    if not x_api_key or x_api_key not in settings.api_keys:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")
    return x_api_key


# ========== 路由 ==========

@app.get("/api/v1/health", response_model=HealthResponse)
async def health():
    """健康检查,不走鉴权(便于监控)。"""
    return HealthResponse(
        status="ok",
        model=engine.model_name,
        version=app.version,
    )


@app.post(
    "/api/v1/ocr/image",
    response_model=OCRResponse,
    responses={400: {"model": ErrorResponse}, 413: {"model": ErrorResponse}},
)
async def ocr_image(
    image: Annotated[UploadFile, File(description="题目图片")],
    _: Annotated[str, Depends(verify_api_key)],
):
    """单图 OCR。返回结构化 blocks(text / formula / table)。"""
    # 1. 大小限制
    contents = await image.read()
    if len(contents) > settings.max_image_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Image too large: {len(contents)} bytes (max {settings.max_image_bytes})",
        )

    # 2. 格式检查
    if image.content_type not in {"image/jpeg", "image/png", "image/webp", "image/bmp"}:
        raise HTTPException(status_code=400, detail=f"Unsupported type: {image.content_type}")

    # 3. 跑 OCR
    t0 = time.perf_counter()
    try:
        blocks = await engine.recognize(contents)
    except Exception as e:
        logger.exception("OCR failed")
        raise HTTPException(status_code=500, detail=f"OCR engine error: {e}")
    elapsed_ms = int((time.perf_counter() - t0) * 1000)

    logger.info(f"OCR ok | size={len(contents)}b blocks={len(blocks)} elapsed={elapsed_ms}ms")

    return OCRResponse(
        ok=True,
        blocks=blocks,
        stats={"elapsed_ms": elapsed_ms, "model": engine.model_name},
    )


# ========== 启动事件 ==========

@app.on_event("startup")
async def startup():
    """启动时预热模型(避免第一次请求超时)。"""
    logger.info("Warming up PaddleOCR model...")
    try:
        engine.warmup()
        logger.info(f"Model ready: {engine.model_name}")
    except Exception:
        logger.exception("Model warmup failed; service will start but first request may fail")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8080,
        workers=1,  # 模型占内存,单进程
        log_level="info",
    )