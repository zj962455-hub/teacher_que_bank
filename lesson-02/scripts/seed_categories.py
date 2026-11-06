#!/usr/bin/env python3
"""给共享试用账号预置一套分类树

为什么
----
老师第一次打开「录题」，分类下拉是空的 —— 不知道该选什么，也懒得自己建。
这里预置一套教培数学的常用分类（两级），老师直接选。

怎么用
------
    python scripts/seed_categories.py --user test2 --password 'xxx' \
        --base-url http://127.0.0.1:8000

只创建「不存在」的同级分类 —— 重复跑不会产生重复项。
"""
import argparse
import json
import sys
import urllib.error
import urllib.request

# 一级 → 二级
TREE = [
    ("函数与导数", ["函数概念与性质", "一次函数与二次函数", "指数与对数函数",
                   "幂函数", "函数的单调性与奇偶性", "三角函数", "导数及其应用"]),
    ("数列", ["等差数列", "等比数列", "数列求和", "数列与函数综合"]),
    ("立体几何", ["空间几何体与三视图", "空间点线面位置关系", "空间向量与立体几何证明"]),
    ("解析几何", ["直线与圆", "圆锥曲线", "直线与圆锥曲线的综合"]),
    ("概率与统计", ["随机事件与概率", "离散型随机变量", "统计与数据分析"]),
    ("不等式", ["不等式性质与基本不等式", "一元二次不等式", "均值不等式应用"]),
    ("数与式", ["集合与常用逻辑用语", "实数与数轴", "整式与分式", "因式分解"]),
    ("方程与根", ["方程的解与根的判别式", "函数与方程", "方程应用题"]),
    ("计数原理与概率初步", ["排列组合", "二项式定理", "古典概型"]),
    ("复数", ["复数的概念与运算", "复数的几何意义"]),
    ("综合与应用", ["数学建模入门", "压轴题型专项", "计算题规范与步骤分"]),
]


def request(url, method="GET", token=None, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:200]
        raise SystemExit(f"HTTP {e.code}: {body}")


def fetch_flat(base, token):
    flat = request(f"{base}/api/categories/flat", "GET", token=token)
    return flat.get("items", []) if isinstance(flat, dict) else flat


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--user", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    base = args.base_url.rstrip("/")
    token = request(f"{base}/api/auth/login", "POST",
                    payload={"username": args.user, "password": args.password})["token"]

    items = fetch_flat(base, token)
    existing = {c["name"] for c in items}
    print(f"现有分类 {len(existing)} 个")

    created = 0
    for parent, children in TREE:
        # 一级分类
        pid = next((c["id"] for c in items if c["name"] == parent and not c.get("parent_id")), None)
        if pid is None:
            if args.dry_run:
                print(f"[dry] 建一级分类: {parent}")
                # dry-run 下拿不到真 id —— 用占位符继续往下走，只为看清单
                pid = -1
            else:
                made = request(f"{base}/api/categories/", "POST", token=token,
                               payload={"name": parent})
                pid = made["id"]
                items.append({"id": pid, "name": parent, "parent_id": None})
                existing.add(parent)
                print(f"✅ {parent}")
            created += 1
        else:
            print(f"· {parent}（已存在）")

        have = {c["name"] for c in items if c.get("parent_id") == pid}
        for child in children:
            if child in existing or child in have:
                continue
            if args.dry_run:
                print(f"[dry]   └ {child}")
            else:
                request(f"{base}/api/categories/", "POST", token=token,
                        payload={"name": child, "parent_id": pid})
                print(f"  ✅ {child}")
            created += 1

    print(f"\n共新建 {created} 个分类" + ("（dry-run，未落库）" if args.dry_run else ""))


if __name__ == "__main__":
    sys.exit(main())
