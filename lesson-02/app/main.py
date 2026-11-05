import logging
import os
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

# === 必须在 import 其他 app 模块前 load .env ===
# .env 在 lesson-02/ 下(load_dotenv 默认读 cwd 的 .env)
load_dotenv()

from app.routers import lessons, courses, upload, ocr, questions, papers, auth, categories, tags   # ← 加 tags(lesson-11)
from app.routers import shares  # ← lesson-24 分享链接（管理线 + 公开线）

# === lesson-08:数据库 ===
from app.database import engine
from app.models import Question, create_tables

# === lesson-32:统一错误契约 ===
from app.services.errors import (
    CODE_AUTH_REQUIRED,
    CODE_AUTH_EXPIRED,
    CODE_FORBIDDEN,
    CODE_INTERNAL,
    CODE_VALIDATION,
    ApiHTTPException,
    current_request_id,
    error_response,
    new_request_id,
)

# === 运行环境 ===
# APP_ENV=production 时:关掉 API 文档、不回显内部错误细节。
# 开发时（默认）保持开放,方便看文档。
APP_ENV = os.getenv("APP_ENV", "development").lower()
IS_PROD = APP_ENV == "production"

logger = logging.getLogger("tqb.api")

app = FastAPI(
    title="教师题库 API",
    description="教培数学老师的私人题库 - 后端 API",
    version="0.3.0",
    # ⚠️ 生产环境关掉 /docs /redoc /openapi.json ——
    #    那三个接口把完整 API 结构公开给任何访客。
    #    需要临时排查时:set APP_ENV=development 再重启。
    docs_url=None if IS_PROD else "/docs",
    redoc_url=None if IS_PROD else "/redoc",
    openapi_url=None if IS_PROD else "/openapi.json",
)

