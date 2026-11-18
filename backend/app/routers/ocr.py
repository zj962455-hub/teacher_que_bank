"""OCR 路由 — lesson-06 原始版 + lesson-35 鉴权收口

这一轮改了什么
--------------
1. **三个接口全部要登录** —— 之前 ``POST /api/ocr/``、``/api/ocr/status/{id}``、
   ``/api/ocr/history`` 一个都没鉴权,公网可调:
   - 任何人能触发 OCR → 打满 OCR 服务(2 并发)就是拒绝服务
   - ``/api/ocr/history`` 返回**所有用户**的识别记录 → 别人的试卷内容泄露

2. **图片归属校验** —— 之前直接拿 URL 拼磁盘路径
   (``image_url.lstrip("/").replace("uploads/", "", 1)``),于是:
   - 前端发 ``/api/uploads/x.png``(lesson-11 鉴权路由的新格式)→ 被砍成
     ``api/x.png`` → 拼出 ``uploads/api/x.png`` → **404,老师根本识别不了**
   - ``/uploads/../../etc/x.png`` → 被砍成 ``../etc/x.png`` → **路径穿越**

   现在:URL 只用来**摘出一个裸文件名**,
   归属交给 ``uploads`` 表查(表里有 filename 唯一索引 + user_id),
   查不到或不是本人的 → 404。``..`` 走不到文件系统。

3. **OCR 任务带 user_id** —— 记录里存 ``user_id``(连同 task 一起落盘,
   随重启恢复),别人的任务查不到、从别人的任务入库也不行。

越权口径
--------
越权一律 **404,不返 403** —— 跟 ``/api/uploads/{filename}`` 既有口径一致:
不让外人用状态码差异探测出某个 id / 文件名存不存在。
"""

import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlmodel import Session, select

from app.database import get_session
from app.models import Upload, User
from app.routers.upload import UPLOAD_DIR
from app.services.auth import get_current_user
from app.services.errors import (
    CODE_NOT_FOUND,
    CODE_VALIDATION,
    ApiHTTPException,
)
from app.services.ocr_store import (
    TASKS as tasks,
    is_task_visible,
    list_history_for_user,
    save_task,
)
from app.services.paddleocr import OcrError, recognize, validate_image

router = APIRouter(prefix="/ocr", tags=["OCR"])

# 图片 URL 前缀 —— 两种都认:
#   /api/uploads/xxx  ← lesson-11 鉴权路由(前端现在发这个)
#   /uploads/xxx      ← lesson-06 静态挂载时代的旧格式(历史数据里还有)
_UPLOAD_URL_PREFIXES = ("/api/uploads/", "/uploads/")


def _now() -> str:
    """ISO8601 时间戳,给 created_at 用"""
    return datetime.now(timezone.utc).isoformat()


def extract_filename(image_url: str) -> str | None:
    """从图片 URL 里取出**裸文件名**;取不出来返回 None

    为什么不能「拿 URL 拼路径」
    ----------------------
    以前这里是 ``image_url.lstrip("/").replace("uploads/", "", 1)`` ——
    两头都错:
    - 前端发 ``/api/uploads/x.png`` → 砍成 ``api/x.png`` → 拼出
      ``uploads/api/x.png`` → **不存在 → 404**(灰度试用直接卡死在这)
    - ``/uploads/../../etc/x.png`` → 砍成 ``../etc/x.png`` →
      **路径穿越**,能读服务器上任意图片

    现在只摘文件名,剩下交给 ``uploads`` 表判归属 ——
    ``..`` 根本走不到文件系统。
    """
    if not isinstance(image_url, str):
        return None

    # 去掉查询串和锚点(前端不会带,但别给绕过留口子)
    url = image_url.split("?", 1)[0].split("#", 1)[0].strip()

    for prefix in _UPLOAD_URL_PREFIXES:
        if url.startswith(prefix):
            filename = url[len(prefix):]
            break
    else:
        return None

    # 必须是裸文件名:不含路径分隔符、不含 ..
    if not filename:
        return None
    if "/" in filename or "\\" in filename or ".." in filename:
        return None
    if filename != Path(filename).name:
        return None

    return filename


