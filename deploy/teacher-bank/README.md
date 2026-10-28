# 教师题库系统 · 部署手册

> 目标服务器：阿里云 ECS 2C4G（8.160.177.222）· Alibaba Cloud Linux 3
> 线上入口：`https://tqb.lanhu-lab.top`（⏳ ICP 备案审核中）· 备用 `http://8.160.177.222/`
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

---

## 🔗 相关

- 教学文档：`docs/lesson-10-notes.md`
- OCR 部署：`deploy/paddleocr/01-install.sh` · `reinstall-paddleocr.sh`
- 前端构建：`lesson-03/`（`npm run build`，产物在 `dist/`）
