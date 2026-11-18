"""question

题库域 —— 分类、题目、标签、上传图片。

这一域管的是「老师存了什么」：录进来的题、章节树、标签体系，
以及题目引用的图片记录（uploads 负责归属校验）。
"""

import json
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import Column, ForeignKey, Integer
from sqlmodel import Field, Relationship, SQLModel



class Category(SQLModel, table=True):
    """章节分类（树）

    为什么要单独的表
    --------------
    之前的「章节树」是按 subject/grade/difficulty 三个字段**拼**出来的 ——
    看着像树，其实改不了、拖不动、也没有真正的归属关系。
    原型 ⑥ 要求「章节树维护 + 拖拽排序 + 题目统计」，那得有一张真表。

    两级就够：
    - 学科（如「高中数学」）
    - 章节（如「函数与导数」）
    parent_id 为空 = 顶层；否则指向上级 category.id
    """

    __tablename__ = "categories"

    id: Optional[int] = Field(default=None, primary_key=True)

    # === 归属 ===
    user_id: int = Field(foreign_key="users.id", index=True, nullable=False)

    # === 树结构 ===
    name: str = Field(max_length=50)
    # 父分类；None = 顶层
    parent_id: Optional[int] = Field(default=None, foreign_key="categories.id", index=True)
    # 同级排序（拖拽后写这个）
    sort_order: int = Field(default=0)

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class Question(SQLModel, table=True):
    """一道题

    字段命名用 ``question_type`` 而不是 ``type``
    —— ``type`` 是 Python 内建名，容易和 SQLModel 的元信息混淆。
    """

    __tablename__ = "questions"

    # === 主键 ===
    id: Optional[int] = Field(default=None, primary_key=True)

    # === 归属 ===
    # 哪个用户的题 —— 数据隔离的依据（NOT NULL：不允许无主数据）
    user_id: int = Field(foreign_key="users.id", index=True, nullable=False)

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

    # === 题目配图（几何示意图）===
    # OCR 认不出图 —— 从原图里裁出来的独立 PNG，导出试卷时带上。
    # 和 image_path（原图 / OCR 来源）不是一回事，别混。
    figure_path: str = Field(default="", max_length=500)

    # === 题图排版（老师可自定义 · 只给三个选项）===
    # bottom_right(文字下方·右下角,默认) / bottom_left(文字下方·左下角)
    # / none(不显示题图)
    figure_layout: str = Field(default="bottom_right", max_length=20)
    # 题图宽度占题目宽度的百分比，0 = 用该版式的默认宽度
    figure_width: int = Field(default=0)

    # === 章节归属 ===
    # 属于哪个章节（分类树节点）；空 = 未归类
    category_id: Optional[int] = Field(default=None, foreign_key="categories.id", index=True)

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

class Tag(SQLModel, table=True):
    """标签（用户自定义的题目标签）

    和分类树（Category）的区别
    ----------------------
    - Category 是**层级**结构，一题只能属于一个分类
    - Tag 是**扁平**结构，一题可以打多个标签

    典型用法：「期末冲刺」「高考真题」「易错题」「需要板书」
    """

    __tablename__ = "tags"

    id: Optional[int] = Field(default=None, primary_key=True)

    # === 归属 ===
    user_id: int = Field(foreign_key="users.id", index=True, nullable=False)

    # === 标签本身 ===
    name: str = Field(max_length=30)
    # 颜色（十六进制，如 #18a058）—— 给标签一点视觉区分度
    color: str = Field(default="#18a058", max_length=10)

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class QuestionTag(SQLModel, table=True):
    """题目 ↔ 标签（多对多关联表）

    为什么要独立表而不是 Question 里存 id 列表：
    标签是**共享**的 —— 同一批题都可能被标上「易错题」，
    存在关联表里才能反查「这个标签下有哪些题」。
    """

    __tablename__ = "question_tags"

    id: Optional[int] = Field(default=None, primary_key=True)

    question_id: int = Field(foreign_key="questions.id", index=True)
    tag_id: int = Field(foreign_key="tags.id", index=True)

    # 关联
    question: Optional[Question] = Relationship()
    tag: Optional[Tag] = Relationship()

class Upload(SQLModel, table=True):
    """上传的图片记录

    为什么要这张表
    --------------
    光有文件名不够 —— **归属信息必须落库**。
    之前 ``questions.image_path`` 只存了路径字符串，
    读图片时无法判断「这张图是谁的」，隔离就无从谈起。

    这张表是「文件名 → 归属」的映射：
    读图片时先查表拿到 user_id，再和当前登录用户比对。

    文件本身仍放磁盘（uploads/），数据库只存元信息。
    """

    __tablename__ = "uploads"

    id: Optional[int] = Field(default=None, primary_key=True)

    # === 归属 ===
    # 哪个用户上传的 —— 读图片时校验这个
    user_id: int = Field(foreign_key="users.id", index=True, nullable=False)

    # === 文件信息 ===
    # 磁盘上的文件名（不含目录）
    filename: str = Field(index=True, unique=True, max_length=255)

    # 对外 URL（前缀 + filename）
    url: str = Field(max_length=500)

    # 原始文件名（老师上传时的名字，可能含题干关键词）
    original_name: str = Field(default="", max_length=255)

    # 文件大小（字节）
    size: int = Field(default=0)

    # MIME 类型
    content_type: str = Field(default="", max_length=100)

    # === 元信息 ===
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
