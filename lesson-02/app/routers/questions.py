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
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlmodel import Session, select

from app.database import get_session
from app.models import Category, Paper, PaperQuestion, Question, Upload, User
from app.services.auth import get_current_user
from app.services.classifier import build_content_versions, classify_blocks
from app.services.errors import CODE_NOT_FOUND, ApiHTTPException
from app.services.paths import upload_file_path, uploads_dir
from app.services.paths import upload_file_path, uploads_dir

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
    # 题目配图（几何示意图）—— /api/uploads/ 下的文件名路径
    figure_path: str = Field(default="", max_length=500)
    ocr_task_id: str = Field(default="", max_length=100)
    # 分类：前端可以传（用户手动改过），不传就后端自动分类
    subject: Optional[str] = None
    question_type: Optional[str] = None
    grade: Optional[str] = None
    difficulty: Optional[str] = None
    # 章节分类（categories.id）—— 不传 = 不归类
    category_id: Optional[int] = None


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
    category_id: Optional[int] = None


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
    figure_path: Optional[str] = None
    # 允许置空（把题从章节里摘出去）
    figure_path: Optional[str] = None
    # 允许置空（把题从章节里摘出去）
    # 允许置空（把题从章节里摘出来）—— 靠 exclude_unset 区分「没传」和「传 null」
    category_id: Optional[int] = None



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


def _own_category_id(category_id, session: Session, user: User):
    """校验分类归属，返回合法的 category_id（None = 不归类）

    别人的分类 id 一律拒绝 —— 不能把题挂到别人的树上。
    """
    if category_id is None:
        return None
    category = session.get(Category, category_id)
    if category is None or category.user_id != (user.id or 0):
        raise HTTPException(status_code=400, detail="章节分类不存在或不属于你")
    return category_id


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
        if payload.category_id is not None:
            question.category_id = _own_category_id(
                payload.category_id, session, current_user
            )
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
    # ⚠️ 课 33：仪表盘卡片只要题干，不要 blocks（每题最多 50 KB）
    return {"items": [_to_dict(q, with_blocks=False) for q in items]}


# === Excel 导出 ===
@router.get("/export/excel")
def export_excel(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """导出我的题库为 Excel

    老师最怕的是数据丢了 —— 这是「导出」的刚需。
    只导当前用户的题；带 CSV 兜底（openpyxl 缺失时不至于 500）。
    """
    from datetime import datetime, timezone

    from fastapi import Response

    items = session.exec(
        select(Question)
        .where(Question.user_id == (current_user.id or 0))
        .order_by(Question.created_at.asc())
    ).all()

    rows = [
        {
            "id": q.id,
            "subject": q.subject,
            "question_type": q.question_type,
            "grade": q.grade,
            "difficulty": q.difficulty,
            "content_plain": q.content_plain,
            "content_markdown": q.content_markdown,
            "created_at": q.created_at.strftime("%Y-%m-%d %H:%M") if q.created_at else "",
        }
        for q in items
    ]

    headers = ["ID", "学科", "题型", "学段", "难度", "题干(纯文本)", "题干(Markdown)", "创建时间"]

    # === Excel ===
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter

        wb = Workbook()
        ws = wb.active
        ws.title = "我的题库"

        # 表头
        head_fill = PatternFill("solid", fgColor="F0F0F0")
        for col, name in enumerate(headers, start=1):
            cell = ws.cell(row=1, column=col, value=name)
            cell.font = Font(bold=True)
            cell.fill = head_fill
            cell.alignment = Alignment(horizontal="center")

        # 数据
        for r, row in enumerate(rows, start=2):
            for c, key in enumerate(
                ["id", "subject", "question_type", "grade", "difficulty",
                 "content_plain", "content_markdown", "created_at"],
                start=1,
            ):
                ws.cell(row=r, column=c, value=row.get(key, ""))

        # 列宽
        widths = [6, 10, 10, 8, 8, 60, 60, 18]
        for i, w in enumerate(widths, start=1):
            ws.column_dimensions[get_column_letter(i)].width = w

        # 题干列换行 + 顶端对齐
        for r in range(2, len(rows) + 2):
            for c in (6, 7):
                ws.cell(row=r, column=c).alignment = Alignment(wrap_text=True, vertical="top")

        import io

        buf = io.BytesIO()
        wb.save(buf)
        content = buf.getvalue()
        filename = f"我的题库_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
    except ImportError:
        # openpyxl 没装 → 退化成 CSV（Excel 也能打开）
        import csv
        import io

        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(headers)
        for row in rows:
            writer.writerow([row.get(k, "") for k in
                             ["id", "subject", "question_type", "grade", "difficulty",
                              "content_plain", "content_markdown", "created_at"]])
        # BOM: Excel 打开 CSV 需要它才认 UTF-8
        content = b"\xef\xbb\xbf" + buf.getvalue().encode("utf-8")
        filename = f"我的题库_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"

    from urllib.parse import quote

    return Response(
        content=content,
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            if filename.endswith(".xlsx")
            else "text/csv"
        ),
        headers={
            "Content-Disposition": (
                f"attachment; filename=\"export.xlsx\"; "
                f"filename*=UTF-8''{quote(filename)}"
            ),
        },
    )


