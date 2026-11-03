# 教师题库系统 · 部署手册

> 目标服务器：阿里云 ECS 2C4G（8.160.177.222）· Alibaba Cloud Linux 3
> 线上入口：`https://tqb.lanhu-lab.top`（✅ ICP 备案已通过 · HTTPS 证书已签）· 备用 `https://8.160.177.222/`
> 详细教学见 `docs/lesson-10-notes.md`

---

## 📐 架构

```
                    公网
                      │
              ┌───────┴────────┐
              │  nginx (:80/:443)│
              └───────┬────────┘
        ┌─────────────┴──────────────┐
        │                            │
  /  → 静态文件              /api/  → 反代
  /opt/teacher-bank/web      127.0.0.1:8000
                                     │
                        ┌────────────┴─────────────┐
                        │  teacherbank-api (systemd)  │
                        │  127.0.0.1:8000           │
                        └────────────┬─────────────┘
                                     │  /api/ocr/ → 本机直连
                        ┌────────────┴─────────────┐
                        │ paddleocr-api (systemd)    │
                        │  127.0.0.1:8080           │
                        │  PP-StructureV3            │
                        └────────────────────────────┘
                                     │
                          PostgreSQL 16 (本机)
                          teacher_question_bank
```

**同源**：前端用相对路径 `/api`，不用管域名、不撞 CORS。

---

## 📁 服务器目录

```
/opt/teacher-bank/
├── app/                 后端代码（lesson-02/）
│   ├── app/             Python 包
│   ├── static/katex/    KaTeX 静态资源（596KB）
│   ├── templates/       Jinja2 模板
│   └── uploads/         上传的图片 + OCR 历史
├── frontend/            前端源码（以后在服务器上改+构建用）
├── web/                 前端构建产物（nginx 托管）
├── .playwright/         Chromium 浏览器（681MB）⚠️ 必须在 /opt
└── .venv/               Python 3.11 venv

/etc/teacherbank/
└── app.env              配置 + 密钥（chmod 600）

/var/log/teacherbank/     stdout.log / stderr.log
```

---

## 🔧 日常运维命令

### 服务

```bash
systemctl status teacherbank-api --no-pager     # 状态
systemctl restart teacherbank-api                # 重启
journalctl -u teacherbank-api -f                 # 实时日志
tail -f /var/log/teacherbank/stderr.log          # 错误日志

systemctl status paddleocr-api --no-pager
```

### 本机自测（不依赖域名，备案期间也能用）

```bash
# 题库
curl -H "Host: tqb.lanhu-lab.top" http://127.0.0.1/api/questions/
curl -H "Host: tqb.lanhu-lab.top" http://127.0.0.1/docs

# OCR
curl -s http://127.0.0.1:8080/api/v1/health

# PDF 导出
curl -H "Host: tqb.lanhu-lab.top" -o /tmp/t.pdf http://127.0.0.1/api/papers/1/export.pdf
file /tmp/t.pdf
```

### 资源

```bash
free -h
systemctl status teacherbank-api | grep Memory
df -h /
```

---

## 🔄 更新代码（日常用这个）

**在本地 Mac 上跑：**
```bash
cd /Users/rrobot/Desktop/dev/teacher_question_bank
bash deploy/teacher-bank/rebuild.sh
```

它做四件事：
1. 本地 `npm run build`（ECS 只有 3.5GB，跑不动 vite）
2. rsync 后端 + 前端源码 + 构建产物到 ECS
3. 修静态文件权限（nginx worker 要能读）
4. 重启服务 + 验证

**ECS 配置文件变了**（比如加了新环境变量）要手动：
```bash
# 改 /etc/teacherbank/app.env 后
systemctl restart teacherbank-api
```

---

## 🆘 故障排查

### PDF 导出 500

```bash
journalctl -u teacherbank-api -n 30 --no-pager
```

**最可能**：Playwright 找不到浏览器
```bash
ls -la /opt/teacher-bank/.playwright/chromium-*/chrome-linux64/chrome
grep PLAYWRIGHT_BROWSERS_PATH /etc/systemd/system/teacherbank-api.service
```
⚠️ 浏览器**必须在 /opt**（`ProtectHome=true` 屏蔽 /home）。
⚠️ `ProtectHome=true` 时报 `Executable doesn't exist` 但文件明明在 —— **极具误导性**。

