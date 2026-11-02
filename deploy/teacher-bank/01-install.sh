#!/usr/bin/env bash
# 教师题库系统部署脚本 · teacher-question-bank
# 系统: Alibaba Cloud Linux 3 (OpenAnolis) / RHEL 8+
#
# 用法:
#   # 首次部署
#   bash 01-install.sh
#   # 增量更新（代码变了，重启服务）
#   bash rebuild.sh
#
# 架构:
#   nginx :443/:80  →  /  (静态 Vue dist)  +  /api/ (反代 8000)
#   systemd: teacherbank-api.service → uvicorn 127.0.0.1:8000
#   postgres: teacher_question_bank 库
#
# 依赖: 与 PaddleOCR 同机(8080)

set -euo pipefail

# === 可配置 ===
APP_ROOT="/opt/teacher-bank"
APP_USER="teacherbank"
DB_NAME="teacher_question_bank"
DB_USER="${DB_USER:-teacherbank}"
# ⚠️ 密码不写死 —— 部署时用环境变量传入
#    export DB_PASSWORD='<强密码>'; bash 01-install.sh
#    或直接写进服务器上的 /etc/teacherbank/app.env（chmod 600，不入 git）
if [ -z "${DB_PASSWORD:-}" ]; then
  echo "❌ 未设置 DB_PASSWORD 环境变量"
  echo "   用法: export DB_PASSWORD='<强密码>' && bash 01-install.sh"
  exit 1
fi
DOMAIN="${SSL_DOMAIN:-tqb.lanhu-lab.top}"
SSL_EMAIL="${SSL_EMAIL:-admin@${DOMAIN}}"
SKIP_CERTBOT="${SKIP_CERTBOT:-0}"
PYTHON_BIN="python3.11"
NODE_VERSION="v22.23.2"

echo "=============================================="
echo " 教师题库系统部署 · $DOMAIN"
echo "=============================================="

# ============ 1. 系统依赖 ============
echo "[1/8] 系统依赖..."
if ! command -v rsync &>/dev/null; then
  dnf install -y -q rsync
fi
if ! command -v nginx &>/dev/null; then
  dnf install -y -q nginx
fi
if ! command -v certbot &>/dev/null; then
  dnf install -y -q certbot python3-certbot-nginx
fi
systemctl enable nginx 2>/dev/null || true

# pip 走阿里云镜像(ECS 访问海外 PyPI 超时)
cat > /etc/pip.conf <<'EOF'
[global]
index-url = https://mirrors.aliyun.com/pypi/simple/
trusted-host = mirrors.aliyun.com
timeout = 60
EOF
echo "  ✓ 系统依赖就绪"

# ============ 2. 用户 + 目录 ============
echo "[2/8] 用户和目录..."
id -u "$APP_USER" &>/dev/null || useradd --system --create-home \
  --home-dir "/home/$APP_USER" --shell /usr/sbin/nologin "$APP_USER"
mkdir -p "$APP_ROOT"/{app,web,frontend}
mkdir -p "/etc/$APP_USER"
mkdir -p "/var/log/$APP_USER"
chown -R "$APP_USER:$APP_USER" "$APP_ROOT" "/var/log/$APP_USER" "/home/$APP_USER"
echo "  ✓ 目录就绪"

# ============ 3. Python venv + 依赖 ============
echo "[3/8] Python 依赖..."
if [ ! -d "$APP_ROOT/.venv" ]; then
  $PYTHON_BIN -m venv "$APP_ROOT/.venv"
fi
chown -R "$APP_USER:$APP_USER" "$APP_ROOT/.venv"
sudo -u "$APP_USER" "$APP_ROOT/.venv/bin/pip" install -q --upgrade pip wheel
sudo -u "$APP_USER" "$APP_ROOT/.venv/bin/pip" install -q \
  fastapi 'uvicorn[standard]' pydantic python-dotenv requests python-multipart \
  sqlmodel 'psycopg[binary]' playwright jinja2
echo "  ✓ Python 依赖就绪"

# ============ 4. Playwright Chromium ============
echo "[4/8] Playwright Chromium(首次较慢)..."
if [ ! -d "/home/$APP_USER/.cache/ms-playwright" ]; then
  # 系统库要 root
  "$APP_ROOT/.venv/bin/playwright" install-deps chromium
  # 浏览器本体要装到 APP_USER 的 HOME
  export PLAYWRIGHT_DOWNLOAD_HOST="${PLAYWRIGHT_DOWNLOAD_HOST:-https://cdn.npmmirror.com/binaries/playwright}"
  sudo -u "$APP_USER" HOME="/home/$APP_USER" \
    "$APP_ROOT/.venv/bin/playwright" install chromium
fi
echo "  ✓ Chromium 就绪"

# ============ 5. 数据库 ============
echo "[5/8] PostgreSQL..."
systemctl enable postgresql 2>/dev/null || true
systemctl start postgresql 2>/dev/null || true
sleep 2

# 建角色(已存在会报错,忽略)
su - postgres -c "psql -tAc \"SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'\"" | grep -q 1 || \
  su - postgres -c "psql -c \"CREATE ROLE $DB_USER LOGIN PASSWORD '$DB_PASSWORD';\""

