"""题目 CRUD 路由 — lesson-08

对应前端
--------
| 方法 | 路径 | 作用 |
|---|---|---|
| POST | /api/questions/ | 新建题目 |
| GET  | /api/questions/ | 列表（可筛选 + 分页）|
| GET  | /api/questions/{id} | 单题详情 |
| PUT  | /api/questions/{id} | 更新题目 |
| DELETE| /api/questions/{id} | 删除题目 |
| POST | /api/questions/from-ocr/{task_id} | 从 OCR 结果一键入库 |

关键设计：from-ocr
-------------------
老师 OCR 完点一下就入库 —— 后端自己从 ocr_store 读 blocks + 跑分类器，
不用前端再把数据传一遍（少一次出错机会）。
"""

import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from app.database import get_session
from app.models import Question
from app.services.classifier import build_content_versions, classify_blocks

router = APIRouter(
    prefix="/questions",
    tags=["题目"],
)


# === 请求体模型 ===
from pydantic import BaseModel, Field


class QuestionCreate(BaseModel):
    """新建题目的请求体"""

    content_plain: str = Field(default="", max_length=10000)
    content_markdown: str = Field(default="", max_length=10000)
    blocks: list[dict] = Field(default_factory=list)
    image_path: str = Field(default="", max_length=500)
    ocr_task_id: str = Field(default="", max_length=100)
    # 分类：前端可以传（用户手动改过），不传就后端自动分类
    subject: Optional[str] = None
    question_type: Optional[str] = None
    grade: Optional[str] = None
    difficulty: Optional[str] = None


class QuestionUpdate(BaseModel):
    """更新题目的请求体（所有字段可选）"""

    content_plain: Optional[str] = None
    content_markdown: Optional[str] = None
    blocks: Optional[list[dict]] = None
    subject: Optional[str] = None
    question_type: Optional[str] = None
    grade: Optional[str] = None
    difficulty: Optional[str] = None
    image_path: Optional[str] = None


