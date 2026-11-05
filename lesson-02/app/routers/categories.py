"""章节分类路由 — lesson-11（原型 ⑥ 分类管理）

功能
----
- 树形读取（带每个节点的题目统计）
- 新建 / 重命名 / 删除
- 拖拽排序（同级重排）
- 题目挂到分类上

权限口径
--------
所有操作只作用于**当前登录用户自己的**分类 —— 与题库/试卷同一套隔离。
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.database import get_session
from app.models import Category, Question, User
from app.services.auth import get_current_user

router = APIRouter(
    prefix="/categories",
    tags=["章节分类"],
)


# === 请求体 ===

class CategoryCreate(BaseModel):
    name: str = Field(max_length=50)
    parent_id: Optional[int] = None


class CategoryUpdate(BaseModel):
    # ⚠️ Optional 必须显式给 default=None ——
    #    Pydantic v2 里 `Optional[str] = Field(max_length=50)` 仍是**必填**
    #    (只有 v1 才把 Optional 自动当可省) → 不传 name 就 422
    name: Optional[str] = Field(default=None, max_length=50)
    parent_id: Optional[int] = None


class ReorderRequest(BaseModel):
    """拖拽排序后的同级顺序

    ids 是同一父节点下的分类 id 列表（按新顺序）。
    """
    parent_id: Optional[int] = None
    ids: list[int] = Field(default_factory=list, max_length=500)


# === 辅助 ===

def _own_category(category_id: int, session: Session, user: User) -> Category:
    """取分类并校验归属 —— 别人的一律当「不存在」"""
    category = session.get(Category, category_id)
    if category is None or category.user_id != (user.id or 0):
        raise HTTPException(status_code=404, detail="分类不存在")
    return category


def _child_ids(category_id: int, session: Session, user_id: int) -> list[int]:
    """递归收集子分类 id（用于「含子分类」的筛选与统计）"""
    result = [category_id]
    frontier = [category_id]
    while frontier:
        children = session.exec(
            select(Category).where(
                Category.parent_id.in_(frontier),
                Category.user_id == user_id,
            )
        ).all()
        if not children:
            break
        frontier = [c.id for c in children if c.id is not None]
        result.extend(frontier)
    return result


def _is_descendant(candidate_id: int, ancestor_id: int, session: Session, user_id: int) -> bool:
    """candidate 是否是 ancestor 的后代（防把分类拖进自己的子孙里形成环）"""
    if candidate_id == ancestor_id:
        return True
    seen = set()
    current = candidate_id
    while current is not None and current not in seen:
        seen.add(current)
        node = session.get(Category, current)
        if node is None or node.user_id != user_id:
            return False
        current = node.parent_id
        if current == ancestor_id:
            return True
    return False


def _build_tree(session: Session, user: User) -> list[dict]:
    """构造树 + 每个节点的题目统计

    统计含子分类（点父节点看到的是整个子树的数量）。
    """
    uid = user.id or 0

    categories = session.exec(
        select(Category).where(Category.user_id == uid).order_by(Category.sort_order, Category.id)
    ).all()
    if not categories:
        return []

    # 题目按 category_id 计数
    counts: dict[int, int] = {}
    for row in session.exec(
        select(Question.category_id, Question.id).where(Question.user_id == uid)
    ).all():
        if row[0] is not None:
            counts[row[0]] = counts.get(row[0], 0) + 1

    by_id = {c.id: c for c in categories if c.id is not None}
    children_map: dict[Optional[int], list[Category]] = {}
    for c in categories:
        children_map.setdefault(c.parent_id, []).append(c)

    def subtree_count(node_id: int) -> int:
        total = counts.get(node_id, 0)
        for child in children_map.get(node_id, []):
            if child.id is not None:
                total += subtree_count(child.id)
        return total

    def to_node(c: Category) -> dict:
        node = {
            "id": c.id,
            "name": c.name,
            "parent_id": c.parent_id,
            "sort_order": c.sort_order,
            # 自己的 + 子孙的
            "count": subtree_count(c.id) if c.id is not None else 0,
            # 直接挂在这个节点上的题
            "own_count": counts.get(c.id, 0) if c.id is not None else 0,
        }
        kids = children_map.get(c.id, [])
        if kids:
            node["children"] = [to_node(k) for k in kids]
        return node

    roots = children_map.get(None, [])
    return [to_node(c) for c in roots]


# === 路由 ===

@router.get("/")
def list_categories(
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """章节树（含题目统计）"""
    return {"tree": _build_tree(session, user)}


@router.get("/flat")
def list_categories_flat(
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """扁平列表（题目编辑时选分类用）"""
    categories = session.exec(
        select(Category)
        .where(Category.user_id == (user.id or 0))
        .order_by(Category.sort_order, Category.id)
    ).all()
    return [
        {
            "id": c.id,
            "name": c.name,
            "parent_id": c.parent_id,
            "sort_order": c.sort_order,
        }
        for c in categories
    ]


@router.post("/")
def create_category(
    payload: CategoryCreate,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """新建分类"""
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="分类名不能为空")

    parent_id = payload.parent_id
    if parent_id is not None:
        _own_category(parent_id, session, user)

    # 同级排最后
    siblings = session.exec(
        select(Category).where(
            Category.user_id == (user.id or 0),
            Category.parent_id == parent_id,
        )
    ).all()
    next_order = max((c.sort_order for c in siblings), default=-1) + 1

    category = Category(
        user_id=user.id or 0,
        name=name,
        parent_id=parent_id,
        sort_order=next_order,
    )
    session.add(category)
    session.commit()
    session.refresh(category)

    return {
        "id": category.id,
        "name": category.name,
        "parent_id": category.parent_id,
        "sort_order": category.sort_order,
    }


@router.put("/{category_id}")
def update_category(
    category_id: int,
    payload: CategoryUpdate,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """重命名 / 改父节点"""
    category = _own_category(category_id, session, user)

    # ⚠️ 用 exclude_unset 区分「没传」和「显式传 null」
    #    parent_id=null = 移到顶层（拖拽排序需要），
    #    不传 parent_id = 保持原样（只改名字）
    data = payload.model_dump(exclude_unset=True)

    if "name" in data and data["name"] is not None:
        name = data["name"].strip()
        if not name:
            raise HTTPException(status_code=400, detail="分类名不能为空")
        category.name = name

    if "parent_id" in data:
        new_parent = data["parent_id"]
        if new_parent is not None:
            # 防环：不能挂到自己或自己的子孙下面
            if _is_descendant(new_parent, category_id, session, user.id or 0):
                raise HTTPException(status_code=400, detail="不能把分类移动到它自己或它的子分类下")
            _own_category(new_parent, session, user)
        category.parent_id = new_parent

    session.add(category)
    session.commit()
    session.refresh(category)

    return {
        "id": category.id,
        "name": category.name,
        "parent_id": category.parent_id,
        "sort_order": category.sort_order,
    }


@router.delete("/{category_id}")
def delete_category(
    category_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """删除分类

    - 子分类提到上一层（不跟着删）
    - 挂在它上面的题目 category_id 置空（题不删，只是失去归属）
    """
    category = _own_category(category_id, session, user)
    uid = user.id or 0

    # 子分类上提到父级
    for child in session.exec(
        select(Category).where(
            Category.parent_id == category_id,
            Category.user_id == uid,
        )
    ).all():
        child.parent_id = category.parent_id
        session.add(child)

    # 题目失去归属（题留着）
    for question in session.exec(
        select(Question).where(
            Question.category_id == category_id,
            Question.user_id == uid,
        )
    ).all():
        question.category_id = None
        session.add(question)

    session.delete(category)
    session.commit()
    return {"ok": True, "deleted": category_id}


@router.post("/reorder")
def reorder_categories(
    payload: ReorderRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """拖拽排序：按给定顺序重排同级分类"""
    uid = user.id or 0

    for index, category_id in enumerate(payload.ids):
        category = session.get(Category, category_id)
        if category is None or category.user_id != uid:
            continue
        category.sort_order = index
        session.add(category)

    session.commit()
    return {"ok": True, "count": len(payload.ids)}