### 服务起不来

```bash
systemctl status teacherbank-api --no-pager
journalctl -u teacherbank-api -n 50 --no-pager
tail -30 /var/log/teacherbank/stderr.log
```

**常见**：配置里的 `DATABASE_URL` 没生效（正常，靠 systemd 的 `EnvironmentFile`）。

### OCR 502 / 超时

```bash
systemctl status paddleocr-api --no-pager
curl -s -m 60 http://127.0.0.1:8080/api/v1/health
tail -30 /var/log/paddleocr-api/stderr.log
```
⚠️ 首次启动要加载模型（1-2 分钟），模型缓存 1.7G 在 `/home/paddleocr/.cache`。
⚠️ PaddleOCR 的 `ProtectHome` 必须是 `false`（要读/写模型缓存）。

### 域名访问 403 + `Server: Beaver`

**ICP 备案没通过**。阿里云在公网入口拦截未备案域名。
**临时方案**：用 `http://8.160.177.222/`（IP 不拦）。
✅ 2026-11-02 起本项目备案已通过，Beaver 拦截已解除。

### 外部访问 `Connection refused`（本机 curl 一切正常）

**firewalld 只放行了 ssh**。nginx 明明监听 `0.0.0.0:80`，iptables/nft 看起来也全 ACCEPT，但公网就是连不上。

```bash
firewall-cmd --list-services        # 只看到 cockpit dhcpv6-client ssh
firewall-cmd --permanent --add-service=http
firewall-cmd --permanent --add-service=https
firewall-cmd --reload
```

⚠️ 排查时容易误判：`iptables -S` 输出全 ACCEPT、`nft list ruleset` 也看不出问题 —— 因为 firewalld 用的是独立的 nftables 表。
**判定法**：`nc -vz <IP> 80` + 看 `firewall-cmd --list-services`，不要只看 iptables。

### certbot 报错 `Read timed out`（连 acme-v02.api.letsencrypt.org 超时）

**ECS 没有 IPv6 出口，但系统 gai 默认优先 IPv6** —— certbot 先试 IPv6，卡到超时才回退。

```bash
ip -6 route show                  # 只有 ::1 和 fe80:: → 没有 IPv6 出口
curl -4 ...                       # IPv4 强制后正常
```

修法（写进 `/etc/gai.conf`）：
```
precedence ::ffff:0:0/96  100
```

⚠️ 另一个坑：**LE 端点从国内 ECS 出去会抖动**，同一天可能 3 次里只成 1 次。签发和续期都要重试循环。

### 证书续期一直失败 `Some challenges have failed`

看 `journalctl -u certbot-renew.service`：如果是备案期间留下的，那是 Beaver 拦的；
备案通过后还失败，就查上面两条（firewalld + IPv6）。

演练续期：
```bash
certbot renew --dry-run --no-random-sleep-on-renew
```

⚠️ `/var/www/html` 必须存在（certbot 的 nginx 插件要往里写挑战文件）：
`mkdir -p /var/www/html/.well-known/acme-challenge`

### 内存吃紧

```bash
free -h
```
2C4G 上 PaddleOCR + 题库 + Chromium 峰值会顶满。
- 题库服务 `MemoryMax=700M`（超了自动重启，不会拖垮整机）
- Chromium 一次只跑一个渲染

---

## 📦 重新部署（机器换了/目录被删了）

```bash
# 1. 传脚本
scp -r deploy/teacher-bank root@8.160.177.222:/opt/

# 2. 跑一键安装
ssh root@8.160.177.222
cd /opt/teacher-bank && bash deploy/teacher-bank/01-install.sh
```

⚠️ **安装脚本会动数据库和 nginx**，生产环境跑之前先备份。

---

## 🔒 密钥管理

| 密钥 | 位置 | 权限 |
|---|---|---|
| 数据库密码 | `/etc/teacherbank/app.env` | 600 |
| PaddleOCR API key | `/etc/paddleocr/api.env` | 600 |

