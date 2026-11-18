"""
安全域 —— 操作审计日志

为什么要这张表
--------------
nginx 的 access.log 记的是「哪个 IP 访问了哪个 URL」，**但不知道访问的是哪个登录用户** ——
同一个出口 IP 后面可能有很多人。而安全评估要求的字段是记在一起、能按账号检索的：

    用户账号 + 操作时间 + 操作类型 + 网络源地址和目标地址 + 网络源端口 + 客户端硬件特征

所以应用层自己记一份：token 解析出的 user_id + 请求本身的元信息。
读操作 nginx 那边也有，但**审计以这张表为准**（字段齐全、可按账号检索、可导出）。

字段对照
--------
- user_id / username   → 用户账号
- created_at          → 操作时间
- method / path / action → 操作类型
- client_ip           → 网络源地址
- client_port         → 网络源端口
- target_host / target_path → 目标地址
- user_agent          → 客户端软硬件特征
- status_code / duration_ms → 结果与耗时
"""

from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


class AuditLog(SQLModel, table=True):
    """操作审计日志（一条 = 一次 API 操作）"""

    __tablename__ = "audit_logs"

    id: Optional[int] = Field(default=None, primary_key=True)

    # === 用户账号 ===
    # 未登录的请求（登录接口、注册接口、非法访问）user_id 为空，
    # 但**照样记** —— 未认证的访问尝试本身就是审计要看的东西。
    user_id: Optional[int] = Field(default=None, index=True)
    username: str = Field(default="", max_length=50)

    # === 操作时间 ===
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), index=True
    )

    # === 操作类型 ===
    method: str = Field(default="", max_length=10)
    path: str = Field(default="", max_length=300)
    action: str = Field(default="", max_length=300)

    # === 网络源地址 / 源端口 ===
    client_ip: str = Field(default="", max_length=45, index=True)
    client_port: str = Field(default="", max_length=10)

    # === 目标地址 ===
    target_host: str = Field(default="", max_length=120)
    target_path: str = Field(default="", max_length=300)

    # === 客户端硬件特征 ===
    user_agent: str = Field(default="", max_length=300)

    # === 结果 ===
    status_code: int = Field(default=0)
    duration_ms: int = Field(default=0)
