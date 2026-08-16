from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(
    prefix="/questions",
    tags=["题目"],
)


# === Pydantic 模型: 定义"客户端发的 JSON 长啥样" ===
class QuestionIn(BaseModel):
    """客户端创建题目时发的 JSON 格式"""
    stem: str = Field(..., min_length=1, max_length=5000,
                      description="题干")
    question_type: str = Field("SC", pattern="^(SC|FB|CA|SA)$",
                                description="题型: 单选/填空/计算/简答")
    difficulty: int = Field(2, ge=1, le=3, description="难度 1-3")

# === 模拟数据(后期换成数据库) ===
fake_questions = {
    1: {"id": 1, "stem": "1+1=?", "answer": "2"},
    2: {"id": 2, "stem": "sin 30°=?", "answer": "1/2"},
}


# === 列表查询(异步版 - 演示 async/await) ===
# @router.get("/")
# async def list_questions():
#     """异步版 - 假装从数据库读"""
#     await asyncio.sleep(0.1)  # 真实场景会等数据库
#     return {"items": list(fake_questions.values()), "total": len(fake_questions)}

@router.get("/")
def list_questions():
    return {"items": list(fake_questions.values()), "total": len(fake_questions)}


# === 详情查询(带错误处理) ===
@router.get("/{question_id}")
def get_question(question_id: int):
    """找不到就 404, 不让前端瞎猜"""
    q = fake_questions.get(question_id)
    if not q:
        raise HTTPException(
            status_code=404,
            detail=f"题目 ID {question_id} 不存在"
        )
    return q


# === 创建题目(POST + Pydantic 自动校验) ===
@router.post("/", status_code=201)  # 201 Created 是 POST 的标准返回
def create_question(q: QuestionIn):
    """客户端发 JSON, Pydantic 自动校验字段"""
    new_id = max(fake_questions.keys()) + 1
    fake_questions[new_id] = {
        "id": new_id,
        "stem": q.stem,
        "answer": "(待填写)",  # 答案后面再编辑
    }
    return fake_questions[new_id]