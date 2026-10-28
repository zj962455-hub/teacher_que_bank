# Lesson 10 精简注释版 · 部署上线（Nginx + systemd + 域名）

> 上一课:组卷 + 导出 PDF,整套系统本地跑通了。
> 这一课:**搬到公网服务器上** —— 老师/学生能通过域名访问。

---

## 📍 为什么要单独一课部署

前 9 课都是「本地跑通」,这课是**第一次面对真实运维环境**:

| 本地 | 服务器 |
|---|---|
| 随便改随便重启 | 改了要 reload,不能随便重启 |
| 内存随便用 | **2C4G,只有 3.5GB 可用** |
| 端口随便占 | 8080/8000 只能本机听 |
| 密钥在 .env | 密钥在 /etc,权限 600 |
| 没有备案 | **没备案域名公网访问会被拦** |

---

## 🧠 4 个核心概念（读 4 分钟）

### 1. 同源架构(不用 CORS)

```
https://tqb.lanhu-lab.top/       → nginx 托管 Vue dist(/opt/teacher-bank/web)
https://tqb.lanhu-lab.top/api/   → nginx 反代 127.0.0.1:8000
```

**好处**:前端用相对路径 `/api`,不用管域名、不撞 CORS、以后加 cookie 也简单。

### 2. 独立用户 + 目录三分法

```
/opt/teacher-bank/   应用代码(可写)
/etc/teacherbank/    配置 + 密钥(chmod 600,不放代码里)
/var/log/teacherbank/ 日志
```

**代码目录被删过一次**(PaddleOCR 的 `/opt/paddleocr` 就被删了,进程靠已删除的 inode 苟着,一重启就死) → **所有东西必须在 /opt 或 /etc**。

### 3. systemd 沙箱加固(会踩坑)

```ini
ProtectHome=true      # ⚠️ 屏蔽整个 /home!
ProtectSystem=full
ReadWritePaths=/var/log/teacherbank /opt/teacher-bank/app/uploads
```

⚠️ **`ProtectHome=true` 会让 `/home` 整个不可访问** —— 连 `Environment=HOME=...` 都读不到。
Playwright 会报 `Executable doesn't exist at /home/xxx/chrome`(**文件明明在、权限也正常,极具误导性**)。

### 4. ICP 备案(公网访问的硬门槛)

中国大陆服务器 + 域名 → 必须备案。没备案阿里云会拦:
```
HTTP/1.1 403 Forbidden
Server: Beaver              ← 阿里云的备案检查中间层
<title>Non-compliance ICP Filing</title>
```

⚠️ **Beaver 拦域名,不拦 IP** —— 备案期间可以用 `http://8.160.177.222/` 走 IP 通道。

---

## 🧭 4 个设计决策（老大拍板）

| # | 决策点 | 选择 | 理由 |
|---|---|---|---|
| 1 | 服务器 | **同一台 ECS**(跑着 PaddleOCR) | 省钱;省一次跨机调用 |
| 2 | 域名 | **子域名** `tqb.lanhu-lab.top` | 不用新买域名 |
| 3 | 前端放哪 | **放 ECS**(代码+产物都在) | 老大要"所有资源都倾斜过来" |
| 4 | 前端构建在哪 | **本地构建 → 传产物** | 构建峰值 438MB,ECS 只有 3.5GB 不够跑 vite |

---

## 📁 本课最终改动

```
teacher_que_bank/
├── deploy/teacher-bank/
│   ├── 01-install.sh                 ← 一键安装
│   ├── rebuild.sh                    ← 增量更新(日常用这个)
│   ├── teacherbank-api.service       ← systemd unit
│   └── nginx-teacherbank.conf       ← nginx 同源反代
└── lesson-03/src/api/config.js       ← API 地址环境化
```

---

## 🚀 步骤

### 步骤 1: 前端 API 地址环境化

```js
// src/api/config.js
export const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'
export const API = `${API_BASE}/api`
```
```bash
# .env.development
VITE_API_BASE=http://localhost:8000
# .env.production
VITE_API_BASE=          # 空 → 相对路径 /api
```

⚠️ **必须用 `??` 不能用 `||`** —— `.env.production` 的空值是 `''`(falsy),
用 `||` 会 fallback 到 localhost → **生产产物带着 localhost → 部署后浏览器访问自己电脑 → 直接挂**。

### 步骤 2: 数据库 + 认证

```bash
# 建角色
su - postgres -c "psql -c \"CREATE ROLE teacherbank LOGIN PASSWORD 'xxx';\""
# 建库
su - postgres -c "psql -c \"CREATE DATABASE teacher_question_bank OWNER teacherbank ENCODING 'UTF8';\""
```

