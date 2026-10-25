import os
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# === 必须在 import 其他 app 模块前 load .env ===
# .env 在 lesson-02/ 下(load_dotenv 默认读 cwd 的 .env)
load_dotenv()

from app.routers import lessons, courses, upload, ocr, questions   # ← 加 questions(lesson-08)

# === lesson-08:数据库 ===
from app.database import engine
from app.models import Question, create_tables

app = FastAPI(
    title="教师题库 API",
    description="教培数学老师的私人题库 - 后端 API",
    version="0.3.0",
)

# === CORS + 静态挂载(lesson-04/05 已加) ===
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs("uploads", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# === 注册路由 ===
app.include_router(lessons.router, prefix="/api")
app.include_router(courses.router, prefix="/api")
app.include_router(upload.router, prefix="/api")
app.include_router(ocr.router, prefix="/api")    # ← 新增
app.include_router(questions.router, prefix="/api")   # ← lesson-08 题目 CRUD


@app.get("/")
def root():
    return {
        "message": "教师题库 API",
        "docs": "/docs",
        "version": "0.4.0",     # ← lesson-08 升版本
    }


# === lesson-08:启动时建表 ===
@app.on_event("startup")
def on_startup():
    """启动时确保表存在

    MVP 用 create_all 而不是 Alembic —— lesson-08 是学 SQLModel。
    lesson-10 部署上线时再补 Alembic(那时表结构可能改过几轮)。
    """
    create_tables()