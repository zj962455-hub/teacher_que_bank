# 服务器初始化 Checklist

> 阿里云 2C4G · Ubuntu（待确认具体版本）
> **第 10 课「部署上线」会用到这套环境**

---

## 1️⃣ 基础

- [ ] SSH 登录服务器
  ```bash
  ssh root@你的服务器IP
  ```
- [ ] 创建非 root 用户（生产环境推荐）
  ```bash
  adduser deploy
  usermod -aG sudo deploy
  ```
- [ ] 系统更新
  ```bash
  sudo apt update && sudo apt upgrade -y
  ```
- [ ] 装基础工具
  ```bash
  sudo apt install -y curl wget git vim htop ufw fail2ban
  ```

---

## 2️⃣ Python 3.11

- [ ] 装 Python + venv + dev
  ```bash
  sudo apt install software-properties-common -y
  sudo add-apt-repository ppa:deadsnakes/ppa -y
  sudo apt install python3.11 python3.11-venv python3.11-dev -y
  ```
- [ ] 验证
  ```bash
  python3.11 --version  # Python 3.11.x
  ```

---

## 3️⃣ PostgreSQL

- [ ] 装
  ```bash
  sudo apt install postgresql postgresql-contrib -y
  ```
- [ ] 启动 + 开机自启
  ```bash
  sudo systemctl start postgresql
  sudo systemctl enable postgresql
  ```
- [ ] 创建数据库 + 用户（**安全考虑，不直接用 postgres 账号**）
  ```bash
  sudo -u postgres psql
  
  -- 在 psql 命令行里执行：
  CREATE USER tqb_user WITH PASSWORD '你的强密码';
  CREATE DATABASE teacher_question_bank OWNER tqb_user;
  GRANT ALL PRIVILEGES ON DATABASE teacher_question_bank TO tqb_user;
  \q
  ```
- [ ] 测试连接
  ```bash
  psql -U tqb_user -d teacher_question_bank -h localhost
  ```

---

## 4️⃣ Nginx

- [ ] 装
  ```bash
  sudo apt install nginx -y
  ```
- [ ] 启动 + 开机自启
  ```bash
  sudo systemctl start nginx
  sudo systemctl enable nginx
  ```
- [ ] 测试访问
  ```bash
  curl http://你的服务器IP
  # 应该看到 Nginx 欢迎页
  ```

---

## 5️⃣ 防火墙

- [ ] 配 UFW（默认防火墙）
  ```bash
  sudo ufw allow OpenSSH
  sudo ufw allow 80/tcp    # HTTP
  sudo ufw allow 443/tcp   # HTTPS
  sudo ufw enable
  sudo ufw status
  ```

---

## 6️⃣ 域名 + HTTPS

- [ ] DNS 解析：把域名 A 记录指向服务器 IP
- [ ] 装 Certbot（Let's Encrypt 免费证书）
  ```bash
  sudo apt install certbot python3-certbot-nginx -y
  sudo certbot --nginx -d 你的域名.com -d www.你的域名.com
  ```
- [ ] 配自动续期
  ```bash
  sudo certbot renew --dry-run
  ```

---

## 7️⃣ 项目部署（第十课详谈）

- [ ] 装 git（前面已装）
- [ ] clone 仓库
  ```bash
  cd /home/deploy
  git clone https://github.com/zj962455-hub/teacher_que_bank.git
  cd teacher_que_bank
  ```
- [ ] 建 venv + 装依赖
  ```bash
  python3.11 -m venv venv
  source venv/bin/activate
  pip install -r requirements.txt
  ```
- [ ] 配 `.env`（不提交到 Git）
  ```bash
  cp .env.example .env
  vim .env  # 填实际值
  ```
- [ ] 配 systemd 服务（让 gunicorn 后台跑）
  ```bash
  sudo vim /etc/systemd/system/tqb.service
  ```
  内容（第十课会写完整）：
  ```ini
  [Unit]
  Description=Teacher Question Bank FastAPI
  After=network.target

  [Service]
  User=deploy
  WorkingDirectory=/home/deploy/teacher_que_bank
  Environment="PATH=/home/deploy/teacher_que_bank/venv/bin"
  ExecStart=/home/deploy/teacher_que_bank/venv/bin/gunicorn main:app -w 2 -k uvicorn.workers.UvicornWorker -b 127.0.0.1:8000
  Restart=always

  [Install]
  WantedBy=multi-user.target
  ```
  ```bash
  sudo systemctl daemon-reload
  sudo systemctl start tqb
  sudo systemctl enable tqb
  ```

---

## 8️⃣ 监控

- [ ] 装 htop / iotop 看资源
  ```bash
  htop
  ```
- [ ] 配日志
  ```bash
  sudo journalctl -u tqb -f  # 实时看应用日志
  ```
- [ ] 配 logrotate（防止日志占满磁盘）
  ```bash
  sudo vim /etc/logrotate.d/tqb
  ```
  内容：
  ```
  /var/log/tqb/*.log {
      daily
      rotate 7
      compress
      missingok
      notifempty
  }
  ```

---

## 9️⃣ 验收清单

服务器环境完全 OK 的标志：

- [ ] SSH 能用非 root 用户登录
- [ ] `python3.11 --version` 输出 3.11.x
- [ ] PostgreSQL 能用 `tqb_user` 连接
- [ ] Nginx 启动且能访问欢迎页
- [ ] 域名解析正确，HTTPS 证书有效
- [ ] 项目能 clone、venv 能装、`.env` 能配
- [ ] `systemctl status tqb` 显示 active running
- [ ] `curl https://你的域名/api/info` 能返回 JSON

---

## 📅 时间预估

| 阶段 | 时间 |
|---|---|
| 1-5 基础环境 | 1 小时 |
| 6 域名 HTTPS | 30 min（DNS 解析要等几分钟到几小时） |
| 7 项目部署 | 1 小时（**第十课详细做**） |
| 8 监控 | 30 min |

**Phase 1 部署前完成 1-6 即可**。

---

## 🆘 常见问题

| 问题 | 解决 |
|---|---|
| 装包慢 / 超时 | 换源：`pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple` |
| PostgreSQL 连不上 | 检查 `pg_hba.conf` 认证方式；`listen_addresses` 是否监听 |
| Nginx 502 Bad Gateway | gunicorn 没启动或端口不对；`systemctl status tqb` |
| HTTPS 证书申请失败 | DNS 没解析；80 端口没开；域名拼写错 |

**卡住截图发我，我帮你定位**。
