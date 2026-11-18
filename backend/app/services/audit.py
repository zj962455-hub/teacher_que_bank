"""
操作审计 —— 应用层记录（公安备案 · 安全评估）

为什么 nginx 的 access.log 不够
------------------------------
nginx 记的是「哪个 IP 访问了哪个 URL」，**但不知道访问的是哪个登录用户** ——
同一个出口 IP 后面可能有很多人。而安全评估要的字段是记在一起、能按账号检索的：

    用户账号 + 操作时间 + 操作类型 + 网络源地址和目标地址 + 网络源端口 + 客户端硬件特征

所以应用层自己记一份：token 解析出的 user_id + 请求元信息 → audit_logs 表。

客户端地址怎么取（别踩代理的坑）
--------------------------------
应用跑在 nginx 后面，直接用 ``request.client.host`` 拿到的是 **127.0.0.1**（代理自己），
真实客户端地址在 ``X-Real-IP`` / ``X-Forwarded-For`` 里。
但这两个头**任何人都能伪造** —— 只有直连对端是本机/内网（也就是自家 nginx）时才采信，
否则一律用真实对端地址。
"""

import ipaddress
import logging
import time

from fastapi import Request
from sqlmodel import Session

from app.database import engine
from app.models.audit import AuditLog

logger = logging.getLogger(__name__)

# 只审计 API 路径（静态资源、图标那些不记）
AUDIT_PREFIX = "/api/"

# 路径前缀 → 操作类型（报告里「操作类型」这一栏要能看懂的词）
_ACTION_MAP = [
    ("/api/auth/password/reset", "密码重置"),
    ("/api/auth/register", "账号注册"),
    ("/api/auth/login", "账号登录"),
    ("/api/auth/logout", "会话注销"),
    ("/api/auth/me", "账号信息查询"),
    ("/api/questions", "题目管理"),
    ("/api/papers", "试卷管理"),
    ("/api/shares", "分享链接管理"),
    ("/api/uploads", "文件上传"),
    ("/api/ocr", "录题识别"),
    ("/api/categories", "分类管理"),
    ("/api/tags", "标签管理"),
    ("/api/feedback", "反馈管理"),
    ("/api/invites", "邀请码管理"),
    # lesson-42 · 合规与监管配合（审计导出、调阅台账登记）
    ("/api/compliance", "合规与监管配合"),
]


def resolve_action(path: str) -> str:
    """把接口路径归一成「操作类型」"""
    for prefix, name in _ACTION_MAP:
        if path.startswith(prefix):
            return name
    return "其他操作"


def client_ip_and_port(request: Request) -> tuple[str, str]:
    """取（网络源地址, 网络源端口）

    为什么不信 request.client
    ----------------------------
    uvicorn 开了 --proxy-headers，会用 X-Forwarded-For 改写 scope["client"] ——
    改写后 request.client.host 已经是**客户端的公网 IP**（不再是 nginx 的 127.0.0.1），
    端口被置成 0（falsy）。

    所以「对端是不是内网 → 才采信代理头」这种判断会**全部误判成不可信**，
    结果连自家 nginx 发来的头都不读，源端口永远记不上（2026-11-18 实测踩到）。

    改看**头在不在**
    ----------------
    X-Real-IP 只有我们的 nginx 会发 —— 它用
    proxy_set_header X-Real-IP $remote_addr; **覆盖**客户端送来的同名头，
    客户端伪造不了；而后端只监听 127.0.0.1，外部根本进不来。
    所以「有这个头」= 「一定经过了我们的 nginx」，据此采信源地址与源端口。

    ⚠️ 这两个头都依赖 nginx 侧配置：
       proxy_set_header X-Real-IP $remote_addr;
       proxy_set_header X-Client-Port $remote_port;
    """
    x_real_ip = request.headers.get("x-real-ip", "").strip()
    x_client_port = request.headers.get("x-client-port", "").strip()
    peer = request.client.host if request.client else ""
    peer_port = (
        str(request.client.port) if request.client and request.client.port else ""
    )

    if x_real_ip:
        # 经过我们的 nginx —— 采信它发来的源地址与源端口
        return x_real_ip[:45], (x_client_port or peer_port)[:10]

    # 直连（本地调试 / 测试）—— 用真实对端
    return peer[:45], peer_port[:10]

def record_audit(
    request: Request,
    *,
    user_id: int | None,
    username: str,
    status_code: int,
    duration_ms: int,
    client_ip: str,
    client_port: str,
) -> None:
    """写一条审计记录。写失败不能影响业务请求，所以整体吞异常。"""
    path = request.url.path
    try:
        with Session(engine) as session:
            session.add(
                AuditLog(
                    user_id=user_id,
                    username=username[:50],
                    method=request.method,
                    path=path[:300],
                    action=resolve_action(path),
                    client_ip=client_ip,
                    client_port=client_port,
                    target_host=request.headers.get("host", "")[:120],
                    target_path=path[:300],
                    user_agent=request.headers.get("user-agent", "")[:300],
                    status_code=status_code,
                    duration_ms=duration_ms,
                )
            )
            session.commit()
    except Exception:  # 审计写失败不影响主流程
        logger.exception("审计日志写入失败 path=%s", path)


async def audit_middleware(request: Request, call_next):
    """操作审计中间件 —— 记录每一次 API 操作"""
    if not request.url.path.startswith(AUDIT_PREFIX):
        return await call_next(request)

    started = time.perf_counter()
    client_ip, client_port = client_ip_and_port(request)
    response = await call_next(request)
    duration_ms = int((time.perf_counter() - started) * 1000)

    record_audit(
        request,
        user_id=getattr(request.state, "user_id", None),
        username=getattr(request.state, "username", "") or "",
        status_code=response.status_code,
        duration_ms=duration_ms,
        client_ip=client_ip,
        client_port=client_port,
    )
    return response
