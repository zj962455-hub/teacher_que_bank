# PaddleOCR 服务部署(阿里云 ECS)

OCR 服务跑在阿里云 ECS 上,统一对外暴露 HTTP API。
**所有调用方**(本地测试 / 萝卜特服务 / 未来小程序)都走这个 API,不再依赖 Mathpix 之类的第三方。

---

## 🏗 架构

```
[客户端]              [阿里云 ECS 2C4G Ubuntu]
                      
浏览器/脚本  ─┐        ┌─ nginx (443/80) ─→ 反代
              ├─HTTPS─→│
萝卜特(我)   ─┘         └─ paddleocr-api (FastAPI :8080)
                              │
                              ├─ PaddleOCR (PP-StructureV3)
                              └─ 模型目录 ~/.paddleocr/
                              
                      [数据]
                      - 日志: /var/log/paddleocr-api/
                      - systemd 守护
```

**关键参数:**
- 单进程(模型占内存,workers=1)
- 并发上限:2(避免 OOM,4G 内存小)
- 图片上传上限:10MB
- 单图耗时:3-10 秒(纯 CPU,无 GPU)

---

## 🚀 一键脚本(推荐路径 B)

## 系统要求

- **Alibaba Cloud Linux 3 (OpenAnolis)** / RHEL 8+ / CentOS 8+
- 2C4G+ 内存(PaddleOCR 模型加载后 ~1.5GB)
- root 权限
- 阿里云安全组放行 **80 / 443**(22 已经有了)
- Python 3.9+ 由 `01-install.sh` 自动装(默认 python3.6.8 太老,跳过)

## 三步走

### 1. 本地推文件到 ECS

由于本地代理会拦截域名 SSH,建议**直接用公网 IP**:

```bash
# 先查 ECS 公网 IP(阿里云控制台),假设是 8.142.xx.xx
rsync -avz --exclude '.venv' --exclude '__pycache__' \
  ~/.openclaw/workspace/projects/teacher-question-bank/deploy/paddleocr/ \
  root@8.142.xx.xx:/opt/paddleocr-deploy/
```

SSH 也是:
```bash
ssh root@8.142.xx.xx
```

### 2. ECS 上跑一键安装

```bash
cd /opt/paddleocr-deploy
bash 01-install.sh
```

这个脚本会(7 步):
- `[1/7] dnf install python3.11 nginx certbot python3-certbot-nginx bind-utils` 等(Anolis 用 dnf,不是 apt)
- `[2/7] 建 paddleocr 系统用户 + 目录`
- `[3/7] 建 Python 3.11 venv + 装 paddleocr paddlepaddle fastapi uvicorn`(模型会下 ~300MB)
- `[4/7] 生成 2 个 API key 并打印(本地用 + 服务用)`
- `[5/7] systemd unit + 自启`
- `[6/7] nginx 反代 + 自动替换 server_name 为 $DOMAIN`
- `[7/7] certbot 自动签 HTTPS 证书(需要 DNS 已解析,否则跳过并提醒手动跑)`

⚠️ 中间模型下载 5-10 分钟,耐心等。

⚠️ certbot 需要 `SSL_DOMAIN`(默认 `lanhu-lab.top`)的 DNS A 记录指向 ECS 公网 IP。如未配，脚本会跳过 HTTPS 并提醒手动跑 certbot。

**环境变量覆盖(可选):**
```bash
# 自定义域名(默认 lanhu-lab.top)
SSL_DOMAIN=api.lanhu-lab.top bash 01-install.sh

# 自定义邮箱(默认 admin@<DOMAIN>)
SSL_EMAIL=admin@example.com bash 01-install.sh

# 跳过 certbot(本地测试 / DNS 没配时)
SKIP_CERTBOT=1 bash 01-install.sh
```

### 3. 验证

在 ECS 上跑:
```bash
curl -s http://127.0.0.1:8080/api/v1/health     # 内部
curl -s https://lanhu-lab.top/api/v1/health    # 外部 HTTPS(证书已签后)
```

或在本地(把 IP 替成 ECS 公网 IP 或域名,key 替成 01-install.sh 打印出来的):
```bash
cd ~/.openclaw/workspace/projects/teacher-question-bank/deploy/paddleocr/test
bash health.sh https://lanhu-lab.top
bash ocr-test.sh https://lanhu-lab.top <本地key> /path/to/某张题图.jpg
```

