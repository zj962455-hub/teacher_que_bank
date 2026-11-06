#!/usr/bin/env python3
"""反馈周报 —— 把「老师试用期间提了什么」汇总成一份能直接看的 markdown

为什么单独一个脚本
------------------
老大要的是「用了一段时间后，给到反馈结果怎么样」。
反馈表里躺着原始记录，人得一条条翻。这个脚本把它变成一张表 + 分组明细。

怎么跑（服务器上，DATABASE_URL 在 /etc/teacherbank/app.env 里）
----------------------------------------------------------
    cd /opt/teacher-bank/app
    sudo -u teacherbank env $(grep -v '^#' /etc/teacherbank/app.env | xargs) \
        python scripts/feedback_digest.py --since-days 7

输出：一段 markdown（直接贴进 QQ/微信就能给老大看）
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

# 与后端 app/routers/feedback.py 的标签保持一致
CATEGORY_LABELS = {"bug": "功能异常", "feature": "功能建议", "other": "其它"}
STATUS_LABELS = {"new": "待处理", "read": "已读", "resolved": "已处理"}


def load_models():
    """延迟导入 —— 依赖 DATABASE_URL，导入失败时给一句人话而不是一堆栈"""
    try:
        from sqlmodel import Session, select
        from app.database import engine
        from app.models import Feedback, User
    except Exception as e:  # noqa: BLE001
        print(f"❌ 导入失败：{e}", file=sys.stderr)
        print("   提示：需要 DATABASE_URL 环境变量", file=sys.stderr)
        sys.exit(1)
    return Session, select, engine, Feedback, User


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since-days", type=int, default=7, help="统计最近 N 天（默认 7）")
    ap.add_argument("--include-resolved", action="store_true",
                    help="默认不列已处理的反馈（周报只看还没处理的）")
    ap.add_argument("--out", default="", help="写到文件（默认打印到 stdout）")
    args = ap.parse_args()

    Session, select, engine, Feedback, User = load_models()

    since = datetime.now(timezone.utc) - timedelta(days=args.since_days)

    with Session(engine) as session:
        feedbacks = session.exec(
            select(Feedback).where(Feedback.created_at >= since)
        ).all()
        if not args.include_resolved:
            feedbacks = [f for f in feedbacks if f.status != "resolved"]

        users = {u.id: u for u in session.exec(select(User)).all()}

    total = len(feedbacks)
    by_cat = Counter(f.category for f in feedbacks)
    by_status = Counter(f.status for f in feedbacks)

    # 按提交人聚合（共享账号下 reporter 才是区分人的关键）
    by_person = defaultdict(list)
    for f in feedbacks:
        author = users.get(f.user_id)
        key = (f.reporter or "").strip() or (author.display_name if author else "") or \
              (author.username if author else f"用户{f.user_id}")
        by_person[key].append(f)

    lines = []
    lines.append(f"## 题库试用反馈 · 最近 {args.since_days} 天")
    lines.append("")
    lines.append(f"- 反馈总数：**{total}** 条")
    lines.append(f"- 待处理：**{by_status.get('new', 0)}** · "
                 f"已读：**{by_status.get('read', 0)}** · "
                 f"已处理：**{by_status.get('resolved', 0)}**")
    cats = " · ".join(
        f"{CATEGORY_LABELS.get(c, c)} {n}" for c, n in by_cat.most_common()
    )
    lines.append(f"- 类别分布：{cats or '—'}")
    lines.append(f"- 参与人数：**{len(by_person)}**")
    lines.append("")

    if not feedbacks:
        lines.append("> 这段时间没有新反馈。")
    else:
        for person, items in sorted(by_person.items(),
                                    key=lambda kv: -len(kv[1])):
            lines.append(f"### {person}（{len(items)} 条）")
            lines.append("")
            for f in sorted(items, key=lambda x: x.created_at):
                ts = f.created_at.astimezone(timezone.utc).astimezone().strftime("%m-%d %H:%M")
                lines.append(f"- **{CATEGORY_LABELS.get(f.category, f.category)}** "
                             f"[{STATUS_LABELS.get(f.status, f.status)}] {ts}")
                lines.append(f"  > {f.content}")
                if f.page_url:
                    lines.append(f"  > 页面：`{f.page_url}`")
                author = users.get(f.user_id)
                if author and (f.contact or "").strip():
                    lines.append(f"  > 联系方式：{f.contact.strip()}")
            lines.append("")

    text = "\n".join(lines)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text)
        print(f"已写入 {args.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