⚠️ **ECS 上 `password_encryption` 可能是 md5**(Mac 上是 scram-sha-256)→ 存的 md5 哈希但 hba 要 scram → 认证失败。
**修**:
```sql
SET password_encryption='scram-sha-256';
ALTER ROLE teacherbank PASSWORD 'xxx';
```
⚠️ **pg_hba 要加精确规则(放最前,第一条匹配生效)**:
```
host    teacher_question_bank   teacherbank   127.0.0.1/32   scram-sha-256
```

### 步骤 3: systemd unit

```ini
[Service]
User=teacherbank
WorkingDirectory=/opt/teacher-bank/app
EnvironmentFile=/etc/teacherbank/app.env
ExecStart=/opt/teacher-bank/.venv/bin/uvicorn app.main:app \
  --host 127.0.0.1 --port 8000 --workers 1
ProtectHome=true
ReadWritePaths=/var/log/teacherbank /opt/teacher-bank/app/uploads
Environment=PLAYWRIGHT_BROWSERS_PATH=/opt/teacher-bank/.playwright
MemoryMax=700M
```

⚠️ **`--workers 1`**:多 worker 会各自拉一份 Chromium → OOM。
⚠️ **`PLAYWRIGHT_BROWSERS_PATH` 必须在 /opt**:`ProtectHome=true` 挡住 /home。

### 步骤 4: nginx

```nginx
upstream teacherbank_backend { server 127.0.0.1:8000; }
server {
    listen 80 default_server;         # ← IP 直连通道(备案期间用)
    server_name tqb.lanhu-lab.top;
    client_max_body_size 12M;
    location /api/    { proxy_pass http://teacherbank_backend; proxy_read_timeout 120s; }
    location /uploads/ { proxy_pass http://teacherbank_backend; }
    location /        { root /opt/teacher-bank/web; try_files $uri $uri/ /index.html; }
}
```

⚠️ **静态文件权限**:rsync 传过去是 700/600 → nginx worker(nginx 用户)读不了 → 403。
```bash
find web -type d -exec chmod 755 {} \;
find web -type f -exec chmod 644 {} \;
```

### 步骤 5: 增量更新(日常用)

```bash
bash deploy/teacher-bank/rebuild.sh
# 本地构建前端 → rsync → 修权限 → 重启 → 验证
```

---

## 🛡️ 资源账(2C4G)

| 组件 | 常驻 | 峰值 |
|---|---|---|
| PaddleOCR(PP-StructureV3) | ~700MB | ~2.5GB |
| 题库后端 | ~150MB | |
| **前端构建** | — | **+438MB** |
| **Chromium 渲染 PDF** | — | **+300-500MB** |
| nginx + OS | ~400MB | |

**最坏情况**(PaddleOCR 大图 + 同时导 PDF)= 3.35GB → 顶满 3.5GB → swap 顶着。
**缓解**:Chromium 并发锁(同时只跑1个) + 服务 MemoryMax + swap 兜底。

---

## ⚠️ 部署踩的 8 个坑

1. **rsync 没装** → `dnf install -y rsync`
2. **PostgreSQL 密码 md5/scram 不匹配** → 重设密码 + 改 pg_hba
3. **`sudo` 默认清空环境变量** → `sudo -u xxx -E` 或靠 systemd 的 EnvironmentFile
4. **systemd `WantedBy` 首字母必须大写**(大小写敏感)→ `systemctl enable` 报"no installation config"
5. **nginx 读不了 700 权限目录** → chmod 755/644
6. **Playwright 默认用 headless_shell** → `launch(channel="chromium")`
7. **`ProtectHome=true` 挡住 /home** → 浏览器挪 /opt
8. **同机服务绕公网域名互调** → 改 `127.0.0.1`(不受备案/DNS影响,key 不出机器)

---

## ✅ ECS 重启验证(2026-10-27 19:41 · 8/8 通过)

```
uptime 3min · 4 服务全自启 · OCR 端到端 511ms · PDF 200 · 数据持久
模型缓存 1.7G 复用 · 内存 813Mi/3.5Gi
```

**三个前提(缺一不可):**
1. 代码在 **/opt**(不在会被删的地方)
2. Playwright 浏览器在 **/opt/teacher-bank/.playwright**
3. PaddleOCR `ProtectHome=false` + `ReadWritePaths` 含 `/home/paddleocr`(读模型缓存)

---

## 📚 速查表

### 常用命令

```bash
# 服务状态
systemctl status teacherbank-api --no-pager
journalctl -u teacherbank-api -f
tail -f /var/log/teacherbank/stderr.log

# 改配置后
systemctl daemon-reload && systemctl restart teacherbank-api

# 本机自测(不依赖域名)
curl -H "Host: tqb.lanhu-lab.top" http://127.0.0.1/api/questions/

# 内存
free -h
systemctl status teacherbank-api | grep Memory
```

---

## 🔗 相关

- 上一课:`lesson-09-notes.md`(组卷 + PDF)
- 部署手册:`deploy/teacher-bank/README.md`
- OCR 部署:`deploy/paddleocr/01-install.sh` · `reinstall-paddleocr.sh`
