import os
import uuid
from pathlib import Path
from fastapi import APIRouter, HTTPException, BackgroundTasks

from app.services.paddleocr import recognize

router = APIRouter(prefix="/ocr", tags=["OCR"])

# === MVP:内存存任务状态(重启丢失)===
tasks: dict[str, dict] = {}

UPLOAD_DIR = Path("uploads")


def _run_ocr(task_id: str, image_path: str) -> None:
    """后台跑 OCR,完成时把结果塞到 tasks[task_id]"""
    try:
        result = recognize(image_path)
        tasks[task_id] = {
            "status": "completed",
            "result": result,
            "stats": result.get("stats", {}),
        }
    except Exception as e:
        tasks[task_id] = {
            "status": "failed",
            "error": str(e),
        }


@router.post("/")
async def start_ocr(payload: dict, background_tasks: BackgroundTasks):
    """
    开始 OCR 任务
    
    payload: {"image_url": "/uploads/xxx.jpg"}
    返回:{"task_id": "abc", "status": "processing"}
    """
    image_url = payload.get("image_url", "")
    if not image_url:
        raise HTTPException(400, detail="image_url 必填")
    
    # 拼本地路径(我们的 uploads/ 是相对路径)
    filename = image_url.lstrip("/").replace("uploads/", "", 1)
    image_path = UPLOAD_DIR / filename
    
    if not image_path.exists():
        raise HTTPException(404, detail=f"图片不存在:{image_url}")
    
    task_id = str(uuid.uuid4())
    tasks[task_id] = {"status": "processing", "result": None}
    
    background_tasks.add_task(_run_ocr, task_id, str(image_path))
    
    return {"task_id": task_id, "status": "processing"}


@router.get("/status/{task_id}")
async def get_status(task_id: str):
    """轮询任务状态"""
    if task_id not in tasks:
        raise HTTPException(404, detail="task_id 不存在")
    return tasks[task_id]