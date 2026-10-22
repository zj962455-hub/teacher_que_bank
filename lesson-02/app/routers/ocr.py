import uuid
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, HTTPException, BackgroundTasks, Query

from app.services.paddleocr import recognize, OcrError, validate_image
from app.services.ocr_store import TASKS as tasks, save_task, list_history

router = APIRouter(prefix="/ocr", tags=["OCR"])

UPLOAD_DIR = Path("uploads")


def _now() -> str:
    """ISO8601 时间戳,给 created_at 用"""
    return datetime.now(timezone.utc).isoformat()


def _run_ocr(task_id: str, image_url: str, image_path: str) -> None:
    """后台跑 OCR,完成时把结果写进 tasks[task_id] 并落盘"""
    try:
        result = recognize(image_path)
        save_task(task_id, {
            "task_id": task_id,
            "status": "completed",
            "result": result,
            "stats": result.get("stats", {}),
            "image_url": image_url,
            "created_at": _now(),
        })
    except OcrError as e:
        # 业务错误(校验/超时/连接/鉴权/HTTP 错误码)→ 结构化返回
        save_task(task_id, {
            "task_id": task_id,
            "status": "failed",
            "error": e.message,
            "error_code": e.status_code,
            "hint": e.hint,
            "image_url": image_url,
            "created_at": _now(),
        })
    except Exception as e:
        # 兜底:其他未知异常
        save_task(task_id, {
            "task_id": task_id,
            "status": "failed",
            "error": f"未知错误:{type(e).__name__}",
            "error_code": 500,
            "hint": str(e),
            "image_url": image_url,
            "created_at": _now(),
        })


@router.post("/")
async def start_ocr(payload: dict, background_tasks: BackgroundTasks):
    """
    开始 OCR 任务
    
    payload: {"image_url": "/uploads/xxx.jpg"}
    返回:{"task_id": "abc", "status": "processing"}
    """
    image_url = payload.get("image_url", "")
    if not image_url:
        raise HTTPException(status_code=400, detail="image_url 必填")

    # 拼本地路径(我们的 uploads/ 是相对路径)
    filename = image_url.lstrip("/").replace("uploads/", "", 1)
    image_path = UPLOAD_DIR / filename

    if not image_path.exists():
        raise HTTPException(status_code=404, detail=f"图片不存在:{image_url}")

    # 任务 2:同步校验(图片过大/类型不对立刻返 413/415,不用进后台再失败)
    try:
        validate_image(str(image_path))
    except OcrError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))

    task_id = str(uuid.uuid4())
    save_task(task_id, {
        "task_id": task_id,
        "status": "processing",
        "result": None,
        "image_url": image_url,
        "created_at": _now(),
    })

    background_tasks.add_task(_run_ocr, task_id, image_url, str(image_path))

    return {"task_id": task_id, "status": "processing"}


@router.get("/status/{task_id}")
async def get_status(task_id: str):
    """轮询任务状态"""
    if task_id not in tasks:
        raise HTTPException(404, detail="task_id 不存在")
    return tasks[task_id]


@router.get("/history")
async def get_history(limit: int = Query(default=10, ge=1, le=50)):
    """
    列出最近 N 条成功识别记录(按时间倒序)
    数据来自 uploads/ocr/*.json,后端重启后依然可用
    """
    return {"items": list_history(limit=limit), "total": len(list_history(limit=50))}