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
# ⚠️ 必填，不给默认值
# ---------------------------------
# 之前这里写死了 fallback（本地开发的 rrobot@localhost），
# 结果生产环境如果 EnvironmentFile 没生效，就会静默连到错误的库，
# 报错还很难查（"Ident authentication failed for user rrobot"）。
#
# 现在：拿不到就立刻报错，让问题在启动时暴露。
#   - 本地开发：lesson-02/.env 里配 DATABASE_URL
#   - 生产：systemd 的 EnvironmentFile=/etc/teacherbank/app.env
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL 未配置！\n"
        "  本地开发：检查 lesson-02/.env\n"
        "  生产环境：检查 systemd 的 EnvironmentFile=/etc/teacherbank/app.env"
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
