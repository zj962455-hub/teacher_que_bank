from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def read_root():
    return {"message": "Hello from FastAPI"}

@app.get("/api/info")
def get_info():
    return {
        "project": "teacher-question-bank",
        "version": "0.1.0",
        "author": "老大",
        "lesson": "Lesson 01: Hello World",
    }

@app.get("/api/lessons")
def get_lessons():
    return {
        "phase_1": [
            "第 1 课:Hello World",
            "第 2 课:FastAPI 入门",
            "第 3 课:Vue 3 入门",
            # ... 共 10 课
        ]
    }

@app.get("/api/lessons/{lesson_id}")
def get_lesson(lesson_id: int):  # ← 类型注解 int,FastAPI 自动校验
    return {
        "id": lesson_id,
        "title": f"第 {lesson_id} 课",
    }

@app.get("/api/greet")
def greet(name: str = "老大", level: int = 1):
    return {
        "message": f"你好 {name}!",
        "level": level,
        "encouragement": "💪" * level,
    }