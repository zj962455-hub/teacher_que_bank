"""
写 site.config.js 的备案字段（MPS / OPERATOR / CONTACT）

为什么单独一个文件
----------------
回填脚本 deploy/teacher-bank/fill-mps-number.sh 里本来是内嵌 python heredoc，
再往里加正则替换就越写越难读。拆出来单独一个文件，改起来不容易出错。

用法：python3 _set_site_fields.py <MPS> <OPERATOR> <CONTACT> <文件路径>
  —— 空字符串表示「这一项不动」（不是清空）

⚠️ 拒绝样例值：真实值没到位，正确做法是**留空**（页面会自动隐藏那一行），
   不是写「某某公司」「待填」这种假信息 —— 假信息一旦上线就是备案事故。
"""

import io
import re
import sys

BANNED = ("待填", "待补充", "某某", "占位", "placeholder", "example.com", "TODO", "FIXME")


def set_field(text, name, value):
    """只改非空字段 —— 传空 = 不动这一项"""
    if not value:
        return text, False
    for bad in BANNED:
        if bad in value:
            raise SystemExit("!! 拒绝写入样例值（%s 里含「%s」）" % (name, bad))
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


def main():
    if len(sys.argv) != 5:
        raise SystemExit("用法: _set_site_fields.py <MPS> <OPERATOR> <CONTACT> <文件路径>")
    mps, operator, contact, path = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
    s = io.open(path, encoding="utf-8").read()

    s, a = set_field(s, "MPS", mps)
    s, b = set_field(s, "OPERATOR", operator)
    s, c = set_field(s, "CONTACT", contact)

    io.open(path, "w", encoding="utf-8").write(s)

    if a:
        print("  已写入 MPS = " + mps)
    if b:
        print("  已写入 OPERATOR（运营主体名称）")
    if c:
        print("  已写入 CONTACT（应急联系方式）")
    if not (a or b or c):
        print("  没有要写入的字段（全部为空 = 不动）")


main()
