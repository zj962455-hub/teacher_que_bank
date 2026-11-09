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
from sqlalchemy import Column, ForeignKey, Integer


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

    # 是否管理员（课 34 · 灰度试用入口）
    #
    # ⚠️ 单独一列而不是「角色表」+ 关联：全站只有两种身份，
    #    引入角色表会带来三张表和一堆关联查询，收益为零。
    #    以后真要细分角色（教研/运营）再说。
    is_admin: bool = Field(default=False)

    # 是否允许自助改密码（课 34 · 共享试用账号）
    #
    # ⚠️ 为什么需要这一列
    # ------------------
    # 灰度阶段是「几个老师共用一个账号」—— 改密码会 revoke_all_sessions，
    # **一个人改密 = 所有人被踢下线**（改密的人自己也一起掉线）。
    # 所以共享账号必须把这一列置 false，改密接口直接 403。
    #
    # 注意这是「能不能改」，不是「能不能登录」——
    # 共享账号照常登录、照常录题，只是不能自助改密。
    allow_password_change: bool = Field(default=True)

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


class Invite(SQLModel, table=True):
    """灰度试用邀请码 — 课 34

    干什么用的
    ----------
    之前账号只能由管理员在服务器上手工建号（``create_users.py``），
    老师想试用得等管理员有空。现在给老师发一个邀请码，
    他自己在网页上注册就能进来 —— 灰度试用的入口。

    一次邀请码 = 「谁能注册 + 能注册几个 + 到什么时候」
    | 字段 | 含义 |
    |---|---|
    | code | 邀请码本身（唯一） |
    | max_uses / used_count | 名额：最多能用几次 / 已经用了几次 |
    | expires_at | 过期时间（可空 = 永不过期）|
    | is_active | 停用开关（老师流失了/发错了，一键停）|
    | created_by_user_id | 谁发的（管理员，可空 —— 脚本批量生成时没人）|

    code 为什么明文存
    ----------------
    跟 ``paper_shares.token`` 同一个理由：**要能反复复制分发**。
    管理员要把码贴在群里、发微信、印在通知里；存哈希就永远拿不回原文，
    只能作废重发 —— 那不叫邀请码，叫一次性口令。

    它不是密码级秘密：
    - 6 字节随机（48 位熵），猜不中
    - 名额有限（max_uses），用完即废
    - 可停用（is_active）、可过期（expires_at）
    - 只有管理员看得到（接口层面挡着）
    泄露的最坏后果 = 多注册一个账号，不是「拿到别人的数据」。
    """

    __tablename__ = "invites"

    id: Optional[int] = Field(default=None, primary_key=True)

    # 邀请码（唯一）—— 生成的码是大写带横线的，方便念和抄
    code: str = Field(index=True, unique=True, max_length=32)

    # 备注：给谁发的、哪个批次（管理员自己看）
    label: str = Field(default="", max_length=50)

    # 名额
    max_uses: int = Field(default=1)
    used_count: int = Field(default=0)

    # 过期时间（None = 永不过期）
    expires_at: Optional[datetime] = Field(default=None, index=True)

    # 停用开关
    is_active: bool = Field(default=True, index=True)

    # 谁发的（可空：批量脚本生成时没有具体的人）
    # ⚠️ ON DELETE CASCADE：跟仓库其它外键一致 —— 管理员账号被删，
    #    他发出去的码也一起清掉，不留指向空账号的记录。
    created_by_user_id: Optional[int] = Field(
        sa_column=Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=True)
    )

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


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
