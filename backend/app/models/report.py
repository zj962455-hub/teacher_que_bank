"""
举报域 —— 违法有害信息举报的受理、处置与反馈

为什么要建这张表
----------------
《网络安全责任告知书》第五条（六）要求：「建立标识、举报制度、公开举报、举报方式等
信息举报渠道的畅通、及时发现并处理相关有害信息的情况」。

原来平台只有页脚两个**外链**（12377、公安网络违法犯罪举报网）—— 那是把用户导去
别处的渠道；平台自己**不受理、不记录、不知道有没有处理**。审核问「举报渠道是否
畅通、有无及时发现并处理」时，只能答「有外链」，答不出闭环。

这张表把闭环补齐：

    举报提交 → 生成受理编号 → 管理员核实 → 处置（删内容 / 吊销链接 / 停账号）
    → 处置结论回填 → 举报人凭编号查结果

只记**举报这件事本身**，不抄被举报内容的正文。
"""

from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


class Report(SQLModel, table=True):
    """一条举报（一条 = 一次举报受理）"""

    __tablename__ = "reports"

    id: Optional[int] = Field(default=None, primary_key=True)

    # === 受理编号 ===
    # 举报人拿这个编号查处理结果 —— 没有编号，举报人无从问起
    report_no: str = Field(index=True, unique=True, max_length=32)

    # === 被举报对象 ===
    # 类型：question / paper / share / upload / user / other
    target_type: str = Field(default="other", max_length=20, index=True)
    target_id: Optional[int] = Field(default=None, index=True)
    # 对象描述（题目标题 / 分享卷名 / 链接片段）——
    # 对象被删掉之后，管理员仍要看得见「当时举报的是什么」
    target_desc: str = Field(default="", max_length=300)

    # === 举报内容 ===
    reason: str = Field(default="other", max_length=30, index=True)
    detail: str = Field(default="", max_length=1000)

    # === 举报人 ===
    # 允许匿名（公开分享页的访客没有账号）→ reporter_user_id 可空
    reporter_user_id: Optional[int] = Field(default=None, index=True)
    reporter_name: str = Field(default="", max_length=50)
    reporter_contact: str = Field(default="", max_length=100)
    source_ip: str = Field(default="", max_length=45, index=True)

    # === 处置状态 ===
    # pending（待受理）→ processing（核实中）→ resolved（已处置）/ rejected（不予受理）
    status: str = Field(default="pending", max_length=20, index=True)
    handle_note: str = Field(default="", max_length=1000)
    handled_by: str = Field(default="", max_length=50)
    handled_at: Optional[datetime] = Field(default=None)
    # 实际执行的处置动作：none / delete_question / revoke_share / disable_account
    dispose_action: str = Field(default="none", max_length=30)

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)
