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

from sqlmodel import Field, SQLModel


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


# === 建表 ===
def create_tables() -> None:
    """建所有表（如果不存在）

    MVP 用这个而不是 Alembic —— lesson-08 是学 SQLModel，不是学迁移工具。
    lesson-10 部署上线时再补 Alembic（那时表结构可能已经改过几轮了）。
    """
    from app.database import engine

    SQLModel.metadata.create_all(engine)
    print("✅ 数据表已创建/确认")
