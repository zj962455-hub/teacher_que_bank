"""数据库连接与会话管理 — lesson-08

为什么单独一个文件
------------------
- ``engine`` 全局只应该创建一次（连接池），放模块级
- ``get_session`` 是 FastAPI 的依赖注入入口，路由层用 ``Depends(get_session)`` 拿会话

连接串从环境变量读
------------------
``DATABASE_URL`` 放 .env（不提交 git），格式：
``postgresql+psycopg://用户名:密码@主机:端口/库名``
"""

import os
from collections.abc import Generator

from dotenv import load_dotenv
from sqlalchemy import Engine
from sqlmodel import Session, create_engine

# .env 在 lesson-02/ 下(load_dotenv 默认读 cwd 的 .env)
load_dotenv()

# === 数据库地址 ===
# 本地开发:postgres://rrobot@localhost:5432/teacher_question_bank
# 部署时(lesson-10)改成带密码的完整 URL
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://rrobot@localhost:5432/teacher_question_bank",
)

# === 引擎 ===
# echo=True 会打印所有 SQL(调试用),生产要关
# pool_pre_ping=True 会在取连接前先 ping 一下,避免拿���死连接
engine: Engine = create_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
)


def get_session() -> Generator[Session, None, None]:
    """FastAPI 依赖:每个请求一个数据库会话

    用法:
        @router.get("/")
        def list_questions(session: Session = Depends(get_session)):
            ...
    """
    with Session(engine) as session:
        yield session
