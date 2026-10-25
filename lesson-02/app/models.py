"""数据模型 — lesson-08

题目表设计
----------
一张 ``questions`` 表装下所有内容。为什么不拆成多张：

- MVP 阶段数据量小（个人题库几千题量级），单表查询简单
- 公式 blocks 用 JSON 字段存,不做关联表 —— 拆表要处理顺序/引用,收益不大
- 等 lesson-11+ 做标签/组卷再拆

三个内容版本并存
----------------
| 字段 | 内容 | 用途 |
|---|---|---|
| content_plain | 公式用 Unicode（x²） | 复制到 Word/微信 |
| content_markdown | 公式用 $...$ | 二次编辑、导入支持 LaTeX 的编辑器 |
| blocks_json | 完整 OCR blocks | 重新渲染、看 bbox、溯源 |

三个版本各有用处（今天 lesson-07 做的三个复制按钮正好对应），
存一份就不用每次重新 OCR。
"""

import json
from datetime import datetime, timezone
from typing import Any, Optional

from sqlmodel import Field, Relationship, SQLModel


class Question(SQLModel, table=True):
    """一道题

    字段命名用 ``question_type`` 而不是 ``type``
    —— ``type`` 是 Python 内建名，容易和 SQLModel 的元信息混淆。
    """

    __tablename__ = "questions"

    # === 主键 ===
    id: Optional[int] = Field(default=None, primary_key=True)

    # === 分类（lesson-06 任务 5C 的自动分类结果）===
    subject: str = Field(default="未知", index=True, max_length=20)
    question_type: str = Field(default="未知", index=True, max_length=20)
    grade: str = Field(default="通用", index=True, max_length=20)
    difficulty: str = Field(default="简单", index=True, max_length=20)

    # === 内容三版本 ===
    content_plain: str = Field(default="", max_length=10000)
    content_markdown: str = Field(default="", max_length=10000)
    blocks_json: str = Field(default="", max_length=50000)

    # === 来源 ===
    image_path: str = Field(default="", max_length=500)
    ocr_task_id: str = Field(default="", index=True, max_length=100)

    # === 元信息 ===
    # ⚠️ 必须用 datetime.now(timezone.utc) 而不是 datetime.now()
    #    字段类型是 TIMESTAMP WITH TIME ZONE,
    #    naive datetime(不带时区)插入会报:
    #    "Datetime values must have timezone information"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # === 便捷方法 ===

    @property
    def blocks(self) -> list[dict[str, Any]]:
        """把 blocks_json 解析成 list

        存成 str 是因为 SQLModel 的 JSON 字段在不同版本上行为不一致，
        统一用 str 存最稳，读取时自己 json.loads。
        """
        if not self.blocks_json:
            return []
        try:
            return json.loads(self.blocks_json)
        except json.JSONDecodeError:
            return []


class Paper(SQLModel, table=True):
    """一张试卷（组卷）

    decisions.md 的 MVP 目标:
    「图片 OCR + 公式自动识别」→ 老师组卷 → 导出 PDF

    试卷跟题目的关系是多对多（一张卷可以有多道题，一道题也能进多张卷），
    所以中间需要 PaperQuestion 关联表。
    """

    __tablename__ = "papers"

    id: Optional[int] = Field(default=None, primary_key=True)

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
