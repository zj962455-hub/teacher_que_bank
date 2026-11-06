#!/usr/bin/env python3
"""线上接口体积/耗时探针（课 33 验收用）"""
import json
import time
import urllib.request

BASE = "https://tqb.lanhu-lab.top"
USER, PASSWORD = "test1", "abc123"


def post(path, payload, token=None):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def get(path, token=None):
    req = urllib.request.Request(BASE + path)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=60) as r:
        body = r.read()
    return body, (time.perf_counter() - t0) * 1000, r.status


def main():
    token = post("/api/auth/login", {"username": USER, "password": PASSWORD})["token"]
    print("=== 线上接口（课 33 验收）===")
    for path, label in (
        ("/api/questions/?limit=50", "题目列表（50 条）"),
        ("/api/papers/", "试卷列表"),
        ("/api/categories/", "分类树"),
        ("/api/categories/flat", "分类扁平"),
        ("/api/auth/stats", "统计"),
        ("/api/questions/recent", "最近编辑"),
    ):
        body, ms, code = get(path, token)
        print(f"  {label:20s} {code}  {len(body)/1024:8.1f} KB  {ms:6.1f} ms")

    body, ms, code = get("/api/questions/?limit=50", token)
    d = json.loads(body)
    print(f"\n  列表 items={len(d['items'])} total={d['total']}")
    print(f"  item 字段: {sorted(d['items'][0].keys())}")
    print(f"  含 blocks: {'blocks' in d['items'][0]}  (应该是 False)")
    print(f"  详情接口含 blocks: {'blocks' in json.loads(get('/api/questions/%s' % d['items'][0]['id'], token)[0])}  (应该是 True)")


if __name__ == "__main__":
    main()