# === 全部备份（JSON）===
@router.get("/export/backup")
def export_backup(
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """导出我的全部数据（题目 + 试卷 + 组卷关系）为 JSON

    老师最怕的是数据丢了 —— 这是「一键备份」。
    题库里的图片不在这里（图片在 uploads 目录，另有单图下载），
    这里备的是**结构化数据**，够在别的系统重建。
    """
    from datetime import datetime, timezone

    from fastapi import Response

    uid = current_user.id or 0
    questions = session.exec(
        select(Question).where(Question.user_id == uid).order_by(Question.id)
    ).all()
    papers = session.exec(
        select(Paper).where(Paper.user_id == uid).order_by(Paper.id)
    ).all()

    paper_ids = {p.id for p in papers}
    relations = session.exec(
        select(PaperQuestion).where(PaperQuestion.paper_id.in_(paper_ids)).order_by(PaperQuestion.order_index)
    ).all() if paper_ids else []

    data = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "user": {"id": uid, "username": current_user.username},
        "questions": [
            {
                "id": q.id,
                "subject": q.subject,
                "question_type": q.question_type,
                "grade": q.grade,
                "difficulty": q.difficulty,
                "content_plain": q.content_plain,
                "content_markdown": q.content_markdown,
                "blocks_json": q.blocks_json,
                "image_path": q.image_path,
                "figure_path": q.figure_path,
                "ocr_task_id": q.ocr_task_id,
                "created_at": q.created_at.isoformat() if q.created_at else None,
            }
            for q in questions
        ],
        "papers": [
            {
                "id": p.id,
                "title": p.title,
                "subtitle": p.subtitle,
                "created_at": p.created_at.isoformat() if p.created_at else None,
            }
            for p in papers
        ],
        "paper_questions": [
            {
                "paper_id": r.paper_id,
                "question_id": r.question_id,
                "order_index": r.order_index,
                "label": r.label,
                "score": r.score,
            }
            for r in relations
        ],
    }

    import json

    from urllib.parse import quote

    filename = f"题库备份_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
    return Response(
        content=json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"),
        media_type="application/json",
        headers={
            "Content-Disposition": (
                f"attachment; filename=\"backup.json\"; "
                f"filename*=UTF-8''{quote(filename)}"
            ),
        },
    )


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
    category_id: Optional[int] = Query(default=None, description="按章节分类筛选（含子分类）"),
    tag_ids: Optional[str] = Query(
        default=None,
        description="按标签筛选，逗号分隔（如 1,2）；多标签取交集",
    ),
    sort: str = Query(
        default="created_at",
        description="排序字段：created_at/updated_at/difficulty/subject/question_type",
    ),
    order: str = Query(default="desc", description="排序方向：asc/desc"),
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
    if category_id is not None:
        # 含子分类 —— 点父节点要能看到整个子树
        from app.models import Category
        from app.routers.categories import _child_ids

        ids = _child_ids(category_id, session, current_user.id or 0)
        stmt = stmt.where(Question.category_id.in_(ids))
    # 按标签筛选 —— 多标签取「交集」（同一道题要同时有这些标签）
    tag_id_list: list[int] = []
    if tag_ids:
        for part in tag_ids.split(","):
            part = part.strip()
            if part.isdigit():
                tag_id_list.append(int(part))
    if tag_id_list:
        from app.models import QuestionTag

        # 逐个标签取交集：题必须同时有这些标签
        for tid in tag_id_list:
            sub = (
                select(QuestionTag.question_id)
                .where(QuestionTag.tag_id == tid)
            )
            stmt = stmt.where(Question.id.in_(sub))

    # 排序 —— 字段白名单，防注入
    sort_columns = {
        "created_at": Question.created_at,
        "updated_at": Question.updated_at,
        "difficulty": Question.difficulty,
        "subject": Question.subject,
        "question_type": Question.question_type,
    }
    column = sort_columns.get(sort, Question.created_at)
    stmt = stmt.order_by(column.asc() if order == "asc" else column.desc())
    stmt = stmt.offset(offset).limit(limit)

    items = session.exec(stmt).all()

    # 总数(不带 limit/offset,用于前端分页)
    # ⚠️ 课 33 性能：原来写的是 `len(session.exec(count_stmt).all())` ——
    #    把**所有**符合条件的题拉进 Python 再数个数。
    #    题库到几千道时,这一步就是「加载整表」—— 白白浪费一次全表扫描 + 内存。
    #    正确做法：让数据库只回一个数字（COUNT 在库里算）。
    count_stmt = select(func.count()).select_from(Question).where(Question.user_id == (current_user.id or 0))
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
    if category_id is not None:
        from app.models import Category
        from app.routers.categories import _child_ids

        ids = _child_ids(category_id, session, current_user.id or 0)
        count_stmt = count_stmt.where(Question.category_id.in_(ids))
    # 按标签筛选 —— 多标签取「交集」（同一道题要同时有这些标签）
    tag_id_list: list[int] = []
    if tag_ids:
        for part in tag_ids.split(","):
            part = part.strip()
            if part.isdigit():
                tag_id_list.append(int(part))
    if tag_id_list:
        from app.models import QuestionTag

        # 逐个标签取交集：题必须同时有这些标签
        for tid in tag_id_list:
            sub = (
                select(QuestionTag.question_id)
                .where(QuestionTag.tag_id == tid)
            )
            count_stmt = count_stmt.where(Question.id.in_(sub))
    total = session.exec(count_stmt).one()

    # 批量取标签（一次查询，别在循环里查）
    tag_map = _tags_map([q.id for q in items if q.id is not None], session)

    return {
        "items": [
            # ⚠️ 课 33：列表不带 blocks（单题最多 50 KB，50 道题 = 165 KB 白下）
            _to_dict(
                q,
                tag_map.get(q.id, []) if q.id is not None else [],
                with_blocks=False,
            )
            for q in items
        ],
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
    tag_map = _tags_map([question_id], session)
    return _to_dict(question, tag_map.get(question_id, []))


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
        category_id=_own_category_id(payload.category_id, session, current_user),
    )

    session.add(question)
    session.commit()
    session.refresh(question)

    return _to_dict(question)


