"""
写备案字段：**MPS 进 site.config.js，其余个人信息进 .env.local**

为什么分两个地方（2026-11-20 改）
--------------------------------
- site.config.js 是**入库文件**，而 teacher_que_bank 仓库在 GitHub 上是 **public**。
  把运营主体姓名、联系方式写进去 = 把个人信息推到公开仓库，
  以后删掉也还能从 git 历史里翻出来。
- 所以拆开：
    MPS（公安备案号，公开信息）      → site.config.js（入库无妨）
    OPERATOR / CONTACT（个人信息）  → frontend/.env.local（.gitignore 已忽略，不入库）
  前端从 import.meta.env.VITE_OPERATOR / VITE_CONTACT 读，构建时注入。

⚠️ Vite 加载顺序：.env → .env.local → .env.[mode] → .env.[mode].local，
   **后者覆盖前者**。所以入库的 .env.development / .env.production 里
   只能写注释说明，**不能写 VITE_OPERATOR= 空值** ——
   否则空值会把 .env.local 里的真实值覆盖掉，线上那行又不显示了。

用法：python3 _set_site_fields.py <MPS> <OPERATOR> <CONTACT> <site.config.js 路径>
  —— 空字符串表示「这一项不动」（不是清空）

⚠️ 拒绝样例值：真实值没到位，正确做法是**留空**（页面会自动隐藏那一行），
   不是写「某某公司」「待填」这种假信息 —— 假信息一旦上线就是备案事故。
"""

import io
import os
import re
import sys

BANNED = (
    "待填",
    "待补充",
    "某某",
    "占位",
    "placeholder",
    "example.com",
    "TODO",
    "FIXME",
    # 我们自己在用法注释/文档里用过的假值 —— 照抄注释就会把假信息推到公网
    "13800000000",
    "13800138000",
    "公司全称",
)


def _check(name, value):
    for bad in BANNED:
        if bad in value:
            raise SystemExit("!! 拒绝写入样例值（%s 里含「%s」）" % (name, bad))
    # 尖括号 = 没填的占位写法（<主办单位全称> 之类）
    if "<" in value or ">" in value:
        raise SystemExit("!! 拒绝写入占位写法（%s 里含尖括号）" % name)


def set_js_field(text, name, value):
    """改 site.config.js 里的 export const NAME = '...'"""
    if not value:
        return text, False
    _check(name, value)
    safe = value.replace("\\", "\\\\").replace("'", "\\'")
    new, n = re.subn(
        r"^export const " + name + r" = '[^']*'.*$",
        "export const " + name + " = '" + safe + "'",
        text,
        count=1,
        flags=re.M,
    )
    if n == 0:
        raise SystemExit("!! 没找到 export const " + name + " = 这一行")
    return new, True


def set_env_field(text, key, value):
    """改 .env.local 里的 KEY=value"""
    if not value:
        return text, False
    _check(key, value)
    line = key + "=" + value
    pattern = r"^" + re.escape(key) + r"=.*$"
    if re.search(pattern, text, flags=re.M):
        new, n = re.subn(pattern, line, text, count=1, flags=re.M)
        return new, True
    if text and not text.endswith("\n"):
        text += "\n"
    return text + line + "\n", True


def main():
    if len(sys.argv) != 5:
        raise SystemExit("用法: _set_site_fields.py <MPS> <OPERATOR> <CONTACT> <site.config.js 路径>")
    mps, operator, contact, path = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
    s = io.open(path, encoding="utf-8").read()

    s, a = set_js_field(s, "MPS", mps)
    if a:
        # ⚠️ 必须真的落盘：少了这一行，脚本会打印「已写入」但文件没变 ——
        #    备案号回填会「静默假成功」（号没进 site.config.js，构建/rsync/验收
        #    用的还是空值，脚本最后照样打印「✅ 已回填并上线」）。
        io.open(path, "w", encoding="utf-8").write(s)
        print("  已写入 MPS = " + mps + "（site.config.js）")

    # 个人信息 → frontend/.env.local（不入库）
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(path))), ".env.local")
    env = io.open(env_path, encoding="utf-8").read() if os.path.exists(env_path) else ""
    env, b = set_env_field(env, "VITE_OPERATOR", operator)
    env, c = set_env_field(env, "VITE_CONTACT", contact)
    if b or c:
        io.open(env_path, "w", encoding="utf-8").write(env)
        os.chmod(env_path, 0o600)
    if b:
        print("  已写入 VITE_OPERATOR（运营主体）→ .env.local（不入库）")
    if c:
        print("  已写入 VITE_CONTACT（联系方式）→ .env.local（不入库）")

    if not (a or b or c):
        print("  没有要写入的字段（全部为空 = 不动）")


main()
