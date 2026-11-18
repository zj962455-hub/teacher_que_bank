"""feedback

反馈域 —— 老师的意见与处理状态。

这一域独立存在，因为访问控制完全不同：
老师提交、管理员改状态，是管理员功能而不是普通业务功能。
"""

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import Column, ForeignKey, Integer
from sqlmodel import Field, Relationship, SQLModel


class Feedback(SQLModel, table=True):
    """老师反馈 — 课 34

    灰度试用期间老师的意见（哪里点不动、想要什么功能）。
    收集到的东西没有价值，**收到了并且处理了**才有价值 ——
    所以除了内容，还记一个 status（新/已读/已处理）。

    谁能看
    ------
    - 普通用户：只看得到自己提的（避免互相看到别人的吐槽）
    - 管理员：看得到全部，且带提交人用户名 —— 这才是「处理反馈」的前提
    """

    __tablename__ = "feedbacks"

    id: Optional[int] = Field(default=None, primary_key=True)

    # 谁提的
    # ⚠️ ON DELETE CASCADE：账号被删 → 反馈一起删（不留孤儿记录）
    user_id: int = Field(
        sa_column=Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    )

    # 类别：bug / feature / other
    category: str = Field(default="other", max_length=20, index=True)

    # 正文（5–2000 字，长度在接口层校验）
    content: str = Field(default="", max_length=2000)

    # 提交人自报身份（课 34 · 共享账号下区分老师）
    #
    # ⚠️ 为什么不能只靠 user_id
    # ------------------
    # 灰度阶段几个老师**共用一个账号** → user_id 全是同一个，
    # 光看 user_id 分不出「这条反馈是谁提的」。
    # 所以老师提交时自报一下（「张老师·市三中」），为空则后端用 display_name 兜底。
    reporter: str = Field(default="", max_length=50)

    # 联系方式（选填：微信 / 手机）—— 管理员要跟进时用得上
    contact: str = Field(default="", max_length=100)

    # 提反馈时所在页面（管理员复现问题用）
    page_url: str = Field(default="", max_length=500)

    # 处理状态：new / read / resolved
    status: str = Field(default="new", max_length=20, index=True)

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# === 中文数字（自动题号用） ===
# 一 二 三 ... 十 十一 ... 二十
CN_NUMBERS = [
    "一", "二", "三", "四", "五", "六", "七", "八", "九", "十",
    "十一", "十二", "十三", "十四", "十五", "十六", "十七", "十八", "十九", "二十",
    "二十一", "二十二", "二十三", "二十四", "二十五", "二十六", "二十七", "二十八",
    "二十九", "三十",
]


def auto_label(index: int) -> str:
    """自动题号（0-based → 「一、」「二、」）

    组卷默认用中文数字 + 顿号（数学卷的惯例）。
    超过 30 题就退回阿拉伯数字。
    """
    if 0 <= index < len(CN_NUMBERS):
        return f"{CN_NUMBERS[index]}、"
    return f"{index + 1}."


# === 建表 ===
def create_tables() -> None:
    """建所有表（如果不存在）

    MVP 用这个而不是 Alembic —— lesson-08 是学 SQLModel，不是学迁移工具。
    lesson-10 部署上线时再补 Alembic（那时表结构可能已经改过几轮了）。
    """
    from app.database import engine

    SQLModel.metadata.create_all(engine)
    print("✅ 数据表已创建/确认")
