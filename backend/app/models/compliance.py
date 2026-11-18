"""
合规域 —— 面向监管与执法部门的数据调阅台账

为什么要有这张表
----------------
安全评估要求「建立为监管部门和执法部门依法履职提供技术、数据支持和协助的工作机制」。

「机制」不能只是一句承诺，得**留痕** —— 否则出了事说不清「什么时候配合了什么」。
这张表记录每一次向监管/执法部门提供数据或协助的情况：
谁要的、依据什么文书、要什么、给了什么、什么时候给的、有没有回执。

只记**调阅这件事本身**，不记被调阅的业务内容。
"""

from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


class RegulatoryRequest(SQLModel, table=True):
    """监管/执法调阅与协助台账（一条 = 一次）"""

    __tablename__ = "regulatory_requests"

    id: Optional[int] = Field(default=None, primary_key=True)

    # === 谁要的 ===
    # 请求单位：公安机关网安部门 / 市场监管 / 教育主管部门 等
    authority: str = Field(default="", max_length=100, index=True)
    # 请求人：姓名 + 警号或证件号后四位（不留完整证件号）
    requester: str = Field(default="", max_length=100)

    # === 依据 ===
    # 法律依据 + 文书编号（责令改正通知书 / 查询函 / 调取证据通知书 等）
    basis: str = Field(default="", max_length=300)

    # === 要什么 / 给了什么 ===
    # 请求的数据范围（账号、时间段、IP、接口路径等）
    scope: str = Field(default="", max_length=500)
    # 实际提供的内容摘要（导出了哪些表、多少条、什么格式）
    data_provided: str = Field(default="", max_length=500)
    # 提供方式：平台导出 / 当面提供 / 邮件 / 邮寄
    channel: str = Field(default="平台导出", max_length=50)

    # === 什么时候 / 谁给的 ===
    provided_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), index=True
    )
    provided_by: str = Field(default="", max_length=50)

    # === 回执 ===
    # 对方给的回执/凭证编号 —— 双向留痕
    receipt_no: str = Field(default="", max_length=100)

    notes: str = Field(default="", max_length=500)

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
