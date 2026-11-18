"""上传图片路由 — lesson-11

改动（相对 lesson-06 的原始版本）
--------------------------------
1. **上传需要登录** —— 之前任何人能往服务器写文件
2. **每次上传记一条归属记录**（uploads 表）—— 文件名 → user_id 的映射
3. **读取需要登录 + 校验归属** —— 之前静态目录裸奔，任何人拿 URL 就能下载
4. 文件名加随机后缀 —— 时间戳可猜，同名文件也会互相覆盖

为什么不能直接挂静态目录
------------------------
``app.mount("/uploads", StaticFiles(...))`` **不认识 token**，
只要知道 URL 就能拿到文件 —— 数据隔离从「一道门」变成「一道门 + 一扇窗」。
题目图片是学生试卷扫描件，里面有姓名班级，不能裸奔。
"""

import os
import secrets
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from sqlmodel import Session, select

from app.database import get_session
from app.models import Upload, User
from app.services.auth import get_current_user

router = APIRouter(
    prefix="/uploads",
    tags=["图片上传"],
)

UPLOAD_DIR = Path("uploads")

# 大小上限 5MB
MAX_SIZE = 5 * 1024 * 1024

# 允许的图片类型
ALLOWED_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


def _ensure_dir() -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _safe_extension(content_type: str, original: str) -> str:
    """按 MIME 定扩展名，不信任原文件名的扩展名"""
    ext = ALLOWED_TYPES.get(content_type.lower())
    if ext:
        return ext
    # 不在白名单里就按原名后缀兜底（但类型检查已经拦住了非 image/）
    suffix = Path(original).suffix.lower()
    return suffix if suffix in {".png", ".jpg", ".jpeg", ".webp", ".gif"} else ".png"



# === 上传 ===

@router.post("/")
async def upload_image(
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """接收图片上传，存到本地 uploads/ 目录

    - 前端发: multipart/form-data，字段名 'file'
    - 返回: {filename, url, size, content_type}
    """
    _ensure_dir()

    # 类型检查（只允许图片）
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"只支持图片（{'、'.join(sorted(ALLOWED_TYPES))}），收到 {file.content_type}",
        )

    content = await file.read()

    # 大小校验（5 MB 上限）
    if len(content) > MAX_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"文件超过 5 MB 限制（当前 {len(content) // (1024 * 1024)} MB）",
        )

    # 文件名：时间戳 + 随机后缀 + 安全扩展名
    # ⚠️ 随机后缀是必须的 —— 纯时间戳可猜（同秒上传会互相覆盖）
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    random_suffix = secrets.token_hex(4)
    ext = _safe_extension(file.content_type, file.filename or "")
    filename = f"{timestamp}_{random_suffix}{ext}"
    filepath = UPLOAD_DIR / filename

    with open(filepath, "wb") as f:
        f.write(content)

    # 记归属 —— 读图片时靠它判断能不能给
    record = Upload(
        user_id=current_user.id or 0,
        filename=filename,
        url=f"/api/uploads/{filename}",
        original_name=(file.filename or "")[:255],
        size=len(content),
        content_type=file.content_type,
    )
    session.add(record)
    session.commit()

    return {
        "filename": filename,
        "url": record.url,
        "size": record.size,
        "content_type": record.content_type,
    }


# === 列表 ===

@router.get("/list")
def list_uploads(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """列出当前用户上传的图片（只列自己的）"""
    records = session.exec(
        select(Upload)
        .where(Upload.user_id == (current_user.id or 0))
        .order_by(Upload.created_at.desc())
    ).all()

    return [
        {
            "filename": r.filename,
            "url": r.url,
            "size": r.size,
            "content_type": r.content_type,
            "original_name": r.original_name,
        }
        for r in records
    ]


# === 读取（鉴权） ===

@router.get("/{filename}")
def get_upload(
    filename: str,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """读取一张上传的图片

    ⚠️ 必须鉴权 —— 这里是数据隔离的最后一环。
    别人的图片一律当「不存在」（404），不返 403 ——
    避免用状态码差异探测出某个文件名存不存在。
    """
    # 防目录穿越：文件名里不能有路径分隔符
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=404, detail="文件不存在")

    record = session.exec(
        select(Upload).where(Upload.filename == filename)
    ).first()

    if record is None or record.user_id != (current_user.id or 0):
        raise HTTPException(status_code=404, detail="文件不存在")

    filepath = UPLOAD_DIR / filename
    if not filepath.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")

    return FileResponse(
        filepath,
        media_type=record.content_type or "application/octet-stream",
        headers={"Cache-Control": "private, max-age=604800"},
    )
