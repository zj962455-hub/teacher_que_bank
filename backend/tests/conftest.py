"""
pytest 全局夹具 — lesson-43

为什么要有这个文件
------------------
之前没有 conftest.py，**测试之间会互相污染**，今天踩到了：

登录失败限流是「同账号 15 分钟内失败 5 次 → 拒绝」。用例
`test_login_wrong_password` 只失败 1 次、期望 401；但本地开发库里
`login_attempts` 从来没人清过，跑过几轮之后同一个手机号累积到 11 次失败
（阈值 5），于是**第一条请求就被限流拦成 429**，用例莫名其妙地挂掉。

⚠️ 症状很像「我刚写的代码有 bug」—— 其实是我反复跑测把脏数据攒出来的。
    所以这类失败要先查数据，别急着改业务代码。

这个夹具做两件事
----------------
1. **每个用例前清空登录流水**（表小，delete 很快）
   —— 用例内自己造的流水不受影响（夹具只在用例**开始前**跑一次）。
2. **确保表结构是最新的**（新增模型后忘了跑迁移的用例不会莫名其妙挂）

为什么不清别的表
----------------
只清「限流用的流水表」。业务数据（题目、试卷、用户）由各用例自己管，
统一清反而会让用例之间的依赖变得不可见。
"""

import sys
from pathlib import Path

import pytest
from sqlmodel import Session, delete

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import engine  # noqa: E402
from app.models import LoginAttempt, create_tables  # noqa: E402


@pytest.fixture(autouse=True)
def _clean_login_attempts():
    """每个用例前清空登录尝试流水 —— 避免跨用例累积把限流提前触发"""
    with Session(engine) as session:
        session.exec(delete(LoginAttempt))
        session.commit()
    yield


@pytest.fixture(scope="session", autouse=True)
def _ensure_schema():
    """整轮测试开始前建一次表（新增模型后忘了跑迁移也不至于整轮挂）"""
    create_tables()