# === 几何示意图：从原图里裁出来 ===


def _extract_figure(
    record: dict,
    blocks: list[dict],
    session: Session,
    current_user: User,
) -> str:
    """把题图里的几何示意图裁出来，存成独立文件

    返回 /api/uploads/xxx_fig.png；裁不出来返回空串。

    为什么单独存一份
    ----------------
    OCR 认出的只是**文字**，三角形、垂足这些图形元素它一个也读不出来。
    原图里图明明还在 —— 但题目库里只存了路径，导出时那张图就被扔了，
    学生的卷子上只剩一段没有图的证明题。

    裁不出来宁可没有：宁可题里没图，也不要把一行没认出来的字当成图贴上去。
    """
    from app.services.figure_crop import crop_bbox_png, crop_figure_png

    image_url = record.get("image_url", "")
    filename = (image_url or "").rsplit("/", 1)[-1]
    src = upload_file_path(filename)
    if not src:
        return ""

    # 强模型(PP-StructureV3)的版面模型会把图形标成 figure 块并给出 bbox ——
    # 模型直接说「图在这儿」，比自己猜准得多，有就用它的。
    fig_bbox = None
    for b in blocks or []:
        if isinstance(b, dict) and b.get("type") == "figure":
            bb = b.get("bbox")
            if bb and len(bb) >= 4:
                fig_bbox = [float(v) for v in bb[:4]]
                break

    try:
        if fig_bbox:
            png = crop_bbox_png(src, fig_bbox)
        else:
            png = crop_figure_png(src, blocks)
    except Exception:
        # 裁图失败不许影响入库 —— 图是锦上添花，题才是主菜
        return ""
    if not png:
        return ""

    out_name = f"{Path(filename).stem}_fig.png"
    try:
        (uploads_dir() / out_name).write_bytes(png)
    except OSError:
        return ""

    # 同一张图重复入库（比如老师把同一张截图 OCR 两次）时，配图文件名会撞 ——
    # uploads.filename 是唯一键，硬插直接 500。已经在就复用，不重复登记。
    existing = session.exec(
        select(Upload).where(Upload.filename == out_name)
    ).first()
    if existing is not None:
        return f"/api/uploads/{out_name}"

    session.add(
        Upload(
            user_id=current_user.id or 0,
            filename=out_name,
            url=f"/api/uploads/{out_name}",
            original_name=f"{filename} (配图)"[:255],
            size=len(png),
            content_type="image/png",
        )
    )
    return f"/api/uploads/{out_name}"