---

## 🔑 鉴权(API Key)

- 所有 `/api/v1/*` 端点要求 `X-API-Key: <token>` header
- token 存 `/etc/paddleocr/api.env`(`EnvironmentFile=` 加载)
- 默认生成两个 token:**老大本地** + **服务调用**,各自可独立吊销

**查看/修改 token:**
```bash
sudo nano /etc/paddleocr/api.env
sudo systemctl restart paddleocr-api
```

---

## 📡 API

### 健康检查
```bash
curl https://lanhu-lab.top/api/v1/health
# → {"status":"ok","model":"PP-StructureV3","version":"..."}
```

### 单图 OCR
```bash
curl -X POST \
  -H "X-API-Key: <token>" \
  -F "image=@/path/to/question.jpg" \
  https://lanhu-lab.top/api/v1/ocr/image
```

返回结构:
```json
{
  "ok": true,
  "blocks": [
    {"type":"text","text":"下列哪个是...","bbox":[x1,y1,x2,y2],"confidence":0.98},
    {"type":"formula","latex":"\\frac{a}{b}","bbox":[...],"confidence":0.92},
    {"type":"table","html":"<table>...</table>","bbox":[...],"confidence":0.85}
  ],
  "stats": {"elapsed_ms":3500,"model":"PP-StructureV3"}
}
```

---

## 🔧 运维命令速查

| 操作 | 命令 |
|------|------|
| 看日志 | `journalctl -u paddleocr-api -f` |
| 重启服务 | `sudo systemctl restart paddleocr-api` |
| 停服务 | `sudo systemctl stop paddleocr-api` |
| 看 nginx 日志 | `tail -f /var/log/nginx/paddleocr.access.log` |
| 模型重下 | `rm -rf ~/.paddleocr && systemctl restart paddleocr-api` |

---

## 📁 文件结构

```
deploy/paddleocr/
├── README.md                       # ← 你正在看的
├── 01-install.sh                   # 一键安装
├── app/
│   ├── main.py                     # FastAPI 入口
│   ├── ocr.py                      # PaddleOCR 封装
│   ├── schemas.py                  # 请求/响应模型
│   ├── config.py                   # 配置(读 env)
│   └── requirements.txt            # Python 依赖
├── deploy/
│   ├── paddleocr-api.service       # systemd unit
│   ├── paddleocr-api.env.example   # 环境变量模板
│   └── nginx-paddleocr.conf        # nginx 反代
└── test/
    ├── health.sh                   # 健康检查
    └── ocr-test.sh                 # 端到端 OCR 测试
```

---

## ⚠️ 已知限制 / 风险

- 4G 内存偏紧,**模型预热后约占 1.5-2GB**,并发过高会触发 OOM killer
- CPU 推理慢,单图 3-10 秒;**批量 OCR 走多请求**,不要并发塞满
- 当前不接 GPU(成本 + 4G 跑不动),以后上 8G+ 可考虑 ONNX 加速
- PaddleOCR 升级有时 break API,**锁版本**:`paddleocr==2.7.3`、`paddlepaddle==2.6.0`(在 requirements 里)
- ECS 默认 Python 3.6 太老,**脚本强制装 python3.9**,venv 在 `/opt/paddleocr/.venv/` 里
- Anolis / RHEL nginx 默认配置目录是 `/etc/nginx/conf.d/`(不是 Ubuntu 的 sites-enabled),脚本已处理
- ECS 本地有 66+ 安全补丁未打,**部署期间先不碰**,服务稳定后再单独打补丁

---

## 🗓 与主项目对接

部署好之后,`teacher-question-bank/lesson-06` 的 OCR 模块:

- `teacher_question_bank/app/services/ocr.py` → 调用本服务的 `/api/v1/ocr/image`
- 配置:`OCR_API_URL=https://lanhu-lab.top/api/v1`、`OCR_API_KEY=<token>`
- 渲染层:**LaTeX 用 KaTeX**(已在 lesson-XX 链上),表格 HTML 走 Vue 组件
- 主栈 OCR 模块从 `Mathpix` 改成 `PaddleOCR(自托管)`