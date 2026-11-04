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
from app.models import PaperQuestion, Question, User
from app.services.auth import get_current_user
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


class BatchDeleteRequest(BaseModel):
    """批量删除"""
    ids: list[int] = Field(default_factory=list, max_length=200)


class BatchUpdateRequest(BaseModel):
    """批量改分类/难度

    只传要改的字段,没传的保持原样。
    """
    ids: list[int] = Field(default_factory=list, max_length=200)
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



def _normalize_image_path(path: str) -> str:
    """图片路径规范化

    历史数据存的是 ``/uploads/xxx``（静态挂载时代），
    现在图片走鉴权路由 ``/api/uploads/xxx`` —— 统一成后者。

    只做路径改写，不改文件名（文件名是随机后缀，不可猜）。
    """
    if not path:
        return ""
    if path.startswith("/api/uploads/"):
        return path
    if path.startswith("/uploads/"):
        return "/api/uploads/" + path[len("/uploads/"):]
    return path


# === 分类树（左侧章节树的数据源）===
@router.get("/categories")
def category_tree(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """按学科/学段/难度三维聚合出章节树

    原型的「章节树」本质是题目的多维归类 ——
    这里用已有字段拼出来,不额外建表（数据量小时够用,
    以后真要拖拽维护再单独建 categories 表）。

    返回结构：
    {
      "tree": [
        {"key":"数学","label":"数学","count":12,"children":[
            {"key":"数学/高中","label":"高中","count":8,"children":[
                {"key":"数学/高中/简单","label":"简单","count":3,"count":3}
            ]}
        ]}
      ],
      "total": 30
    }
    """
    from sqlalchemy import func

    uid = current_user.id or 0

    # 一次把当前用户的题目全捞出来,在 Python 里聚合 ——
    # 数据量小(几千题)时比三次 group by 简单得多
    rows = session.exec(
        select(Question.subject, Question.grade, Question.difficulty)
        .where(Question.user_id == uid)
    ).all()

    tree: dict[str, dict] = {}
    for subject, grade, difficulty in rows:
        node = tree.setdefault(
            subject,
            {"key": subject, "label": subject, "count": 0, "children": {}},
        )
        node["count"] += 1

        gnode = node["children"].setdefault(
            grade,
            {"key": f"{subject}/{grade}", "label": grade, "count": 0, "children": {}},
        )
        gnode["count"] += 1

        dnode = gnode["children"].setdefault(
            difficulty,
            {"key": f"{subject}/{grade}/{difficulty}", "label": difficulty, "count": 0},
        )
        dnode["count"] += 1

    def to_list(children: dict) -> list:
        out = []
        for node in children.values():
            item = {
                "key": node["key"],
                "label": node["label"],
                "count": node["count"],
            }
            if node.get("children"):
                item["children"] = to_list(node["children"])
            out.append(item)
        return out

    return {
        "tree": to_list(tree),
        "total": sum(n["count"] for n in tree.values()),
    }


# === 批量操作 ===
@router.post("/batch/delete")
def batch_delete(
    payload: BatchDeleteRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """批量删除题目

    只删当前用户的 —— 别人的 id 静默跳过(不当成错误),
    返回实际删了多少条。
    """
    if not payload.ids:
        return {"deleted": 0, "skipped": 0}

    deleted = 0
    skipped = 0
    for qid in payload.ids:
        question = session.get(Question, qid)
        if question is None or question.user_id != (current_user.id or 0):
            skipped += 1
            continue
        # 关联的试卷记录先清掉(外键约束)
        for pq in session.exec(
            select(PaperQuestion).where(PaperQuestion.question_id == qid)
        ).all():
            session.delete(pq)
        session.delete(question)
        deleted += 1

    session.commit()
    return {"deleted": deleted, "skipped": skipped}


@router.post("/batch/update")
def batch_update(
    payload: BatchUpdateRequest,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """批量改分类/难度"""
    if not payload.ids:
        return {"updated": 0, "skipped": 0}

    from datetime import datetime, timezone

    updated = 0
    skipped = 0
    for qid in payload.ids:
        question = session.get(Question, qid)
        if question is None or question.user_id != (current_user.id or 0):
            skipped += 1
            continue
        if payload.subject is not None:
            question.subject = payload.subject
        if payload.question_type is not None:
            question.question_type = payload.question_type
        if payload.grade is not None:
            question.grade = payload.grade
        if payload.difficulty is not None:
            question.difficulty = payload.difficulty
        question.updated_at = datetime.now(timezone.utc)
        session.add(question)
        updated += 1

    session.commit()
    return {"updated": updated, "skipped": skipped}


# === 最近编辑（仪表盘用）===
@router.get("/recent")
def recent_questions(
    limit: int = Query(default=6, ge=1, le=20),
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """最近编辑的题目（仪表盘「最近编辑」卡片）"""
    items = session.exec(
        select(Question)
        .where(Question.user_id == (current_user.id or 0))
        .order_by(Question.updated_at.desc())
        .limit(limit)
    ).all()
    return {"items": [_to_dict(q) for q in items]}


# === 列表 ===
# 完整路径: GET /api/questions/
@router.get("/")
def list_questions(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
    subject: Optional[str] = Query(default=None, description="按学科筛选"),
    question_type: Optional[str] = Query(default=None, description="按题型筛选"),
    grade: Optional[str] = Query(default=None, description="按学段筛选"),
    difficulty: Optional[str] = Query(default=None, description="按难度筛选"),
    keyword: Optional[str] = Query(default=None, description="内容关键词搜索"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """题目列表（支持筛选 + 分页）

    只返回当前登录用户自己的题目 —— 数据隔离的第一道门。
    """
    stmt = select(Question).where(Question.user_id == (current_user.id or 0))

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
    count_stmt = select(Question).where(Question.user_id == (current_user.id or 0))
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
def get_question(
    question_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """单题详情"""
    question = _get_own_question(question_id, session, current_user)
    return _to_dict(question)


# === 新建 ===
# 完整路径: POST /api/questions/
@router.post("/")
def create_question(
    payload: QuestionCreate,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """新建题目"""
    versions = build_content_versions(payload.blocks)

    # 分类：前端传了就用前端的（用户可能手动改过），没传就后端自动算
    auto = classify_blocks(payload.blocks)
    question = Question(
        user_id=current_user.id or 0,
        subject=payload.subject or auto["subject"],
        question_type=payload.question_type or auto["type"],
        grade=payload.grade or auto["grade"],
        difficulty=payload.difficulty or auto["difficulty"],
        content_plain=payload.content_plain or versions["plain"],
        content_markdown=payload.content_markdown or versions["markdown"],
        blocks_json=versions["blocks_json"],
        image_path=_normalize_image_path(payload.image_path),
        ocr_task_id=payload.ocr_task_id,
    )

    session.add(question)
    session.commit()
    session.refresh(question)

    return _to_dict(question)


# === 从 OCR 一键入库 ===
# 完整路径: POST /api/questions/from-ocr/{task_id}
@router.post("/from-ocr/{task_id}")
def create_from_ocr(
    task_id: str,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
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
        user_id=current_user.id or 0,
        subject=auto["subject"],
        question_type=auto["type"],
        grade=auto["grade"],
        difficulty=auto["difficulty"],
        content_plain=versions["plain"],
        content_markdown=versions["markdown"],
        blocks_json=versions["blocks_json"],
        image_path=_normalize_image_path(record.get("image_url", "")),
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
    current_user: User = Depends(get_current_user),
):
    """更新题目"""
    question = _get_own_question(question_id, session, current_user)

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
def delete_question(
    question_id: int,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """删除题目"""
    question = _get_own_question(question_id, session, current_user)

    session.delete(question)
    session.commit()

    return {"deleted": True, "id": question_id}


# === 辅助函数 ===
def _get_own_question(question_id: int, session: Session, user: User) -> Question:
    """取题目并校验归属

    别人的题目一律当「不存在」而不是「403」——
    让外人无法通过状态码差异探测出某个 id 存不存在。
    """
    question = session.get(Question, question_id)
    if not question or question.user_id != (user.id or 0):
        raise HTTPException(status_code=404, detail="题目不存在")
    return question


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
