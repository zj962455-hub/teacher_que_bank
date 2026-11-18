"""数据模型 —— 按业务域拆分

原来是一个 639 行的 models.py，把四个互不相干的业务域揉在一起：
账号（用户/会话/短信）、题库（题目/分类/标签/上传）、试卷（试卷/分享）、反馈。
现在拆成四个模块，各管各的域：

- account.py   账号域：用户、会话、短信验证码、邀请码
- question.py  题库域：分类、题目、标签、上传图片
- paper.py     试卷域：试卷、试卷题目、分享链接
- feedback.py  反馈域：老师反馈

⚠️ **对外接口没变**：所有 from app.models import User 这类写法照旧能用 ——
本文件把各域的模型统一再导出一次。改代码时按域找文件，但不用改任何 import。

建表用 create_tables()（见本文件末尾）。
"""

from sqlmodel import SQLModel

from .account import Invite, Session_, SmsAttempt, User
from .feedback import Feedback
from .paper import CN_NUMBERS, Paper, PaperQuestion, PaperShare, auto_label
from .question import Category, Question, QuestionTag, Tag, Upload

__all__ = [
    # 账号域
    "User",
    "Session_",
    "SmsAttempt",
    "Invite",
    # 题库域
    "Category",
    "Question",
    "Tag",
    "QuestionTag",
    "Upload",
    # 试卷域
    "Paper",
    "PaperQuestion",
    "PaperShare",
    "auto_label",
    "CN_NUMBERS",
    # 反馈域
    "Feedback",
    # 建表
    "create_tables",
]


# === 建表 ===
def create_tables() -> None:
    """建所有表（如果不存在）

    MVP 用这个而不是 Alembic —— lesson-08 是学 SQLModel，不是学迁移工具。
    lesson-10 部署上线时再补 Alembic（那时表结构可能已经改过几轮了）。
    """
    from app.database import engine

    SQLModel.metadata.create_all(engine)
    print("✅ 数据表已创建/确认")