**都不在代码里、不在 git 里。** 换密码：
```bash
# 数据库
su - postgres -c "psql -c \"SET password_encryption='scram-sha-256'; ALTER ROLE teacherbank PASSWORD '新密码';\""
# 然后同步改 /etc/teacherbank/app.env 并重启
```

### ⚠️ 历史泄露说明（2026-11-02）

commit `f07fbca`（部署到 ECS）曾把一个数据库口令硬编码进 `01-install.sh`。**该口令已于 2026-11-02 23:51 轮换失效**，线上不再使用。

在 Git 历史里搜到 `tb_app_2026` 的，请当作**已废弃的无效值**，不要再尝试使用。保留历史是为了不破坏 commit hash 与可回溯性。

已做的加固：
- `01-install.sh` 不再硬编码口令，改为必须由环境变量 `DB_PASSWORD` 传入，缺失则直接退出
- 口令轮换 + `/etc/teacherbank/app.env` 同步（权限 600）+ 服务重启验证
- 数据库仅监听 `127.0.0.1` / `::1`，外网不可达

---

## 🌐 上线状态（2026-11-02）

| 项 | 状态 |
|---|---|
| ICP 备案 | ✅ 已通过 · Beaver 拦截解除 |
| DNS | ✅ `lanhu-lab.top` / `tqb.lanhu-lab.top` → 8.160.177.222 |
| HTTPS 证书 | ✅ `tqb.lanhu-lab.top` 到期 2027-01-31（自动续期已验证） |
| 主域名证书 | ✅ `lanhu-lab.top` 到期 2026-11-25 · 自动续期已修复（IPv6 优先导致） |
| firewalld | ✅ 已放行 80/443 |
| 全链路 | ✅ 前端 / API / OCR（PP-StructureV3）/ PDF 导出 均 200 |

**待办**：公安联网备案（beian.mps.gov.cn · ICP 通过后 30 日内）· 网站页脚展示 ICP 备案号 + 公安备案号。

---

## 🔗 相关

- 教学文档：`docs/lesson-10-notes.md`
- OCR 部署：`deploy/paddleocr/01-install.sh` · `reinstall-paddleocr.sh`
- 前端构建：`lesson-03/`（`npm run build`，产物在 `dist/`）

---

## 👥 用户体系（lesson-11 · 2026-11-03）

### 建号

```bash
# 服务器上跑（需要 app.env 里的 DATABASE_URL）
set -a; . /etc/teacherbank/app.env; set +a
cd /opt/teacher-bank/app

# 建两个测试账号（弱口令 + 不强制改密，仅测试用）
/opt/teacher-bank/.venv/bin/python -m app.scripts.create_users --force --no-force-change

# 建正式账号（强口令 + 首登强制改密）
/opt/teacher-bank/.venv/bin/python -m app.scripts.create_users \
    --user zhang:张老师:Abc12345
```

密码规则：**大写 + 小写 + 数字 + ≥8 位**。不合规直接拒绝（`--force` 可跳过，仅限测试）。

### 迁移（改表结构必读）

⚠️ **`create_all` 不会给已存在的表加列** —— 加列必须跑迁移脚本：

```bash
set -a; . /etc/teacherbank/app.env; set +a
psql -h 127.0.0.1 -U teacherbank -d teacher_question_bank \
    -v ON_ERROR_STOP=1 -f /opt/teacher-bank/app/app/migrations/001_add_users.sql
```

顺序：**先建表 → 再建号 → 再跑迁移**（迁移里的存量归属靠 `username='test1'` 查 id，账号不存在会 `RAISE EXCEPTION` 回滚）。

### 目录结构（容易踩）

```
/opt/teacher-bank/app/          ← WorkingDirectory
├── app/                        ← 真正的 python 包(lesson-02/app → app/app)
│   ├── models.py
│   ├── migrations/001_add_users.sql
│   └── scripts/create_users.py
├── templates/
└── web/                        ← 前端产物(不在 app 下)
```

⚠️ rsync 时目标是 **`app/app/`**，不是 `app/` —— rsync 到 `app/` 会多出一层嵌套，服务加载不到。
