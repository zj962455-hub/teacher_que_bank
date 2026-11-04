"""真实导出 PDF,检查页脚溯源串 —— 脚本

跑法（本地）：
    cd lesson-02
    venv/bin/python scripts/verify_pdf_trace.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlmodel import Session, select, text  # noqa: E402

from app.database import engine  # noqa: E402
from app.models import Paper, PaperQuestion, Question, User  # noqa: E402
from app.routers.papers import _build_trace  # noqa: E402
from app.scripts.create_users import hash_password  # noqa: E402
from app.services.pdf_export import export_paper_pdf  # noqa: E402


def main() -> int:
    # 清理
    with Session(engine) as s:
        # ⚠️ 显式 SQL 顺序删（外键依赖顺序）
        for sql in (
            "DELETE FROM sessions",
            "DELETE FROM uploads",
            "DELETE FROM paper_questions",
            "DELETE FROM papers",
            "DELETE FROM questions",
            "DELETE FROM users",
        ):
            s.exec(text(sql))
        s.commit()

    # 建用户 + 卷
    with Session(engine) as s:
        user = User(
            username="trace_demo",
            display_name="张老师",
            password_hash=hash_password("Abc12345"),
            must_change_password=False,
            is_active=True,
        )
        s.add(user)
        s.commit()
        s.refresh(user)
        uid = user.id or 0

        q = Question(
            user_id=uid,
            content_plain="已知 f(x)=x²+2x+1，求 f(2) 的值",
            content_markdown="已知 $f(x)=x^2+2x+1$，求 $f(2)$ 的值",
            subject="数学",
        )
        s.add(q)
        s.commit()
        s.refresh(q)

        p = Paper(user_id=uid, title="高一数学第一单元测试", subtitle="2026 秋季")
        s.add(p)
        s.commit()
        s.refresh(p)

        s.add(PaperQuestion(paper_id=p.id, question_id=q.id, order_index=0, label="一、", score=5.0))
        s.commit()
        # ⚠️ session 关闭后不能再访问 ORM 属性 —— 这里把要用的字段取成普通值
        paper_title = p.title
        paper_subtitle = p.subtitle
        paper_id = p.id or 0

    # 溯源串
    with Session(engine) as s:
        u = s.exec(select(User).where(User.username == "trace_demo")).first()
        trace = _build_trace(u, Paper(user_id=u.id or 0, title=paper_title, subtitle=paper_subtitle))
    print(f"溯源串: {trace}")

    # 导出 PDF
    items = [{"label": "一、", "content": "已知 $f(x)=x^2+2x+1$，求 $f(2)$ 的值", "score": 5.0}]
    pdf = export_paper_pdf(
        paper={"title": paper_title, "subtitle": paper_subtitle},
        items=items,
        trace=trace,
    )
    out = Path("/tmp/trace-demo.pdf")
    out.write_bytes(pdf)
    print(f"PDF 已生成: {out} ({len(pdf)} 字节)")
    print(f"是合法 PDF: {pdf[:4] == b'%PDF'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