def _own_upload(filename: str, session: Session, user: User) -> Upload:
    """查上传记录并校验归属

    查不到 或 不是本人的 → 一律 404(不返 403)。

    ⚠️ 这一条同时把路径穿越堵死:文件名必须真实存在于 uploads 表
    且属于本人,``..`` 之类的东西压根到不了文件系统。
    """
    record = session.exec(select(Upload).where(Upload.filename == filename)).first()

    if record is None or record.user_id != (user.id or 0):
        raise ApiHTTPException(
            status_code=404,
            detail="图片不存在",
            code=CODE_NOT_FOUND,
        )

    return record


def _run_ocr(task_id: str, image_url: str, image_path: str, user_id: int) -> None:
    """后台跑 OCR,完成时把结果写进 tasks[task_id] 并落盘

    ⚠️ user_id 必须一路带着 —— 落盘后这条记录才认得出主人,
    重启恢复(TASKS 从磁盘重建)后归属才不会丢。
    """
    try:
        result = recognize(image_path)
        save_task(task_id, {
            "task_id": task_id,
            "status": "completed",
            "result": result,
            "stats": result.get("stats", {}),
            "image_url": image_url,
            "user_id": user_id,
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
            "user_id": user_id,
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
            "user_id": user_id,
            "created_at": _now(),
        })


@router.post("/")
async def start_ocr(
    payload: dict,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    开始 OCR 任务

    payload: {"image_url": "/api/uploads/xxx.jpg"}
    返回:{"task_id": "abc", "status": "processing"}

    ⚠️ 要登录 —— 之前任何人可调,能把 OCR 服务(2 并发)打满。
    """
    image_url = payload.get("image_url", "")
    if not image_url:
        raise ApiHTTPException(
            status_code=400,
            detail="image_url 必填",
            code=CODE_VALIDATION,
        )

    # === 图片归属:URL 只用来摘文件名,归属查 uploads 表 ===
    filename = extract_filename(image_url)
    if filename is None:
        raise ApiHTTPException(
            status_code=404,
            detail="图片不存在",
            code=CODE_NOT_FOUND,
        )

    _own_upload(filename, session, current_user)

    # 拼本地路径(我们的 uploads/ 是相对路径)
    image_path = UPLOAD_DIR / filename

    if not image_path.is_file():
        raise ApiHTTPException(
            status_code=404,
            detail="图片不存在",
            code=CODE_NOT_FOUND,
        )

    # 任务 2:同步校验(图片过大/类型不对立刻返 413/415,不用进后台再失败)
    try:
        validate_image(str(image_path))
    except OcrError as e:
        raise ApiHTTPException(
            status_code=e.status_code,
            detail=str(e),
            code=CODE_VALIDATION,
        )

    task_id = str(uuid.uuid4())
    save_task(task_id, {
        "task_id": task_id,
        "status": "processing",
        "result": None,
        "image_url": image_url,
        "user_id": current_user.id or 0,
        "created_at": _now(),
    })

    background_tasks.add_task(
        _run_ocr, task_id, image_url, str(image_path), current_user.id or 0
    )

    return {"task_id": task_id, "status": "processing"}


@router.get("/status/{task_id}")
async def get_status(
    task_id: str,
    current_user: User = Depends(get_current_user),
):
    """轮询任务状态

    ⚠️ 别人的任务 → 404(不返 403):不泄露「这个 task_id 存不存在」。
    没有 user_id 的历史遗留记录 → 只有管理员看得到。
    """
    record = tasks.get(task_id)

    if not is_task_visible(
        record, current_user.id or 0, is_admin=bool(current_user.is_admin)
    ):
        raise ApiHTTPException(
            status_code=404,
            detail="任务不存在",
            code=CODE_NOT_FOUND,
        )

    return record


@router.get("/history")
async def get_history(
    limit: int = Query(default=10, ge=1, le=50),
    current_user: User = Depends(get_current_user),
):
    """
    列出最近 N 条成功识别记录(按时间倒序)
    数据来自 uploads/ocr/*.json,后端重启后依然可用

    ⚠️ 只返回**当前用户自己**的记录 —— 之前返回所有人的,
    等于把别人的试卷识别结果公开给任何登录用户。
    管理员可以看全部(含没有 user_id 的历史遗留记录,做追溯用)。
    """
    uid = current_user.id or 0
    is_admin = bool(current_user.is_admin)

    items = list_history_for_user(uid, limit=limit, is_admin=is_admin)
    total = len(list_history_for_user(uid, limit=50, is_admin=is_admin))

    return {"items": items, "total": total}
