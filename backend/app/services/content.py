"""
用户可填内容校验 —— 账号标识信息的违法有害信息兜底拦截

为什么要有这一层
----------------
安全评估要求「对用户账号和通讯群组名称、昵称、简介、备注、标识等，
以及信息发布、转发、评论等服务功能中的违法有害信息，有防范和处置措施」。

蓝狐网的用户标识字段只有一个：显示名（display_name）——
没有简介、没有群组、没有头像标识。昵称在**注册时**填写、之后可自行修改
（PATCH /api/auth/profile），所以它是用户可写、平台可读的一处内容入口。

这一层拦两类
------------
1. 明显违反法律法规的关键词（涉黄/赌博/毒品/恐怖暴力/诈骗黑产/违禁物品）
2. 诱导性信息（网址、即时通讯账号）—— 账号标识里出现这些，
   等于在平台上留了一条引流通道

⚠️ 这一层是**兜底**，不是审核系统
---------------------------------
平台真正的防线是结构性的：没有面向公众的内容发布通道、没有评论与群组、
内容默认私有且需要鉴权、分享链接强制过期可吊销。
昵称既不展示在任何公开页面（分享页只渲染卷名与题目标签），
也不参与检索与互动 —— 构成不了「舆论」或「社会动员」。
这一层只是防止有人把明显的违法有害信息写进账号标识里。

⚠️ 不拦题目正文
--------------
题目内容是数学题（题干、公式、图形），**不做关键词过滤** ——
过滤会误伤正常的数学表述。要拦的是「标识类」字段。
"""

import re
import unicodedata

# 账号标识里允许出现的常见符号
_ALLOWED_SYMBOLS = set("·-_.()（）【】[]《》<>、，。！？!?,.:;；'\"@#&+*=%$")

# 诱导性信息：网址 / 即时通讯账号
_INDUCEMENT_PATTERNS = [
    (re.compile(r"https?://", re.I), "不能包含网址"),
    (re.compile(r"\bwww\.", re.I), "不能包含网址"),
    (
        re.compile(
            r"[a-z0-9.-]+\.(?:com|cn|net|org|top|xyz|cc|vip|shop)\b", re.I
        ),
        "不能包含网址",
    ),
    (
        re.compile(
            r"(?:微信|weixin|wechat|qq|扣扣|vx|v信|加v)\s*[:：]?\s*[a-z0-9_-]{4,}",
            re.I,
        ),
        "不能包含即时通讯账号",
    ),
]

# 基础违法有害关键词（分类）
ILLEGAL_KEYWORDS = {
    "涉黄": ("色情", "裸照", "情色", "招嫖", "约炮", "成人视频"),
    "赌博": ("赌博", "博彩", "赌钱", "六合彩", "澳门赌场"),
    "毒品": ("毒品", "冰毒", "海洛因", "大麻代购", "摇头丸"),
    "恐怖暴力": ("恐怖袭击", "暴恐", "制作枪支", "枪支买卖", "杀人不犯法"),
    "诈骗黑产": (
        "诈骗",
        "洗钱",
        "代开发票",
        "办假证",
        "代办证件",
        "身份证代办",
        "刷单返现",
    ),
    "违禁物品": ("迷药", "迷情药", "违禁药物", "野生动物贩卖"),
}


def check_display_name(name: str) -> list[str]:
    """检查显示名（昵称）是否合规。

    返回不合规原因列表；空列表 = 通过。
    """
    problems: list[str] = []

    stripped = (name or "").strip()
    if not stripped:
        problems.append("显示名不能为空")
        return problems

    if len(stripped) > 50:
        problems.append("显示名最长 50 字")

    # 控制字符 / 零宽字符（用来藏东西）
    for ch in stripped:
        if unicodedata.category(ch) in ("Cc", "Cf"):
            problems.append("显示名含有不可见字符")
            break

    # 不允许的符号（emoji 允许 —— category So）
    for ch in stripped:
        if (
            ch.isalnum()
            or ch.isspace()
            or unicodedata.category(ch) == "So"
            or ch in _ALLOWED_SYMBOLS
        ):
            continue
        problems.append("显示名含有不允许的字符")
        break

    for pattern, message in _INDUCEMENT_PATTERNS:
        if pattern.search(stripped):
            problems.append(message)
            break

    lowered = stripped.lower()
    for category, words in ILLEGAL_KEYWORDS.items():
        for w in words:
            if w.lower() in lowered:
                problems.append("含有违法违规内容（%s）" % category)
                break

    return problems
