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
DB_USER="teacherbank"
DB_PASSWORD="tb_app_2026"
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
cp "$(dirname "$0")/nginx-teacherbank.conf" /etc/nginx/conf.d/teacherbank.conf
sed -i "s/tqb\.lanhu-lab\.top/$DOMAIN/g" /etc/nginx/conf.d/teacherbank.conf
nginx -t && systemctl reload nginx
echo "  ✓ nginx 已配置"

if [ "$SKIP_CERTBOT" = "1" ]; then
  echo "  · 跳过 certbot(SKIP_CERTBOT=1)"
else
  echo "  签发 HTTPS 证书..."
  certbot --nginx -d "$DOMAIN" --email "$SSL_EMAIL" --agree-tos --no-eff-email \
    --redirect || echo "  ⚠️ certbot 失败(可能 DNS 没解析),稍后手动跑"
fi

echo ""
echo "=============================================="
echo " ✅ 部署完成"
echo "   http://$DOMAIN/    (HTTPS 看上面 certbot 结果)"
echo "   后端: 127.0.0.1:8000"
echo "   日志: journalctl -u teacherbank-api -f"
echo "=============================================="
