# 服务器环境验证 Checklist

> 老大 2026-08-13 说"做了初始化，该有的都有了"
> **跑下面 8 条命令确认下**，5 分钟搞定

---

## 1️⃣ 5 条基础命令

SSH 上服务器后跑：

```bash
# 1. Python（系统可能是 3.10 / 3.11 / 3.12）
python3 --version

# 2. pip
pip3 --version

# 3. PostgreSQL
which psql && psql --version

# 4. Nginx
which nginx && nginx -v

# 5. venv 模块
python3 -m venv --help > /dev/null 2>&1 && echo "venv OK" || echo "venv missing"
```

## 2️⃣ 期望结果

| 命令 | 期望输出 |
|---|---|
| `python3 --version` | `Python 3.10.x` / `3.11.x` / `3.12.x`（3.10+ 都可以） |
| `pip3 --version` | `pip x.x` |
| `psql --version` | `psql (PostgreSQL) 14.x` 或 `15.x` 或 `16.x` |
| `nginx -v` | `nginx version: nginx/1.18` 或更新 |
| `venv test` | `venv OK` |

## 3️⃣ 缺什么装什么

把输出发我，缺的我直接告诉你装什么。

参考命令（**别直接跑，先发我看**）：

```bash
# 如果 Python 3.10- 是系统默认（Ubuntu 22.04 默认 3.10）
# 装 3.11（推荐）：
sudo apt install software-properties-common -y
sudo add-apt-repository ppa:deadsnakes/ppa -y
sudo apt install python3.11 python3.11-venv python3.11-dev -y

# 装 PostgreSQL：
sudo apt install postgresql postgresql-contrib -y
sudo systemctl start postgresql
sudo systemctl enable postgresql

# 装 Nginx：
sudo apt install nginx -y
sudo systemctl start nginx
sudo systemctl enable nginx
```

## 4️⃣ DNS 解析验证

**在本地 Mac 跑**（不是服务器上）：

```bash
nslookup lanhu-lab.top
# 或
dig lanhu-lab.top
```

期望看到 A 记录指向**阿里云服务器 IP**。

如果没解析：
- 去阿里云 DNS 控制台加 A 记录
- 主机记录：`@`（或留空）
- 记录值：服务器 IP
- TTL：10 分钟

## 5️⃣ HTTP 访问测试

服务器跑：

```bash
sudo systemctl status nginx
# 应该看到 active (running)

curl http://localhost
# 应该看到 Nginx 欢迎页
```

本地 Mac 跑：

```bash
curl http://lanhu-lab.top
# 应该看到 Nginx 欢迎页（或被防火墙挡住，那是 OK 的）
```

## 6️⃣ 验收标准

- [ ] Python 3.10+ ✅
- [ ] pip 可用 ✅
- [ ] PostgreSQL 装了 ✅
- [ ] Nginx 装了 + 跑起来 ✅
- [ ] 域名 DNS 解析到服务器 IP ✅
- [ ] 服务器本地 `curl http://localhost` 看到 Nginx 欢迎页 ✅

---

## 7️⃣ 把结果发我

把 5 条命令的输出复制贴回来，我看看缺什么。

如果一切 OK → 我们就开始第 1 课：写第一个 FastAPI 应用。

---

## 🆘 遇到 SSH 问题

```bash
# 第一次连不上
ssh -v root@你的IP
# -v 看详细日志

# 改 SSH 端口（如果默认 22 不通）
ssh -p 2222 root@你的IP
```

如果还是不行，告诉我你的 SSH 用户名和端口（**不要发密码/密钥**），我看下问题在哪。
