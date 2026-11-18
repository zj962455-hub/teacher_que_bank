"""邀请码批量生成脚本 — 课 34（灰度试用入口）

给一批老师发试用邀请码时用：在服务器上跑一次，拿到 N 个码，
贴到群里 / 发微信，每人一个。

用法
----
    cd /opt/teacher-bank/app
    /opt/teacher-bank/.venv/bin/python -m app.scripts.generate_invites \
        --count 20 --label "高一数学组" --max-uses 1 --expires-days 30

    # 永不过期、一个码给 5 个人用
    /opt/teacher-bank/.venv/bin/python -m app.scripts.generate_invites \
        --count 3 --label "教研组" --max-uses 5 --expires-days 0

    # 绑定到某个管理员名下（后台列表里能看出是谁发的）
    /opt/teacher-bank/.venv/bin/python -m app.scripts.generate_invites \
        --count 10 --label "秋季试用" --by admin

参数
----
| 参数 | 含义 | 默认 |
|---|---|---|
| --count N | 生成几个码 | 10 |
| --label 名称 | 备注（给谁发的 / 哪个批次）| 空 |
| --max-uses M | 一个码能用几次 | 1 |
| --expires-days D | 多少天后过期（0 = 永不过期）| 30 |
| --by 用户名 | 记在哪个管理员名下 | 不记 |

⚠️ 本脚本只往库里写码，**不改权限**——
   邀请码谁都能注册，但没有管理员身份就不会拿到管理入口。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 让脚本能 import app.*
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.database import engine  # noqa: E402
from app.models import User, create_tables  # noqa: E402
from app.services.invites import (  # noqa: E402
    DEFAULT_EXPIRE_DAYS,
    DEFAULT_MAX_USES,
    MAX_EXPIRE_DAYS,
    MAX_MAX_USES,
    create_invite,
)


def find_user_by_username(username: str) -> User | None:
    """按用户名找用户（找不到返回 None）"""
    from sqlmodel import Session, select

    with Session(engine) as session:
        return session.exec(
            select(User).where(User.username == username)
        ).first()


def main() -> int:
    parser = argparse.ArgumentParser(description="批量生成邀请码")
    parser.add_argument(
        "--count",
        type=int,
        default=10,
        help="生成几个邀请码（默认 10）",
    )
    parser.add_argument(
        "--label",
        default="",
        help="备注：给谁发的 / 哪个批次",
    )
    parser.add_argument(
        "--max-uses",
        type=int,
        default=DEFAULT_MAX_USES,
        help=f"一个码能用几次（默认 {DEFAULT_MAX_USES}，上限 {MAX_MAX_USES}）",
    )
    parser.add_argument(
        "--expires-days",
        type=int,
        default=DEFAULT_EXPIRE_DAYS,
        help=f"多少天后过期（0 = 永不过期，默认 {DEFAULT_EXPIRE_DAYS}，上限 {MAX_EXPIRE_DAYS}）",
    )
    parser.add_argument(
        "--by",
        default="",
        metavar="用户名",
        help="记在哪个管理员名下（可选）",
    )
    args = parser.parse_args()

    if args.count < 1:
        print("❌ --count 至少为 1")
        return 1
    if args.max_uses < 1:
        print("❌ --max-uses 至少为 1")
        return 1
    if args.max_uses > MAX_MAX_USES:
        print(f"❌ --max-uses 最多 {MAX_MAX_USES}")
        return 1
    if args.expires_days < 0:
        print("❌ --expires-days 不能是负数")
        return 1
    if args.expires_days > MAX_EXPIRE_DAYS:
        print(f"❌ --expires-days 最多 {MAX_EXPIRE_DAYS}")
        return 1

    # 建表（invites 表不存在时创建；已有表不加列 —— 加列走 migrations/008）
    create_tables()

    created_by_user_id = None
    if args.by:
        owner = find_user_by_username(args.by)
        if owner is None:
            print(f"❌ 找不到用户：{args.by}")
            return 1
        created_by_user_id = owner.id

    from sqlmodel import Session

    print(f"共生成 {args.count} 个邀请码：")
    print(f"（名额 {args.max_uses} 次 / "
          f"{'永不过期' if args.expires_days == 0 else f'{args.expires_days} 天后过期'}"
          f"{' / 备注：' + args.label if args.label else ''}）\n")

    with Session(engine) as session:
        for _ in range(args.count):
            invite = create_invite(
                session,
                label=args.label,
                max_uses=args.max_uses,
                expires_days=args.expires_days,
                created_by_user_id=created_by_user_id,
            )
            print(f"  {invite.code}")

    print("\n✅ 完成。把这些码发给老师就行 —— 注册页填码即可自助注册。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