# === 从 OCR 一键入库 ===
# 完整路径: POST /api/questions/from-ocr/{task_id}
@router.post("/from-ocr/{task_id}")
def create_from_ocr(
    task_id: str,
    payload: dict | None = None,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """从 OCR 结果一键入库

    后端自己读 ocr_store 的记录 + 跑分类器,
    前端只要传 task_id。
    """
    from app.services.ocr_store import TASKS, is_task_visible

    record = TASKS.get(task_id)

    # ⚠️ 归属校验 —— 之前任何登录用户拿 task_id 就能把**别人**的 OCR 结果入库。
    # 越权一律 404(不返 403):不泄露「这个 task_id 存不存在」。
    if not is_task_visible(
        record, current_user.id or 0, is_admin=bool(current_user.is_admin)
    ):
        raise ApiHTTPException(
            status_code=404,
            detail="OCR 任务不存在或已过期",
            code=CODE_NOT_FOUND,
        )

    result = record.get("result") or {}
    blocks = result.get("blocks") or []
    if not blocks:
        raise HTTPException(status_code=400, detail="该 OCR 任务没有识别结果")

    versions = build_content_versions(blocks)
    auto = classify_blocks(blocks)

    # === 老师手动改过的分类优先 ===
    # 老师在 OCR 校对页把难度从「简单」改成「困难」，点一键入库时，
    # 以前这里只用 AI 的分类结果 —— 老师改的难度当场就丢了。
    # 前端不传（老客户端）就还是走 AI 分类，行为不变。
    override = payload or {}
    subject = override.get("subject") or auto["subject"]
    question_type = override.get("question_type") or auto["type"]
    grade = override.get("grade") or auto["grade"]
    difficulty = override.get("difficulty") or auto["difficulty"]

    # === 几何示意图 ===
    # OCR 只能读文字，读不出三角形、垂足、辅助线 —— 图会整个丢掉。
    # 这里从原图里把图裁出来单独存一份，导出试卷时再带上。
    figure_path = _extract_figure(record, blocks, session, current_user)

    question = Question(
        user_id=current_user.id or 0,
        subject=subject,
        question_type=question_type,
        grade=grade,
        difficulty=difficulty,
        content_plain=versions["plain"],
        content_markdown=versions["markdown"],
        blocks_json=versions["blocks_json"],
        image_path=_normalize_image_path(record.get("image_url", "")),
        figure_path=figure_path,
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
        "figure_path",
    ):
        if field in data and data[field] is not None:
            setattr(question, field, data[field])

    # category_id 单独处理：允许置空（把题从章节里摘出来）
    if "category_id" in data:
        question.category_id = _own_category_id(
            data["category_id"], session, current_user
        )

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



def _tags_map(question_ids: list[int], session: Session) -> dict[int, list[dict]]:
    """批量取题目的标签 —— 避免在列表里 N+1 查库

    返回 {question_id: [{id, name, color}, ...]}
    """
    if not question_ids:
        return {}

    from app.models import QuestionTag, Tag

    rows = session.exec(
        select(QuestionTag.question_id, QuestionTag.tag_id)
        .where(QuestionTag.question_id.in_(question_ids))
    ).all()
    if not rows:
        return {}

    tag_ids = list({r[1] for r in rows})
    tags = session.exec(select(Tag).where(Tag.id.in_(tag_ids))).all()
    tag_by_id = {t.id: t for t in tags}

    result: dict[int, list[dict]] = {}
    for qid, tid in rows:
        tag = tag_by_id.get(tid)
        if tag is None:
            continue
        result.setdefault(qid, []).append(
            {"id": tag.id, "name": tag.name, "color": tag.color}
        )
    return result


def _to_dict(
    question: Question,
    tags: list[dict] | None = None,
    *,
    with_blocks: bool = True,
) -> dict:
    """ORM 对象 → dict（给前端）

    tags 传了就带上标签数组（批量查一次，别在循环里查库）。

    ⚠️ 课 33 性能：**列表接口不要带 blocks**
    ------------------------------------
    ``blocks`` 是 OCR 的原始识别块（含每块 bbox 坐标），单题最多 50 KB。
    列表接口一次返回 50 道题 —— 实测响应从 24 KB 涨到 **165 KB**，
    而列表页（题目列表）**根本不用 blocks**（只有 OCR 校对页 / 题目详情页要）。

    所以列表走 ``with_blocks=False``；详情/新建/更新保持带（详情页要溯源 blocks）。
    """
    data = {
        "id": question.id,
        "subject": question.subject,
        "question_type": question.question_type,
        "grade": question.grade,
        "difficulty": question.difficulty,
        "content_plain": question.content_plain,
        "content_markdown": question.content_markdown,
        "image_path": question.image_path,
        "figure_path": question.figure_path,
        "ocr_task_id": question.ocr_task_id,
        "category_id": question.category_id,
        "created_at": question.created_at.isoformat() if question.created_at else None,
        "updated_at": question.updated_at.isoformat() if question.updated_at else None,
        "tags": tags or [],
    }
    if with_blocks:
        data["blocks"] = question.blocks
    return data