# === 列表 ===
# 完整路径: GET /api/questions/
@router.get("/")
def list_questions(
    session: Session = Depends(get_session),
    subject: Optional[str] = Query(default=None, description="按学科筛选"),
    question_type: Optional[str] = Query(default=None, description="按题型筛选"),
    grade: Optional[str] = Query(default=None, description="按学段筛选"),
    difficulty: Optional[str] = Query(default=None, description="按难度筛选"),
    keyword: Optional[str] = Query(default=None, description="内容关键词搜索"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """题目列表（支持筛选 + 分页）"""
    stmt = select(Question)

    if subject:
        stmt = stmt.where(Question.subject == subject)
    if question_type:
        stmt = stmt.where(Question.question_type == question_type)
    if grade:
        stmt = stmt.where(Question.grade == grade)
    if difficulty:
        stmt = stmt.where(Question.difficulty == difficulty)
    if keyword:
        stmt = stmt.where(Question.content_plain.contains(keyword))

    # 按创建时间倒序(新的在前)
    stmt = stmt.order_by(Question.created_at.desc())
    stmt = stmt.offset(offset).limit(limit)

    items = session.exec(stmt).all()

    # 总数(不带 limit/offset,用于前端分页)
    count_stmt = select(Question)
    if subject:
        count_stmt = count_stmt.where(Question.subject == subject)
    if question_type:
        count_stmt = count_stmt.where(Question.question_type == question_type)
    if grade:
        count_stmt = count_stmt.where(Question.grade == grade)
    if difficulty:
        count_stmt = count_stmt.where(Question.difficulty == difficulty)
    if keyword:
        count_stmt = count_stmt.where(Question.content_plain.contains(keyword))
    total = len(session.exec(count_stmt).all())

    return {
        "items": [_to_dict(q) for q in items],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


# === 详情 ===
# 完整路径: GET /api/questions/{question_id}
@router.get("/{question_id}")
def get_question(question_id: int, session: Session = Depends(get_session)):
    """单题详情"""
    question = session.get(Question, question_id)
    if not question:
        raise HTTPException(status_code=404, detail="题目不存在")
    return _to_dict(question)


# === 新建 ===
# 完整路径: POST /api/questions/
@router.post("/")
def create_question(
    payload: QuestionCreate,
    session: Session = Depends(get_session),
):
    """新建题目"""
    versions = build_content_versions(payload.blocks)

    # 分类：前端传了就用前端的（用户可能手动改过），没传就后端自动算
    auto = classify_blocks(payload.blocks)
    question = Question(
        subject=payload.subject or auto["subject"],
        question_type=payload.question_type or auto["type"],
        grade=payload.grade or auto["grade"],
        difficulty=payload.difficulty or auto["difficulty"],
        content_plain=payload.content_plain or versions["plain"],
        content_markdown=payload.content_markdown or versions["markdown"],
        blocks_json=versions["blocks_json"],
        image_path=payload.image_path,
        ocr_task_id=payload.ocr_task_id,
    )

    session.add(question)
    session.commit()
    session.refresh(question)

    return _to_dict(question)


# === 从 OCR 一键入库 ===
# 完整路径: POST /api/questions/from-ocr/{task_id}
@router.post("/from-ocr/{task_id}")
def create_from_ocr(task_id: str, session: Session = Depends(get_session)):
    """从 OCR 结果一键入库

    后端自己读 ocr_store 的记录 + 跑分类器,
    前端只要传 task_id。
    """
    from app.services.ocr_store import TASKS

    record = TASKS.get(task_id)
    if not record:
        raise HTTPException(status_code=404, detail="OCR 任务不存在或已过期")

    result = record.get("result") or {}
    blocks = result.get("blocks") or []
    if not blocks:
        raise HTTPException(status_code=400, detail="该 OCR 任务没有识别结果")

    versions = build_content_versions(blocks)
    auto = classify_blocks(blocks)

    question = Question(
        subject=auto["subject"],
        question_type=auto["type"],
        grade=auto["grade"],
        difficulty=auto["difficulty"],
        content_plain=versions["plain"],
        content_markdown=versions["markdown"],
        blocks_json=versions["blocks_json"],
        image_path=record.get("image_url", ""),
        ocr_task_id=task_id,
    )

    session.add(question)
    session.commit()
    session.refresh(question)

    return {
        "question": _to_dict(question),
        "classification": auto,
    }


# === 更新 ===
# 完整路径: PUT /api/questions/{question_id}
@router.put("/{question_id}")
def update_question(
    question_id: int,
    payload: QuestionUpdate,
    session: Session = Depends(get_session),
):
    """更新题目"""
    question = session.get(Question, question_id)
    if not question:
        raise HTTPException(status_code=404, detail="题目不存在")

    data = payload.model_dump(exclude_unset=True)

    # blocks 变了 → 三个内容版本都要跟着重算
    if "blocks" in data and data["blocks"] is not None:
        versions = build_content_versions(data["blocks"])
        question.blocks_json = versions["blocks_json"]
        if "content_plain" not in data:
            question.content_plain = versions["plain"]
        if "content_markdown" not in data:
            question.content_markdown = versions["markdown"]

    for field in (
        "content_plain",
        "content_markdown",
        "subject",
        "question_type",
        "grade",
        "difficulty",
        "image_path",
    ):
        if field in data and data[field] is not None:
            setattr(question, field, data[field])

    question.updated_at = datetime_now()
    session.add(question)
    session.commit()
    session.refresh(question)

    return _to_dict(question)


# === 删除 ===
# 完整路径: DELETE /api/questions/{question_id}
@router.delete("/{question_id}")
def delete_question(question_id: int, session: Session = Depends(get_session)):
    """删除题目"""
    question = session.get(Question, question_id)
    if not question:
        raise HTTPException(status_code=404, detail="题目不存在")

    session.delete(question)
    session.commit()

    return {"deleted": True, "id": question_id}


# === 辅助函数 ===
def datetime_now():
    """当前时间（带时区）

    字段是 TIMESTAMP WITH TIME ZONE,必须给带时区的 datetime,
    否则 SQLAlchemy 报 "Datetime values must have timezone information"
    """
    from datetime import datetime, timezone
    return datetime.now(timezone.utc)


def _to_dict(question: Question) -> dict:
    """ORM 对象 → dict（给前端）"""
    return {
        "id": question.id,
        "subject": question.subject,
        "question_type": question.question_type,
        "grade": question.grade,
        "difficulty": question.difficulty,
        "content_plain": question.content_plain,
        "content_markdown": question.content_markdown,
        "blocks": question.blocks,
        "image_path": question.image_path,
        "ocr_task_id": question.ocr_task_id,
        "created_at": question.created_at.isoformat() if question.created_at else None,
        "updated_at": question.updated_at.isoformat() if question.updated_at else None,
    }
