#!/usr/bin/env python3
"""在服务器上把 lanhu-lab.top 的 server 块从「一律 404」改成「托管静态首页」。

为什么要改
----------
公安备案要求一级域名能正常访问并显示站名 + 页脚工信部备案号。
改造前 paddleocr.conf 里的 lanhu-lab.top server 块是:
    location / { return 404 "Not Found"; }
—— 打开首页只有 Not Found，审核必然退回。

怎么做
------
只替换那一段 location /，其余（certbot 生成的 ssl 块、80 -> 301、
OCR 接口反代 /api/v1/、acme 验证路径）**一个字都不动**。

安全网
------
· 改前备份（带时间戳）
· 改完立刻 nginx -t；不通过就自动回滚，绝不留下起不来的配置
· 幂等：已经打过补丁就直接退出，不重复改
"""

import datetime
import pathlib
import shutil
import subprocess
import sys

CONF = pathlib.Path("/etc/nginx/conf.d/paddleocr.conf")
REMOTE_DIR = "/opt/lanhu-home"

OLD = """    # 其他路径拒绝
    location / {
        return 404 "Not Found";
    }
"""

NEW = r"""    # === 蓝狐网首页（静态）· 公安备案要求一级域名可正常访问 ===
    root /opt/lanhu-home;
    index index.html;

    # 隐藏文件一律拒绝（.env / .git 之类），但放行 acme 验证路径
    location ~ /\.(?!well-known) {
        deny all;
    }

    # 静态首页；找不到就回首页（单页站）
    location / {
        try_files $uri $uri/ /index.html;
    }
"""


def main():
    if not CONF.exists():
        sys.exit("找不到 %s" % CONF)

    text = CONF.read_text(encoding="utf-8")

    if "lanhu-home" in text:
        print("already patched: %s 已含 lanhu-home 静态首页配置" % CONF)
        check = subprocess.run(["nginx", "-t"], stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, universal_newlines=True)
        if check.returncode != 0:
            print(check.stderr)
            sys.exit("nginx -t 失败：磁盘上的配置有问题，请人工检查")
        print("nginx -t OK")
        return

    if OLD not in text:
        sys.exit(
            "在 %s 里找不到预期的旧 location 块 —— 配置可能被改过，"
            "**没有做任何修改**，请人工检查" % CONF
        )

    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = CONF.with_suffix(".conf.bak-%s" % ts)
    shutil.copy2(CONF, backup)
    print("backup -> %s" % backup)

    CONF.write_text(text.replace(OLD, NEW), encoding="utf-8")

    check = subprocess.run(["nginx", "-t"], stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, universal_newlines=True)
    if check.returncode != 0:
        shutil.copy2(backup, CONF)
        print("nginx -t 失败，已回滚到 %s" % backup)
        print(check.stderr)
        sys.exit(1)

    print("patched: %s" % CONF)
    print(check.stderr.strip())


if __name__ == "__main__":
    main()