# 建库
su - postgres -c "psql -tAc \"SELECT 1 FROM pg_database WHERE datname='$DB_NAME'\"" | grep -q 1 || \
  su - postgres -c "psql -c \"CREATE DATABASE $DB_NAME OWNER $DB_USER ENCODING 'UTF8';\""

# ⚠️ ECS 上 password_encryption 可能是 md5,而 hba 要 scram → 认证失败
#    统一重设一次密码(用 scram 格式)
su - postgres -c "psql -c \"SET password_encryption='scram-sha-256'; ALTER ROLE $DB_USER PASSWORD '$DB_PASSWORD';\""

# hba 加一条精确的 scram 规则(放最前优先匹配)
HBA=$(su - postgres -c "psql -tAc 'SHOW hba_file;'" | tr -d ' ')
if ! grep -q "$DB_NAME.*$DB_USER.*scram" "$HBA"; then
  sed -i "1i host    $DB_NAME   $DB_USER   127.0.0.1/32   scram-sha-256" "$HBA"
  su - postgres -c "psql -c 'SELECT pg_reload_conf();'" >/dev/null
fi
echo "  ✓ 数据库就绪"

# ============ 6. 配置文件 ============
echo "[6/8] 配置文件..."
if [ ! -f "/etc/$APP_USER/app.env" ]; then
  # PaddleOCR 的 key(同机)
  OCR_KEY=$(grep '^OCR_API_KEYS=' /etc/paddleocr/api.env 2>/dev/null \
    | cut -d= -f2- | cut -d, -f1 | tr -d '"' \r) || OCR_KEY=""
  cat > "/etc/$APP_USER/app.env" <<EOF
DATABASE_URL=postgresql+psycopg://$DB_USER:$DB_PASSWORD@127.0.0.1:5432/$DB_NAME
PADDLEOCR_BASE_URL=https://lanhu-lab.top
PADDLEOCR_API_KEY=$OCR_KEY
EOF
  chown "$APP_USER:$APP_USER" "/etc/$APP_USER/app.env"
  chmod 600 "/etc/$APP_USER/app.env"
  echo "  ✓ 配置文件已生成"
else
  echo "  · 配置文件已存在,跳过"
fi

# ============ 7. systemd ============
echo "[7/8] systemd 服务..."
cp "$(dirname "$0")/teacherbank-api.service" /etc/systemd/system/teacherbank-api.service
systemctl daemon-reload
systemctl enable teacherbank-api.service
systemctl restart teacherbank-api.service
sleep 8
systemctl status teacherbank-api.service --no-pager | head -8
echo "  ✓ 服务已启动"

# ============ 8. nginx + 证书 ============
echo "[8/8] nginx + HTTPS..."

# ⚠️ firewalld 默认只放行 ssh —— 不开 80/443，站点从公网完全连不上
# （本机 curl 127.0.0.1 一切正常，nginx 也监听 0.0.0.0:80，但外部 connection refused）
if systemctl is-active --quiet firewalld; then
  firewall-cmd --permanent --add-service=http  >/dev/null 2>&1 || true
  firewall-cmd --permanent --add-service=https >/dev/null 2>&1 || true
  firewall-cmd --reload >/dev/null 2>&1 || true
  echo "  ✓ firewalld 已放行 80/443"
fi

# ⚠️ ECS 无 IPv6 出口，但 gai 默认优先 IPv6 → certbot 连 LE 端点先卡 IPv6 超时
# → 签发/续期全失败（"Read timed out"）。强制 IPv4 优先。
if ! grep -q "^precedence ::ffff:0:0/96" /etc/gai.conf 2>/dev/null; then
  cat >> /etc/gai.conf <<'EOF'

# ECS 无 IPv6 出口，强制 IPv4 优先（certbot 连 Let's Encrypt 用）
precedence ::ffff:0:0/96  100
EOF
  echo "  ✓ gai.conf 已设为 IPv4 优先"
fi

# certbot 的 nginx 插件要往 webroot 写挑战文件
mkdir -p /var/www/html/.well-known/acme-challenge

cp "$(dirname "$0")/nginx-teacherbank.conf" /etc/nginx/conf.d/teacherbank.conf
sed -i "s/tqb\.lanhu-lab\.top/$DOMAIN/g" /etc/nginx/conf.d/teacherbank.conf
nginx -t && systemctl reload nginx
echo "  ✓ nginx 已配置"

if [ "$SKIP_CERTBOT" = "1" ]; then
  echo "  · 跳过 certbot(SKIP_CERTBOT=1)"
else
  echo "  签发 HTTPS 证书..."
  # LE 端点从国内 ECS 出去会抖动，重试几次再放弃
  for i in 1 2 3 4 5; do
    certbot --nginx -d "$DOMAIN" --email "$SSL_EMAIL" --agree-tos --no-eff-email \
      --redirect && break
    echo "  ⚠️ certbot 第 $i 次失败(LE 端点超时?),10 秒后重试"
    sleep 10
  done
  certbot certificates 2>&1 | grep -E "Certificate Name|Expiry" | sed 's/^/  /'
fi

echo ""
echo "=============================================="
echo " ✅ 部署完成"
echo "   http://$DOMAIN/    (HTTPS 看上面 certbot 结果)"
echo "   后端: 127.0.0.1:8000"
echo "   日志: journalctl -u teacherbank-api -f"
echo "=============================================="
