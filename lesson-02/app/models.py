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


class User(SQLModel, table=True):
    """用户账户（邀请制注册）

    账号不是自助注册的 —— 由管理员预创建后分发，登录后可自行改密。

    软删除：删除账号 = ``is_active=False``（停用登录），数据保留。
    这样题目/试卷不会因为人走了而丢失，也满足备案「可单独停用账号」的要求。
    """

    __tablename__ = "users"

    # === 主键 ===
    id: Optional[int] = Field(default=None, primary_key=True)

    # === 身份 ===
    # 登录名，全局唯一（index + unique 双重保险：unique 才是真正的约束）
    username: str = Field(index=True, unique=True, max_length=50)

    # 显示名（老师互相认识的名字，可以是真实姓名或昵称）
    display_name: str = Field(default="", max_length=50)

    # === 凭证 ===
    # bcrypt 哈希，永不存明文 —— bcrypt 自带 salt
    password_hash: str = Field(max_length=255)

    # 首次登录是否强制改密（管理员分发初始密码后置 True）
    must_change_password: bool = Field(default=True)

    # 账号是否启用（软删除开关）
    is_active: bool = Field(default=True)

    # === 元信息 ===
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_login_at: Optional[datetime] = Field(default=None)


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


class Session_(SQLModel, table=True):
    """登录会话

    为什么用服务端 Session 而不是无状态签名 token：
    - **能立即踢下线** —— 删一行记录即失效。备案要写「可单独停用及封禁特定账号」，
      无状态 token 做不到（封号后旧 token 还能用到过期）。
    - 服务重启不丢登录态。
    - 审计可查（谁在什么时间、从哪台设备登过）。
    """

    __tablename__ = "sessions"

    id: Optional[int] = Field(default=None, primary_key=True)

    # 哪个用户的会话
    user_id: int = Field(foreign_key="users.id", index=True, nullable=False)

    # token 的哈希（**不存明文 token** —— 库被拖走也拿不到可用凭证）
    # 校验时对传入的 token 做同样的哈希再比对
    token_hash: str = Field(index=True, unique=True, max_length=64)

    # 会话过期时间
    expires_at: datetime = Field(index=True)

    # 最后一次使用时间（用于「长期未活动自动失效」）
    last_used_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # 创建时间
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # 登录来源 IP（审计用，可空）
    ip: str = Field(default="", max_length=45)

    # 客户端 UA（审计用，可空）
    user_agent: str = Field(default="", max_length=300)


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
