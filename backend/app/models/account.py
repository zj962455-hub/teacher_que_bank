"""account

账号域 —— 用户、会话、短信验证码、邀请码。

这一域管的是「谁在用这个系统」：身份、凭证、登录态、注册通道。
与题库/试卷没有数据关系，只靠 user_id 外键单向依赖。
"""

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import Column, ForeignKey, Integer
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

    # 手机号（lesson-39 · 短信注册后，这就是登录账号）
    #
    # 为什么单独一列而不复用 username
    # -------------------------------
    # username 是历史遗留的登录名（"test1"、共享试用账号、早期老师的昵称），
    # 改它等于改账号身份，审计和历史记录全都对不上。
    # 手机号是新账号体系的真账号 —— 短信验证码证明「这个号是你的」，
    # 所以它必须是**独立的一列**，而不是 username 的别名。
    #
    # 存量账号这一列是 NULL（他们继续用 username 登录，不受影响）。
    # 唯一性由迁移里的部分唯一索引保证（WHERE phone IS NOT NULL）。
    phone: Optional[str] = Field(default=None, index=True, max_length=20)

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

class SmsAttempt(SQLModel, table=True):
    """短信验证码的发送/核验流水 — lesson-39

    为什么要有这张表
    ----------------
    1. **频控**：全项目没有任何限流中间件（services/invites.py 只是靠熵）。
       短信是**按条计费**的（0.06 元/条），不限制 = 被人刷一次就是几十上百块。
    2. **审计**：谁在什么时候给哪个号发了码、IP 是多少 —— 出了骚扰投诉要能查。

    ⚠️ 不存验证码明文
    ----------------
    验证码由**阿里云生成并保管**（TemplateParam 传 ##code##），
    核验走 CheckSmsVerifyCode 现场问阿里云。
    所以库里没有能用的验证码 —— 数据库被拖走也换不来一个号。
    """

    __tablename__ = "sms_attempts"

    id: Optional[int] = Field(default=None, primary_key=True)

    # 目标手机号
    phone: str = Field(index=True, max_length=20)

    # 请求方 IP（限流 + 溯源）
    ip: str = Field(default="", max_length=45)

    # send=发码 / verify=核验
    action: str = Field(default="send", index=True, max_length=10)

    # 验证码用途：register=注册 / reset=重置密码
    # 阿里云那边验证码只认号码不认用途，所以用途隔离只能在我们这边做（见 services/sms.py）
    purpose: str = Field(default="register", index=True, max_length=16)

    # 结果（发码成功 / 核验通过）
    ok: bool = Field(default=False)

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


class LoginAttempt(SQLModel, table=True):
    """登录尝试流水（防撞库 + 审计）

    为什么需要
    ----------
    仓库里一直记着「全项目没有任何限流中间件」—— 短信发码是自己兜的频控，
    但**登录没有**。密码可以无限次试，撞库就���拿别人账号下的个人信息。

    这张表记每一次登录尝试（成功与失败都记），用于：
    - 限流：同 IP / 同账号在时间窗内失败太多 → 拒绝登录
    - 审计：事后能查「谁在什么时候从哪个 IP 试过哪个账号」

    只记结果，不记密码，也不记用户提交的其它内容。
    """

    __tablename__ = "login_attempts"

    id: Optional[int] = Field(default=None, primary_key=True)

    # 提交的登录名（手机号，或历史遗留的用户名）
    account: str = Field(default="", max_length=50, index=True)
    # 来源 IP
    ip: str = Field(default="", max_length=45, index=True)
    # 这次是否成功
    ok: bool = Field(default=False, index=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), index=True
    )
