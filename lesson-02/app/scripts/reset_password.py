#!/usr/bin/env python3
"""重置某个账号的密码（服务器上跑，密码不经过任何聊天记录）

为什么单独一个脚本
------------------
共享试用账号（test2）的密码要定期轮换，但自助改密被禁用了
（``allow_password_change=false`` —— 一个人改密会把全员踢下线）。
管理员改密又走不了自助接口（那也要旧密码）。

所以：**在服务器上直接重置**。密码由管理员自己在终端敲，输一次、输一次确认，
全程不落到聊天记录、不落到 git、不落到命令行历史（用 getpass 读，不带参数传）。

怎么用（服务器上）
------------------
    cd /opt/teacher-bank/app
    sudo -u teacherbank env $(grep -v '^#' /etc/teacherbank/app.env | xargs) \
        python -m app.scripts.reset_password --user test2
    # 交互式：输两遍新密码

非交互（脚本化场景，慎用 —— 密码会进 shell 历史）：
    python -m app.scripts.reset_password --user test2 --password 'xxx'
"""

from __future__ import annotations

import argparse
import getpass
import sys

sys.path.insert(0, ".")

from sqlmodel import Session, select  # noqa: E402

from app.database import engine  # noqa: E402
from app.models import User  # noqa: E402
from app.scripts.create_users import check_password_strength, hash_password  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="重置用户密码")
    ap.add_argument("--user", required=True, help="用户名")
    ap.add_argument("--password", default="", help="新密码（不给则交互式输入，不进历史）")
    ap.add_argument("--force", action="store_true", help="跳过密码强度校验（仅限测试）")
    args = ap.parse_args()

    password = args.password
    if not password:
        password = getpass.getpass("新密码: ")
        again = getpass.getpass("再输一遍: ")
        if password != again:
            print("❌ 两次输入不一致，没改")
            return 1

    if not args.force:
        problems = check_password_strength(password)
        if problems:
            print(f"❌ 密码不合规：{'；'.join(problems)}")
            print("   确认要用弱口令请加 --force")
            return 1

    with Session(engine) as session:
        user = session.exec(select(User).where(User.username == args.user)).first()
        if user is None:
            print(f"❌ 用户 {args.user} 不存在")
            return 1

        user.password_hash = hash_password(password)
        # 重置密码 = 旧 token 全部失效（否则拿到旧 token 的人还能继续用）
        from app.services.auth import revoke_all_sessions

        revoked = revoke_all_sessions(session, user.id or 0)
        session.add(user)
        session.commit()

        print(f"✅ {args.user} 密码已重置（旧会话 {revoked} 个已注销）")
        return 0


if __name__ == "__main__":
    sys.exit(main())