# === CORS + 静态挂载(lesson-04/05 已加) ===
# === CORS ===
# 生产环境前端和 API 同源(tqb.lanhu-lab.top),根本不需要跨域 ——
# 同源之外全部拒绝(allow_origins=[])。开发时放开 localhost:5173。
_cors_origins = [] if IS_PROD else ["http://localhost:5173"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs("uploads", exist_ok=True)
# ⚠️ lesson-11:不再静态挂载 /uploads
#   StaticFiles 不认识 token —— 知道 URL 就能下载任何人的图片。
#   改为带鉴权的路由 routers/upload.py:GET /api/uploads/{filename}。
#   nginx 那层也要同步改（见 deploy/teacher-bank/nginx-teacherbank.conf）。

# === lesson-09:KaTeX 静态资源 ===
# PDF 导出时 Chromium 用 file:// 读这些文件(不走 HTTP,避免死锁),
# 但挂到 HTTP 上方便调试时直接在浏览器里看渲染效果。
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

# === 注册路由 ===
app.include_router(lessons.router, prefix="/api")
app.include_router(courses.router, prefix="/api")
app.include_router(upload.router, prefix="/api")
app.include_router(ocr.router, prefix="/api")    # ← 新增
app.include_router(questions.router, prefix="/api")   # ← lesson-08 题目 CRUD
app.include_router(papers.router, prefix="/api")      # ← lesson-09 试卷 + PDF 导出
app.include_router(auth.router, prefix="/api")        # ← lesson-11 认证
app.include_router(categories.router, prefix="/api")  # ← lesson-11 章节分类
app.include_router(tags.router, prefix="/api")        # ← lesson-11 标签
app.include_router(shares.manage_router, prefix="/api")   # ← lesson-24 分享链接（管理线，要登录）
app.include_router(shares.public_router, prefix="/api")   # ← lesson-24 分享链接（公开线，不用登录）


@app.get("/")
def root():
    return {
        "message": "教师题库 API",
        "docs": "/docs",
        "version": "0.5.0",     # ← lesson-09 升版本
    }


# === lesson-08:启动时建表 ===
@app.on_event("startup")
def on_startup():
    """启动时确保表存在

    MVP 用 create_all 而不是 Alembic —— lesson-08 是学 SQLModel。
    lesson-10 部署上线时再补 Alembic(那时表结构可能改过几轮)。
    """
    create_tables()


# ============================================================
# lesson-11 安全收口
# ============================================================

# === 4.1 安全响应头 ===
@app.middleware("http")
async def security_headers(request: Request, call_next):
    """给每个响应加上安全头

    - X-Content-Type-Options: nosniff —— 禁止浏览器猜 MIME 类型
      (防止有人把 .txt 当 HTML 执行)
    - X-Frame-Options: DENY —— 禁止被 iframe 嵌套(点击劫持)
    - Referrer-Policy: strict-origin-when-cross-origin —— 不外泄 URL 参数
    - Permissions-Policy —— 关掉用不到的浏览器能力
    - HSTS —— 生产环境强制 HTTPS(浏览器层面)
    """
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    response.headers["X-XSS-Protection"] = "0"  # 已被 CSP 取代,留着反而误导
    if IS_PROD and request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


# === lesson-32:统一错误契约 ====================================

# === request_id 中间件 ===
@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """给每个请求生成一个 id

    入站已有 ``X-Request-ID`` 就沿用（网关/上游可能已经生成过），
    没有就自己生成一个。挂在 ``request.state.request_id``，
    后面三个异常出口和响应头都用它 —— 三处同一个 id，才能拿界面上的 id 搜日志。
    """
    incoming = request.headers.get("X-Request-ID", "").strip()
    request.state.request_id = incoming[:64] if incoming else new_request_id()
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    return response


# === 4.2 未捕获异常:不外泄细节 ===
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """兜底异常处理

    客户端只拿到:
      {"detail": "服务器内部错误", "code": "server.internal", "request_id": "..."}

    真正的异常类型和堆栈写进日志 —— 运维靠 request_id 去日志里搜。
    """
    request_id = current_request_id(request)
    logger.exception(
        "未处理异常 request_id=%s method=%s path=%s",
        request_id,
        request.method,
        request.url.path,
    )
    return error_response(
        request,
        status_code=500,
        detail="服务器内部错误",
        code=CODE_INTERNAL,
    )


# === 4.3 参数校验错误:不回显内部结构 ===
@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    """参数校验失败

    FastAPI 默认返回 errors() 列表,里面含字段名和类型 ——
    信息量对攻击者有用(能摸清后端要什么字段)。
    生产环境只回一句人话 + 第一个出错字段名,细节进日志。

    ⚠️ lesson-32:开发模式也返回**字符串** detail（旧的开发模式返数组，
    前端拿到的 detail 有时是数组有时是字符串 → 页面直接渲染成空白）。
    想要原始 errors 就看服务端日志。
    """
    detail = "请求参数有误"
    try:
        first = exc.errors()[0]
        loc = [str(x) for x in first.get("loc", []) if x not in ("body", "query", "path")]
        if loc:
            detail = f"请求参数有误: {'.'.join(loc)}"
    except Exception:
        pass

    logger.warning(
        "参数校验失败 request_id=%s method=%s path=%s detail=%s",
        current_request_id(request),
        request.method,
        request.url.path,
        detail,
    )
    return error_response(
        request,
        status_code=422,
        detail=detail,
        code=CODE_VALIDATION,
    )


# === 4.5 带机器码的 HTTPException（lesson-32）===
@app.exception_handler(ApiHTTPException)
async def api_http_exception_handler(request: Request, exc: ApiHTTPException):
    """业务代码主动抛的、带机器码的错误

    必须在 ``StarletteHTTPException`` 的 handler **之前**注册 ——
    FastAPI 按「异常类精确匹配 → MRO 依次找」找 handler，
    ApiHTTPException 是 StarletteHTTPException 的子类，
    精确匹配会先命中它。
    """
    return error_response(
        request,
        status_code=exc.status_code,
        detail=exc.detail,
        code=exc.code,
        headers=getattr(exc, "headers", None),
    )


# === 4.6 HTTPException:只保留 detail 文本 ===
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """HTTPException 默认会带 detail 字段,那是我们自己写的文案,安全。

    但 500 级别的 StarletteHTTPException.detail 有时是英文默认串,
    生产环境统一换成中文,并去掉 headers 里的内部信息。

    ⚠️ lesson-32:401/403 补上机器码 —— 前端可以据此决定「跳登录」还是「提示没权限」。
    """
    request_id = current_request_id(request)

    if IS_PROD and exc.status_code >= 500:
        logger.error(
            "HTTP %s request_id=%s method=%s path=%s detail=%s",
            exc.status_code,
            request_id,
            request.method,
            request.url.path,
            exc.detail,
        )
        return error_response(
            request,
            status_code=exc.status_code,
            detail="服务器内部错误",
            code=CODE_INTERNAL,
        )

    # 401 → 登录相关；403 → 权限相关；其余按状态码归类
    if exc.status_code == 401:
        code = CODE_AUTH_EXPIRED
    elif exc.status_code == 403:
        code = CODE_FORBIDDEN
    else:
        code = CODE_AUTH_REQUIRED if exc.status_code == 400 else "request.failed"

    return error_response(
        request,
        status_code=exc.status_code,
        detail=exc.detail,
        code=code,
        headers=getattr(exc, "headers", None),
    )
