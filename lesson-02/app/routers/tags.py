"""标签路由 — lesson-11（标签系统）

功能
----
- GET    /api/tags/          标签列表（带题目数统计）
- POST   /api/tags/          新建标签
- PUT    /api/tags/{id}      重命名 / 改颜色
- DELETE /api/tags/{id}      删标签（题目保留，只解除关联）
- GET    /api/questions/{id}/tags   某题的标签
- PUT    /api/questions/{id}/tags   设置某题的标签（整体替换）

权限口径
--------
所有操作只作用于**当前登录用户自己的**标签 —— 与题库/试卷同一套隔离。
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.database import get_session
from app.models import Question, QuestionTag, Tag, User
from app.services.auth import get_current_user

router = APIRouter(
    prefix="/tags",
    tags=["标签"],
)


# === 请求体 ===

class TagCreate(BaseModel):
    name: str = Field(max_length=30)
    color: str = Field(default="#18a058", max_length=10)


class TagUpdate(BaseModel):
    # ⚠️ Optional 必须显式 default=None（Pydantic v2 里 Optional 不自动可省）
    name: Optional[str] = Field(default=None, max_length=30)
    color: Optional[str] = Field(default=None, max_length=10)


class QuestionTagsSet(BaseModel):
    """设置某题的标签（整体替换）

    tag_ids 为空列表 = 清空该题所有标签。
    """
    tag_ids: list[int] = Field(default_factory=list, max_length=50)


# === 辅助 ===

def _own_tag(tag_id: int, session: Session, user: User) -> Tag:
    tag = session.get(Tag, tag_id)
    if tag is None or tag.user_id != (user.id or 0):
        raise HTTPException(status_code=404, detail="标签不存在")
    return tag


def _own_question(question_id: int, session: Session, user: User) -> Question:
    question = session.get(Question, question_id)
    if question is None or question.user_id != (user.id or 0):
        raise HTTPException(status_code=404, detail="题目不存在")
    return question


def _tag_ids_of(question_id: int, session: Session) -> list[int]:
    rows = session.exec(
        select(QuestionTag.tag_id).where(QuestionTag.question_id == question_id)
    ).all()
    return list(rows)


# === 标签 CRUD ===


@router.get("/")
def list_tags(
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """标签列表（带每个标签下的题目数）"""
    uid = user.id or 0

    tags = session.exec(
        select(Tag).where(Tag.user_id == uid).order_by(Tag.id)
    ).all()
    if not tags:
        return {"items": []}

    tag_ids = [t.id for t in tags if t.id is not None]

    # 统计每个标签下的题目数
    counts: dict[int, int] = {}
    for row in session.exec(
        select(QuestionTag.tag_id, QuestionTag.id).where(QuestionTag.tag_id.in_(tag_ids))
    ).all():
        counts[row[0]] = counts.get(row[0], 0) + 1

    return {
        "items": [
            {
                "id": t.id,
                "name": t.name,
                "color": t.color,
                "count": counts.get(t.id, 0),
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in tags
        ]
    }


@router.post("/")
def create_tag(
    payload: TagCreate,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """新建标签（重名自动复用已有标签）"""
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="标签名不能为空")

    uid = user.id or 0

    # 同名标签直接复用 —— 老师不该被迫创建两个「易错题」
    existing = session.exec(
        select(Tag).where(Tag.user_id == uid, Tag.name == name)
    ).first()
    if existing is not None:
        return {
            "id": existing.id,
            "name": existing.name,
            "color": existing.color,
            "count": 0,
            "reused": True,
        }

    tag = Tag(user_id=uid, name=name, color=payload.color or "#18a058")
    session.add(tag)
    session.commit()
    session.refresh(tag)

    return {
        "id": tag.id,
        "name": tag.name,
        "color": tag.color,
        "count": 0,
        "reused": False,
    }


@router.put("/{tag_id}")
def update_tag(
    tag_id: int,
    payload: TagUpdate,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """重命名 / 改颜色"""
    tag = _own_tag(tag_id, session, user)

    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="标签名不能为空")
        # 不能改成别人的已有标签名
        dup = session.exec(
            select(Tag).where(
                Tag.user_id == (user.id or 0),
                Tag.name == name,
                Tag.id != tag_id,
            )
        ).first()
        if dup is not None:
            raise HTTPException(status_code=400, detail=f"标签「{name}」已存在")
        tag.name = name

    if payload.color is not None:
        tag.color = payload.color

    session.add(tag)
    session.commit()
    session.refresh(tag)

    return {"id": tag.id, "name": tag.name, "color": tag.color}


@router.delete("/{tag_id}")
def delete_tag(
    tag_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """删标签 —— 题目保留，只解除关联"""
    tag = _own_tag(tag_id, session, user)

    # 先解关联（题目本身不动）
    for link in session.exec(
        select(QuestionTag).where(QuestionTag.tag_id == tag_id)
    ).all():
        session.delete(link)

    session.delete(tag)
    session.commit()
    return {"ok": True, "deleted": tag_id}


# === 题目 ↔ 标签 ===


@router.get("/question/{question_id}")
def get_question_tags(
    question_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """某题的标签"""
    _own_question(question_id, session, user)

    tag_ids = _tag_ids_of(question_id, session)
    if not tag_ids:
        return {"items": []}

    tags = session.exec(
        select(Tag).where(Tag.id.in_(tag_ids)).order_by(Tag.id)
    ).all()
    return {
        "items": [
            {"id": t.id, "name": t.name, "color": t.color}
            for t in tags
        ]
    }


@router.put("/question/{question_id}")
def set_question_tags(
    question_id: int,
    payload: QuestionTagsSet,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """设置某题的标签（整体替换）"""
    _own_question(question_id, session, user)
    uid = user.id or 0

    # 只接受自己的标签 —— 别人的标签 id 静默丢弃
    valid_ids: list[int] = []
    if payload.tag_ids:
        for tag in session.exec(
            select(Tag).where(Tag.user_id == uid, Tag.id.in_(payload.tag_ids))
        ).all():
            if tag.id is not None:
                valid_ids.append(tag.id)

    # 清掉原有关联
    for link in session.exec(
        select(QuestionTag).where(QuestionTag.question_id == question_id)
    ).all():
        session.delete(link)
    session.flush()

    # 建新的
    for tag_id in dict.fromkeys(valid_ids):  # 去重且保序
        session.add(QuestionTag(question_id=question_id, tag_id=tag_id))

    session.commit()

    return {"ok": True, "tag_ids": list(dict.fromkeys(valid_ids))}
