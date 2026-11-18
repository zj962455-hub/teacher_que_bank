"""paper

试卷域 —— 试卷、试卷题目、分享链接。

这一域管的是「怎么把题组装成卷并发出去」。
组卷默认用中文数字自动题号（auto_label）。
"""

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import Column, ForeignKey, Integer
from sqlmodel import Field, Relationship, SQLModel

from .question import Question


class Paper(SQLModel, table=True):
    """一张试卷（组卷）

    decisions.md 的 MVP 目标:
    「图片 OCR + 公式自动识别」→ 老师组卷 → 导出 PDF

    试卷跟题目的关系是多对多（一张卷可以有多道题，一道题也能进多张卷），
    所以中间需要 PaperQuestion 关联表。
    """

    __tablename__ = "papers"

    id: Optional[int] = Field(default=None, primary_key=True)

    # === 归属 ===
    # 哪个用户的卷 —— 数据隔离的依据（NOT NULL：不允许无主数据）
    user_id: int = Field(foreign_key="users.id", index=True, nullable=False)

    # 标题 —— 老师可自定义（「高一数学第一单元测试」这种）
    title: str = Field(default="未命名试卷", max_length=200)

    # 副标题（可选）—— 姓名/班级/日期那行
    subtitle: str = Field(default="", max_length=200)

    # 关联的题目（多对多）
    questions: list["PaperQuestion"] = Relationship(
        back_populates="paper",
        cascade_delete=True,
    )

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class PaperQuestion(SQLModel, table=True):
    """试卷里的一道题（关联表）

    为什么要独立一张表而不是 Paper 里存 id 列表：
    1. **顺序**（第几题）—— 存 list 改一次顺序要整个更新
    2. **自定义题号** —— 老师可能想要「一、」「(1)」「第一题」不同格式
    3. **分值** —— 组卷常见需求
    """

    __tablename__ = "paper_questions"

    id: Optional[int] = Field(default=None, primary_key=True)

    paper_id: int = Field(foreign_key="papers.id", index=True)
    question_id: int = Field(foreign_key="questions.id", index=True)

    # 排序（0 开始）
    order_index: int = Field(default=0)

    # 自定义题号 —— 空则用自动生成的序号
    label: str = Field(default="", max_length=50)

    # 分值（0 = 不显示）
    score: float = Field(default=0.0)

    # 关联
    paper: Optional[Paper] = Relationship(back_populates="questions")
    question: Optional[Question] = Relationship()

class PaperShare(SQLModel, table=True):
    """试卷分享链接（lesson-24）

    干什么用的
    ----------
    老师组完卷，点「生成分享链接」→ 把链接发到微信群 / 学生家长 →
    对方在浏览器点开就能看卷子、下 PDF / JPG，**不用账号**。

    为什么单独一张表
    --------------
    分享是「一次授权、限时、可吊销」的三元组 —— 离开表就存不下：
    - 属于哪张卷（paper_id）
    - 给谁用（token）
    - 什么时候失效（expires_at）
    - 还能不能用（revoked_at）

    token 为什么明文存
    -----------------
    会话 token 存哈希，因为会话等价于「账号本身」，泄露即失守。
    分享链接不一样：**老师要能反复复制同一个链接**（这周发班级群、下周发补课群），
    存哈希就永远拿不回原文，只能重新生成 —— 那不叫分享，叫发一次性的。
    它的泄露面也小得多：
    - 随机 32 字节 URL-safe token（256 位熵），猜不出来
    - 只授予**一张卷的只读查看**，拿不到账号、拿不到别的卷
    - 必带过期时间（默认 7 天），可随时吊销

    view_count / last_viewed_at 是**审计字段**：
    备案要求「记录访问日志」，分享链接是唯一一条对外暴露数据的口子，
    至少要能回答「这条链接被打开过几次、最后一次是什么时候」。
    """

    __tablename__ = "paper_shares"

    id: Optional[int] = Field(default=None, primary_key=True)

    # === 归属 ===
    # 谁的卷 —— 分享必须由卷的主人发起
    # ⚠️ 用 sa_column 显式写 ForeignKey(ondelete="CASCADE")：
    #    主人删了卷 / 账号被停用删掉 → 分享链接跟着消失（否则链接还在但打不开，
    #    还占着一条指向空卷的记录）。
    #    显式写还保证 create_all 建出来的表跟迁移脚本建出来的一致。
    user_id: int = Field(
        sa_column=Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    )

    # 分享的是哪张卷
    paper_id: int = Field(
        sa_column=Column(Integer, ForeignKey("papers.id", ondelete="CASCADE"), index=True, nullable=False)
    )

    # === 凭证 ===
    # 链接里的那串字符（URL-safe 随机数）
    token: str = Field(index=True, unique=True, max_length=64)

    # === 有效期 ===
    # 必填 —— 「带过期时间」是这节课的核心，不允许永久链接
    expires_at: datetime = Field(index=True)

    # 吊销时间（非空 = 已作废）
    revoked_at: Optional[datetime] = Field(default=None, index=True)

    # === 审计 ===
    view_count: int = Field(default=0)
    last_viewed_at: Optional[datetime] = Field(default=None)

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
