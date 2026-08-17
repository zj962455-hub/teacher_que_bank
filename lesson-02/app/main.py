# from fastapi import FastAPI
# from app.routers import lessons, questions


# app = FastAPI(
#     title="教师题库 API",
#     description="教培数学老师的私人题库 - 后端 API",
#     version="0.1.0",
# )

# # 注册路由组
# app.include_router(lessons.router, prefix="/api")
# app.include_router(questions.router, prefix="/api")


# @app.get("/")
# def root():
#     return {
#         "message": "教师题库 API",
#         "docs": "/docs",
#         "version": "0.1.0",
#     }
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import lessons, courses

app = FastAPI(
    title="教师题库 API",
    description="教培数学老师的私人题库 - 后端 API",
    version="0.1.0",
)

# === lesson-04 新增:CORS 中间件(允许 Vite 5173 访问) ===
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],   # Vite 默认端口
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由组
app.include_router(lessons.router, prefix="/api")
app.include_router(courses.router, prefix="/api")


@app.get("/")
def root():
    return {
        "message": "教师题库 API",
        "docs": "/docs",
        "version": "0.1.0",
    }