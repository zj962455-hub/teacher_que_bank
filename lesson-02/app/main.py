from fastapi import FastAPI
from app.routers import lessons, questions

app = FastAPI(
    title="教师题库 API",
    description="教培数学老师的私人题库 - 后端 API",
    version="0.1.0",
)

# 注册路由组
app.include_router(lessons.router, prefix="/api")
app.include_router(questions.router, prefix="/api")


@app.get("/")
def root():
    return {
        "message": "教师题库 API",
        "docs": "/docs",
        "version": "0.1.0",
    }