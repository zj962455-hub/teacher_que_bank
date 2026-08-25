import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.routers import lessons, courses, upload

app = FastAPI(
    title="教师题库 API",
    description="教培数学老师的私人题库 - 后端 API",
    version="0.2.0",
)

# === CORS 中间件(lesson-04 已加) ===
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === 静态文件挂载(lesson-05 新增) ===
os.makedirs("uploads", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# === 注册路由 ===
app.include_router(lessons.router, prefix="/api")
app.include_router(courses.router, prefix="/api")
app.include_router(upload.router, prefix="/api")


@app.get("/")
def root():
    return {
        "message": "教师题库 API",
        "docs": "/docs",
        "version": "0.2.0",
    }