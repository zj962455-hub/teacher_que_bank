"""统一错误契约 — lesson-32

问题：三个异常出口各写各的，返回体形状不一样
------------------------------------------------
| 出口 | 旧返回体 | 毛病 |
|---|---|---|
| 未捕获异常 | ``{"detail": "服务器内部错误", "request_id": "..."}`` | 只有 500 有 request_id |
| 参数校验 | ``{"detail": "请求参数有误: xxx"}`` / 开发模式下是**数组** | 前端得判断 detail 是字符串还是数组 |
| HTTPException | ``{"detail": exc.detail}`` | 没有 request_id，出错无法定位 |

前端拿到三种形状，就得写三套解析 —— 而现在的解析是**每个页面各写一遍的
``e.response?.data?.detail || `加载失败：${e.message}` `` ，
漏一处就是一处白屏。

统一契约
--------
**所有**错误出口返回同一个形状：

```json
{
  "detail": "人话说明",
  "code": "stable_machine_code",
  "request_id": "a1b2c3d4e5f6"
}
```

- ``detail`` —— **永远是字符串**（前端可以无条件直接显示）
- ``code`` —— 稳定的机器码，前端可据此做特殊处理（如 ``auth.expired`` 直接跳登录）
- ``request_id`` —— 12 位 hex，**每个错误都有**，
  跟服务端日志里的同一个 id 对得上（``journalctl -u teacherbank-api | grep <id>``）

request_id 从哪来
-----------------
``request_id_middleware`` 给**每个**请求生成一个（入站 header ``X-Request-ID``
已有就沿用，没有就生成），挂在 ``request.state.request_id``。
于是：日志、响应体、响应头 ``X-Request-ID`` 三处是同一个 id ——
老师截图报错时，id 就在界面上，运维直接搜日志。
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

# === 机器码 ===

# 认证 / 权限
CODE_AUTH_REQUIRED = "auth.required"
CODE_AUTH_EXPIRED = "auth.expired"
CODE_FORBIDDEN = "auth.forbidden"

# 资源
CODE_NOT_FOUND = "resource.not_found"
CODE_CONFLICT = "resource.conflict"
CODE_VALIDATION = "request.validation_failed"

# 服务端
CODE_INTERNAL = "server.internal"
CODE_UNAVAILABLE = "server.unavailable"


def new_request_id() -> str:
    """生成 12 位 hex 的请求 id"""
    return uuid.uuid4().hex[:12]


def current_request_id(request: Request) -> str:
    """取当前请求的 id

    拿不到就现场生成一个 —— 宁可给个对不上日志的 id，
    也别让错误响应里没有 id（那才是真没法排查）。
    """
    rid = getattr(request.state, "request_id", None)
    if not rid:
        rid = new_request_id()
        request.state.request_id = rid
    return rid


def error_body(
    detail: str,
    *,
    code: str,
    request_id: str,
    extra: dict | None = None,
) -> dict:
    """构造统一错误体"""
    body = {
        "detail": detail,
        "code": code,
        "request_id": request_id,
    }
    if extra:
        body.update(extra)
    return body


def error_response(
    request: Request,
    *,
    status_code: int,
    detail: str,
    code: str,
    headers: dict | None = None,
    extra: dict | None = None,
) -> JSONResponse:
    """构造统一错误响应

    带上 ``X-Request-ID`` 响应头 —— 浏览器 Network 面板里一眼能对上。
    """
    rid = current_request_id(request)
    resp_headers = dict(headers or {})
    resp_headers["X-Request-ID"] = rid
    return JSONResponse(
        status_code=status_code,
        content=error_body(detail, code=code, request_id=rid, extra=extra),
        headers=resp_headers,
    )


class ApiHTTPException(HTTPException):
    """带机器码的 HTTPException

    为什么不用普通的 ``HTTPException``
    ------------------------------
    普通 HTTPException 只有 ``detail``（一句人话），没有机器码。
    前端要区分「登录失效了要跳登录」和「权限不够要提示」，
    就只能去**猜** detail 里的中文 —— 改个文案就崩。

    带上 ``code`` 之后，前端按 code 分支，文案随便改。

    用法::

        raise ApiHTTPException(
            status_code=401,
            detail="登录已失效，请重新登录",
            code=CODE_AUTH_EXPIRED,
        )
    """

    def __init__(
        self,
        status_code: int,
        detail: str,
        *,
        code: str = "request.failed",
        headers: dict | None = None,
    ):
        super().__init__(status_code=status_code, detail=detail, headers=headers)
        self.code = code
