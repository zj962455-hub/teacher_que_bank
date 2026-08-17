from fastapi import APIRouter,HTTPException

router = APIRouter(
    prefix="/courses",
    tags=["课程进度"],
)

# 模拟"用户学习进度"数据(后期换成数据库)
fake_courses = [
    {"id": 1, "title": "第 1 课:环境搭建 + Hello World", "done": True},
    {"id": 2, "title": "第 2 课:FastAPI 入门", "done": True},
    {"id": 3, "title": "第 3 课:Vue 3 入门", "done": False},
    {"id": 4, "title": "第 4 课:前后端打通", "done": False},
    {"id": 5, "title": "第 5 课:上传图片", "done": False},
]


@router.get("/")
def list_courses():
    """返回课程列表(含完成状态)"""
    return fake_courses

@router.get("/{course_id}")
def get_course(course_id: int):
    """返回单个课程详情"""
    course = next((c for c in fake_courses if c["id"] == course_id), None)
    if course is None:
        raise HTTPException(status_code=404, detail=f"课程 {course_id} 不存在")
    return course