"""试卷 CRUD + PDF 导出路由 — lesson-09

| 方法 | 路径 | 作用 |
|---|---|---|
| GET    | /api/papers/                    | 试卷列表 |
| POST   | /api/papers/                    | 新建试卷 |
| GET    | /api/papers/{id}                | 试卷详情（含题目 + 题号）|
| PUT    | /api/papers/{id}                | 更新试卷（标题/题目/题号/分值）|
| DELETE | /api/papers/{id}                | 删除试卷 |
| POST   | /api/papers/{id}/questions      | 加题到试卷 |
| DELETE | /api/papers/{id}/questions/{pq_id} | 从试卷移除题 |
| GET    | /api/papers/{id}/export.pdf     | 导出 PDF |
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.database import get_session
from app.models import Paper, PaperQuestion, Question, auto_label
from app.services.pdf_export import PdfExportError, export_paper_pdf

router = APIRouter(
    prefix="/papers",
    tags=["试卷"],
)


# === 请求体 ===
class PaperCreate(BaseModel):
    title: str = Field(default="未命名试卷", max_length=200)
    subtitle: str = Field(default="", max_length=200)
    question_ids: list[int] = Field(default_factory=list)


class PaperUpdate(BaseModel):
    title: Optional[str] = None
    subtitle: Optional[str] = None


class PaperQuestionCreate(BaseModel):
    question_id: int
    label: str = Field(default="", max_length=50)
    score: float = Field(default=0.0)


class PaperQuestionUpdate(BaseModel):
    label: Optional[str] = None
    score: Optional[float] = None
    order_index: Optional[int] = None


# === 列表 ===
@router.get("/")
def list_papers(session: Session = Depends(get_session)):
    """试卷列表"""
    papers = session.exec(select(Paper).order_by(Paper.created_at.desc())).all()

    items = []
    for p in papers:
        count = len(session.exec(
            select(PaperQuestion).where(PaperQuestion.paper_id == p.id)
        ).all())
        items.append({
            "id": p.id,
            "title": p.title,
            "subtitle": p.subtitle,
            "question_count": count,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        })

    return {"items": items, "total": len(items)}


# === 新建 ===
@router.post("/")
def create_paper(payload: PaperCreate, session: Session = Depends(get_session)):
    """新建试卷（可同时加题）"""
    paper = Paper(title=payload.title, subtitle=payload.subtitle)
    session.add(paper)
    session.commit()
    session.refresh(paper)

    # 按传入顺序加题
    for index, qid in enumerate(payload.question_ids):
        if not session.get(Question, qid):
            continue  # 题目不存在就跳过（不因为一个坏 id 整个失败）
        session.add(PaperQuestion(
            paper_id=paper.id,
            question_id=qid,
            order_index=index,
            label=auto_label(index),
        ))

    session.commit()
    session.refresh(paper)

    return _paper_detail(paper, session)


# === 详情 ===
@router.get("/{paper_id}")
def get_paper(paper_id: int, session: Session = Depends(get_session)):
    """试卷详情（含题目列表 + 题号）"""
    paper = session.get(Paper, paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="试卷不存在")
    return _paper_detail(paper, session)


# === 更新 ===
@router.put("/{paper_id}")
def update_paper(
    paper_id: int,
    payload: PaperUpdate,
    session: Session = Depends(get_session),
):
    """更新试卷基本信息（标题/副标题）"""
    paper = session.get(Paper, paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="试卷不存在")

    if payload.title is not None:
        paper.title = payload.title
    if payload.subtitle is not None:
        paper.subtitle = payload.subtitle

    from datetime import datetime, timezone
    paper.updated_at = datetime.now(timezone.utc)

    session.add(paper)
    session.commit()
    session.refresh(paper)

    return _paper_detail(paper, session)


# === 删除 ===
@router.delete("/{paper_id}")
def delete_paper(paper_id: int, session: Session = Depends(get_session)):
    """删除试卷（关联的题目记录一起删）"""
    paper = session.get(Paper, paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="试卷不存在")

    # 先删关联（外键约束）
    for pq in session.exec(
        select(PaperQuestion).where(PaperQuestion.paper_id == paper_id)
    ).all():
        session.delete(pq)

    session.delete(paper)
    session.commit()

    return {"deleted": True, "id": paper_id}


# === 加题 ===
@router.post("/{paper_id}/questions")
def add_question(
    paper_id: int,
    payload: PaperQuestionCreate,
    session: Session = Depends(get_session),
):
    """往试卷里加一道题"""
    paper = session.get(Paper, paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="试卷不存在")

    question = session.get(Question, payload.question_id)
    if not question:
        raise HTTPException(status_code=404, detail="题目不存在")

    # 排在最后
    existing = session.exec(
        select(PaperQuestion).where(PaperQuestion.paper_id == paper_id)
    ).all()
    next_index = max((pq.order_index for pq in existing), default=-1) + 1

    pq = PaperQuestion(
        paper_id=paper_id,
        question_id=payload.question_id,
        order_index=next_index,
        label=payload.label or auto_label(next_index),
        score=payload.score,
    )
    session.add(pq)
    session.commit()
    session.refresh(pq)

    return {
        "id": pq.id,
        "paper_id": pq.paper_id,
        "question_id": pq.question_id,
        "order_index": pq.order_index,
        "label": pq.label,
        "score": pq.score,
    }


# === 改题号/分值/顺序 ===
@router.put("/{paper_id}/questions/{pq_id}")
def update_paper_question(
    paper_id: int,
    pq_id: int,
    payload: PaperQuestionUpdate,
    session: Session = Depends(get_session),
):
    """改某道题在试卷里的题号/分值/顺序"""
    pq = session.get(PaperQuestion, pq_id)
    if not pq or pq.paper_id != paper_id:
        raise HTTPException(status_code=404, detail="试卷里的题目不存在")

    if payload.label is not None:
        pq.label = payload.label
    if payload.score is not None:
        pq.score = payload.score
    if payload.order_index is not None:
        pq.order_index = payload.order_index

    session.add(pq)
    session.commit()
    session.refresh(pq)

    return {
        "id": pq.id,
        "paper_id": pq.paper_id,
        "question_id": pq.question_id,
        "order_index": pq.order_index,
        "label": pq.label,
        "score": pq.score,
    }


# === 移除题 ===
@router.delete("/{paper_id}/questions/{pq_id}")
def remove_question(paper_id: int, pq_id: int, session: Session = Depends(get_session)):
    """从试卷里移除一道题"""
    pq = session.get(PaperQuestion, pq_id)
    if not pq or pq.paper_id != paper_id:
        raise HTTPException(status_code=404, detail="试卷里的题目不存在")

    session.delete(pq)
    session.commit()

    return {"deleted": True, "id": pq_id}


# === 导出 PDF ===
@router.get("/{paper_id}/export.pdf")
def export_pdf(paper_id: int, session: Session = Depends(get_session)):
    """导出试卷 PDF

    返回 PDF 二进制（Content-Type: application/pdf + 附件下载头）
    """
    paper = session.get(Paper, paper_id)
    if not paper:
        raise HTTPException(status_code=404, detail="试卷不存在")

    detail = _paper_detail(paper, session)
    if not detail["questions"]:
        raise HTTPException(status_code=400, detail="试卷里还没有题目")

    # 组装 PDF 需要的数据
    items = []
    for item in detail["questions"]:
        items.append({
            "label": item["label"],
            # 用 markdown 版 → Chromium 里的 KaTeX 能渲染 $...$
            "content": item["question"]["content_markdown"] or item["question"]["content_plain"],
            "score": item["score"],
        })

    try:
        pdf_bytes = export_paper_pdf(
            paper={"title": paper.title, "subtitle": paper.subtitle},
            items=items,
        )
    except PdfExportError as e:
        raise HTTPException(status_code=500, detail=str(e))

    # 文件名要处理中文（RFC 5987）
    from urllib.parse import quote
    filename = f"{paper.title}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f"attachment; filename=\"paper.pdf\"; "
                f"filename*=UTF-8''{quote(filename)}"
            ),
        },
    )


# === 辅助 ===
def _paper_detail(paper: Paper, session: Session) -> dict:
    """试卷详情（题目 + 题号 + 分值）"""
    pqs = session.exec(
        select(PaperQuestion)
        .where(PaperQuestion.paper_id == paper.id)
        .order_by(PaperQuestion.order_index)
    ).all()

    questions = []
    for index, pq in enumerate(pqs):
        question = session.get(Question, pq.question_id)
        if not question:
            continue
        questions.append({
            "id": pq.id,
            "question_id": pq.question_id,
            "order_index": pq.order_index,
            # 题号：自定义优先，空则自动
            "label": pq.label or auto_label(index),
            "score": pq.score,
            "question": {
                "id": question.id,
                "subject": question.subject,
                "question_type": question.question_type,
                "grade": question.grade,
                "difficulty": question.difficulty,
                "content_plain": question.content_plain,
                "content_markdown": question.content_markdown,
                "image_path": question.image_path,
            },
        })

    return {
        "id": paper.id,
        "title": paper.title,
        "subtitle": paper.subtitle,
        "questions": questions,
        "created_at": paper.created_at.isoformat() if paper.created_at else None,
        "updated_at": paper.updated_at.isoformat() if paper.updated_at else None,
    }
