"""性能基线探针：量接口耗时 + SQL 条数（课 33）

用法：cd lesson-02 && ./venv/bin/python scripts/bench_perf.py
"""
import json, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import event, text
from sqlmodel import Session, select
from app.database import engine
from app.models import User, Question, Paper, PaperQuestion, Upload
from app.scripts.create_users import hash_password

queries = []


@event.listens_for(engine, "before_cursor_execute")
def _before(conn, cursor, statement, params, context, executemany):
    queries.append(statement)


PASSWORD = "abc123456"
N_QUESTIONS = 200
N_PAPERS = 8
PER_PAPER = 25


def cleanup(s):
    uid = s.exec(select(User).where(User.username == "perfprobe")).first()
    if not uid:
        return
    for sql in (
        "DELETE FROM paper_questions WHERE question_id IN (SELECT id FROM questions WHERE user_id=:u)",
        "DELETE FROM paper_questions WHERE paper_id IN (SELECT id FROM papers WHERE user_id=:u)",
        "DELETE FROM question_tags WHERE question_id IN (SELECT id FROM questions WHERE user_id=:u)",
        "DELETE FROM questions WHERE user_id=:u",
        "DELETE FROM papers WHERE user_id=:u",
        "DELETE FROM sessions WHERE user_id=:u",
        "DELETE FROM uploads WHERE user_id=:u",
        "DELETE FROM users WHERE id=:u",
    ):
        s.execute(text(sql), {"u": uid.id})
    s.commit()


def seed(s):
    cleanup(s)
    u = User(username="perfprobe", display_name="perf", password_hash=hash_password(PASSWORD),
             must_change_password=False, is_active=True)
    s.add(u)
    s.commit()
    s.refresh(u)
    uid = u.id
    qs = []
    for i in range(N_QUESTIONS):
        q = Question(
            user_id=uid, subject="数学", question_type="选择题", grade="高一", difficulty="简单",
            content_plain=f"第{i}题 已知等差数列的前 n 项和为 S_n = n^2 + n，求通项公式。",
            content_markdown=f"第{i}题 已知等差数列的前 $n$ 项和为 $S_n = n^2 + n$，求通项公式。",
            # 真实 OCR 数据会有 blocks（每题最多 50 KB）——
            # 列表接口如果把 blocks 一起吐出来，响应会暴涨
            blocks_json=json.dumps(
                [{"type": "text", "text": f"第{i}题题干", "bbox": [10, 20, 300, 60]}] * 40,
                ensure_ascii=False,
            ),
        )
        s.add(q)
        qs.append(q)
    s.commit()
    for q in qs:
        s.refresh(q)
    for p_i in range(N_PAPERS):
        p = Paper(user_id=uid, title=f"卷{p_i}", subtitle="高一")
        s.add(p)
        s.commit()
        s.refresh(p)
        for j in range(PER_PAPER):
            s.add(PaperQuestion(paper_id=p.id, question_id=qs[(p_i * PER_PAPER + j) % N_QUESTIONS].id,
                                order_index=j, label=f"{j + 1}.", score=5.0))
        s.commit()
    return uid


def measure(name, fn):
    queries.clear()
    t0 = time.perf_counter()
    result = fn()
    dt = (time.perf_counter() - t0) * 1000
    size = len(json.dumps(result, ensure_ascii=False).encode()) if result is not None else 0
    extra = f"  响应 {size/1024:8.1f} KB" if size else ""
    print(f"{name:28s} {dt:8.1f} ms  SQL {len(queries):4d} 条{extra}")


def main():
    with Session(engine) as s:
        uid = seed(s)

    with Session(engine) as s:
        from app.routers import papers as P, questions as Q, categories as C

        user = s.exec(select(User).where(User.id == uid)).one()
        pid = s.exec(select(Paper).where(Paper.user_id == uid)).first().id

        def list_papers():
            return P.list_papers(session=s, current_user=user)

        def paper_detail():
            return P._paper_detail(s.get(Paper, pid), s)

        def list_questions():
            return Q.list_questions(session=s, current_user=user, subject=None, question_type=None,
                             grade=None, difficulty=None, keyword=None, category_id=None,
                             tag_ids=None, sort="created_at", order="desc", limit=50, offset=0)

        def cat_tree():
            return C._build_tree(s, user)

        def stats():
            from app.routers import auth as A
            return A.my_stats(session=s, user=user)

        print(f"=== 数据量：{N_QUESTIONS} 题 / {N_PAPERS} 卷 × {PER_PAPER} 题 ===")
        for _ in range(2):
            list_papers(); paper_detail(); list_questions(); cat_tree(); stats()
        measure("GET /api/papers/ (列表)", list_papers)
        measure("GET /api/papers/{id} (详情)", paper_detail)
        measure("GET /api/questions/ (列表)", list_questions)
        measure("GET /api/categories/ (树)", cat_tree)
        measure("GET /api/auth/stats (统计)", stats)

    with Session(engine) as s:
        cleanup(s)
    print("\n（探针数据已清理）")


if __name__ == "__main__":
    main()
