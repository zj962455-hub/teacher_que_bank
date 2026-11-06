"""建号脚本 —— lesson-11 用户体系

管理员预创建账号后分发，登录后可自行改密。

用法（在服务器上跑）：
    cd /opt/teacher-bank/app
    /opt/teacher-bank/.venv/bin/python -m app.scripts.create_users

或一次性建号：
    /opt/teacher-bank/.venv/bin/python -m app.scripts.create_users \
        --user test1:测试账号一:abc123 --user test2:测试账号二:abc123

⚠️ 密码强度：大写 + 小写 + 数字 + ≥8 位。
   「abc123」这种**过不了强度校验** —— 建号时强制，
   避免弱口令进系统（备案表要写「口令采用不可逆哈希加盐存储」，
   弱口令会让这句话变成空话）。
   管理员要建的初始密码必须是强口令，或者用 --force 跳过（仅限测试）。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# 让脚本能 import app.*
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.database import engine  # noqa: E402
from app.models import User, create_tables  # noqa: E402


# ============ 密码强度 ============

# 大写 + 小写 + 数字，各至少 1 个，总长 ≥8
_PASSWORD_RULES = (
    (re.compile(r"[a-z]"), "至少一个小写字母"),
    (re.compile(r"[A-Z]"), "至少一个大写字母"),
    (re.compile(r"\d"), "至少一个数字"),
)


def check_password_strength(password: str) -> list[str]:
    """返回密码不合规的原因列表，空列表 = 通过

    规则：大小写字母 + 数字 + 至少 8 位。
    不强制特殊符号 —— 老师容易忘，强度已经够了。
    """
    problems: list[str] = []

    if len(password) < 8:
        problems.append(f"长度不足 8 位（当前 {len(password)} 位）")

    for pattern, message in _PASSWORD_RULES:
        if not pattern.search(password):
            problems.append(message)

    return problems


# ============ 密码哈希 ============

def hash_password(password: str) -> str:
    """bcrypt 哈希（自带 salt）

    bcrypt 有 72 字节上限，超长会被静默截断 —— 这里先截断，
    避免「密码前 72 字节相同但后面不同」的碰撞。
    """
    import bcrypt

    # bcrypt 只看前 72 字节，显式截断让行为可预期
    raw = password.encode("utf-8")[:72]
    return bcrypt.hashpw(raw, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """校验密码"""
    import bcrypt

    raw = password.encode("utf-8")[:72]
    try:
        return bcrypt.checkpw(raw, password_hash.encode("utf-8"))
    except ValueError:
        # 哈希格式不对（库里存了脏数据）—— 不当成密码错误，抛出去更好排查
        raise


# ============ 建号 ============

def create_user(
    username: str,
    display_name: str,
    password: str,
    *,
    must_change_password: bool = True,
    is_admin: bool = False,
    allow_password_change: bool = True,
    force: bool = False,
) -> User:
    """创建一个用户；用户名已存在则抛错

    ``allow_password_change=False`` → 共享试用账号：
    几个人共用一个账号时，**任何一个人改密都会把全员踢下线**
    （改密会 revoke_all_sessions），所以这类账号禁掉自助改密。
    """
    from sqlmodel import Session, select

    if not force:
        problems = check_password_strength(password)
        if problems:
            raise ValueError(
                f"密码不合规（{'；'.join(problems)}）。"
                f"确认要用弱口令请加 --force（仅限测试）"
            )

    with Session(engine) as session:
        existing = session.exec(
            select(User).where(User.username == username)
        ).first()
        if existing:
            raise ValueError(f"用户 {username} 已存在（id={existing.id}）")

        user = User(
            username=username,
            display_name=display_name,
            password_hash=hash_password(password),
            must_change_password=must_change_password,
            is_active=True,
            is_admin=is_admin,
            allow_password_change=allow_password_change,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return user


def main() -> int:
    parser = argparse.ArgumentParser(description="创建用户账户")
    parser.add_argument(
        "--user",
        action="append",
        default=[],
        metavar="用户名:显示名:密码",
        help="可重复。例：--user test1:测试账号一:Abc12345",
    )
    parser.add_argument(
        "--no-force-change",
        action="store_true",
        help="不标记为「首次登录强制改密」（测试账号用）",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="跳过密码强度校验（仅限测试）",
    )
    parser.add_argument(
        "--admin",
        action="store_true",
        help="建的是**管理员**账号（课 34：能管邀请码 + 处理反馈）",
    )
    parser.add_argument(
        "--lock-password-change",
        action="store_true",
        help=(
            "禁止自助改密码（**共享试用账号必开**）—— "
            "几个人共用一个账号时，一人改密会把全员踢下线"
        ),
    )
    args = parser.parse_args()

    # 建表（users 表不存在时创建；已有表不加列 —— 加列走 migrations/001）
    create_tables()

    if not args.user:
        # 默认建两个测试账号
        specs = [
            ("test1", "测试账号一", "abc123"),
            ("test2", "测试账号二", "abc123"),
        ]
    else:
        specs = []
        for raw in args.user:
            parts = raw.split(":")
            if len(parts) != 3:
                print(f"❌ 格式错误：{raw}（应为 用户名:显示名:密码）")
                return 1
            specs.append((parts[0], parts[1], parts[2]))

    print(f"共 {len(specs)} 个账号待创建：\n")
    for username, display_name, password in specs:
        try:
            user = create_user(
                username,
                display_name,
                password,
                must_change_password=not args.no_force_change,
                is_admin=args.admin,
                allow_password_change=not args.lock_password_change,
                force=args.force,
            )
            print(
                f"✅ {username} ({display_name}) id={user.id} "
                f"强制改密={'否' if args.no_force_change else '是'} "
                f"管理员={'是' if args.admin else '否'} "
                f"可改密码={'否' if args.lock_password_change else '是'}"
            )
        except ValueError as e:
            print(f"❌ {username}: {e}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
