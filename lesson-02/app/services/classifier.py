"""题目自动分类器 — lesson-08（Python 版）

为什么要有 Python 版
------------------
lesson-06 任务 5C 的分类器是前端 JS（``lesson-03/src/utils/classifier.js``）。
lesson-08 需要在后端也能分类：

- ``POST /api/questions/from-ocr/{task_id}`` 一键入库时，
  后端自己从 OCR 结果算分类，不用前端再传一遍
- lesson-09 导出 PDF 时也要用到分类信息

**规则完全一致**（两边同源维护，改规则要同步改两处）。
TODO: lesson-XX 把规则抽成一份（比如 JSON 文件），前后端都读它。

分类维度
--------
| 维度 | 取值 |
|---|---|
| subject | 数学 / 物理 / 化学 / 生物 / 未知 |
| question_type | 选择题 / 填空题 / 计算题 / 证明题 / 应用题 / 未知 |
| grade | 初中 / 高中 / 通用 |
| difficulty | 简单 / 中等 / 困难 |
"""

import json
from typing import Any

# === 学科规则（特征词在前，泛词在后）===
SUBJECT_RULES = [
    {"subject": "物理", "keywords": ["加速度", "电流", "电压", "电阻", "功率", "密度",
                                     "摩擦力", "浮力", "压强", "波长"]},
    {"subject": "化学", "keywords": ["摩尔", "化学式", "溶液", "浓度", "原子", "分子",
                                     "化合价", "电解质"]},
    {"subject": "生物", "keywords": ["细胞", "基因", "遗传", "光合作用", "呼吸作用",
                                     "蛋白质", "染色体"]},
    {"subject": "数学", "keywords": ["方程", "函数", "几何", "三角", "概率", "统计",
                                     "数列", "不等式", "证明", "已知", "求"]},
]

# === 题型规则（特征强的排前面）===
TYPE_RULES = [
    {"type": "选择题", "keywords": ["下列", "正确的是", "错误的是", "不符合", "选项", "以上都对"]},
    {"type": "证明题", "keywords": ["证明", "求证", "证："]},
    {"type": "计算题", "keywords": ["解方程", "解不等式", "化简", "求值", "计算", "求解"]},
    {"type": "填空题", "keywords": ["填空", "横线上", "____", "＿＿", "…"]},
    {"type": "应用题", "keywords": ["某", "一共", "剩下", "平均", "买", "卖出", "走了", "多少"]},
]

# === 学段规则 ===
GRADE_RULES = [
    {"grade": "初中", "keywords": ["一元二次", "勾股", "全等", "相似", "一次函数", "反比例", "圆"]},
    {"grade": "高中", "keywords": ["导数", "数列", "三角函数", "向量", "抛物线", "椭圆",
                                    "双曲线", "排列组合", "概率分布"]},
]


def _first_match(content: str, rules: list[dict], key: str) -> tuple[str, str | None]:
    """返回 (命中值, 命中的关键词)；没命中返回 (fallback, None)"""
    for rule in rules:
        for kw in rule["keywords"]:
            if kw in content:
                return rule[key], kw
    return "", None


def estimate_difficulty(text: str, blocks: list[dict] | None = None) -> str:
    """难度启发式估算

    不是真正的难度评估，只是按文本特征粗判，给老师一个初始值再手动调。
    """
    blocks = blocks or []
    length = len(text)
    formula_count = sum(1 for b in blocks if b.get("type") == "formula")
    table_count = sum(1 for b in blocks if b.get("type") == "table")

    score = 0
    score += min(length / 50, 3)      # 每 50 字加 1 分，上限 3
    score += formula_count * 1.5      # 每个公式 1.5 分
    score += table_count * 2          # 每个表格 2 分

    if score >= 5:
        return "困难"
    if score >= 2.5:
        return "中等"
    return "简单"


def classify(text: str = "", blocks: list[dict] | None = None) -> dict[str, Any]:
    """分类一道题

    Args:
        text: 拼接后的纯文本
        blocks: OCR blocks 数组（可选，用于难度估算）

    Returns:
        {"subject", "type", "grade", "difficulty", "confidence", "matched"}
    """
    content = text or ""
    blocks = blocks or []
    matched: list[str] = []

    # 学科
    subject, kw = _first_match(content, SUBJECT_RULES, "subject")
    if kw:
        matched.append(f"{subject}:{kw}")

    # 题型
    qtype, kw = _first_match(content, TYPE_RULES, "type")
    if kw:
        matched.append(f"{qtype}:{kw}")

    # 学段
    grade, kw = _first_match(content, GRADE_RULES, "grade")
    if kw:
        matched.append(f"{grade}:{kw}")

    # 难度
    difficulty = estimate_difficulty(content, blocks)

    # 置信度:命中维度数 / 3
    hit_count = sum([
        bool(subject),
        bool(qtype),
        bool(grade),
    ])
    confidence = round(hit_count / 3, 2)

    return {
        "subject": subject or "未知",
        "type": qtype or "未知",
        "grade": grade or "通用",
        "difficulty": difficulty,
        "confidence": confidence,
        "matched": matched,
    }


def classify_blocks(blocks: list[dict]) -> dict[str, Any]:
    """直接用 OCR blocks 分类

    流程:
    1. 拼纯文本（公式用 plain 字段,即 Unicode 版）
    2. 调 classify()
    """
    parts: list[str] = []
    for b in blocks or []:
        btype = b.get("type")
        if btype == "formula":
            parts.append(b.get("plain") or b.get("latex") or "")
        elif btype == "text":
            parts.append(b.get("text") or "")
    text = "\n".join(p for p in parts if p)
    return classify(text, blocks)


def build_content_versions(blocks: list[dict]) -> dict[str, str]:
    """从 blocks 生成三个内容版本

    Returns:
        {"plain": "...", "markdown": "...", "blocks_json": "..."}
    """
    plain_parts: list[str] = []
    md_parts: list[str] = []

    for b in blocks or []:
        btype = b.get("type")
        if btype == "formula":
            plain_parts.append(b.get("plain") or b.get("latex") or "")
            md_parts.append(f"${b.get('latex', '')}$")
        elif btype == "text":
            text = b.get("text") or ""
            plain_parts.append(text)
            md_parts.append(text)
        elif btype == "table":
            plain_parts.append(b.get("html") or "")
            md_parts.append(b.get("html") or "")

    return {
        "plain": "\n".join(p for p in plain_parts if p),
        "markdown": "\n".join(p for p in md_parts if p),
        "blocks_json": json.dumps(blocks or [], ensure_ascii=False),
    }
