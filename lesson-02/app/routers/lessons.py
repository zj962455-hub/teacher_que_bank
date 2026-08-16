from fastapi import APIRouter

router = APIRouter(
    prefix="/lessons",          # 这组路由统一前缀
    tags=["课程"],              # /docs 里分组显示用
)

# 完整路径: GET /api/lessons/
@router.get("/")
def list_lessons():
    return {
        "phase_1": [
            "第 1 课:Hello World",
            "第 2 课:FastAPI 进阶",
            "第 3 课:Vue 3 入门",
        ]
    }

# 完整路径: GET /api/lessons/{lesson_id}
@router.get("/{lesson_id}")
def get_lesson(lesson_id: int):
    return {
        "id": lesson_id,
        "title": f"第 {lesson_id} 课",
    }