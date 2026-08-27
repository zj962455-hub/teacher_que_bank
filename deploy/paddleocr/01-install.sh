#!/usr/bin/env bash
# 一键安装 PaddleOCR API 服务
# 系统: Alibaba Cloud Linux 3 (OpenAnolis) / RHEL 8+
# 跑这个脚本前:cd /opt/paddleocr-deploy && bash 01-install.sh
# 要求:root、2C4G+

set -euo pipefail

APP_DIR="/opt/paddleocr"
APP_USER="paddleocr"
# 默认主域名(仅处理 a记录指向 ECS 的主域名)。子域名可用 SSL_DOMAIN=api.lanhu-lab.top 覆盖
DOMAIN="${SSL_DOMAIN:-lanhu-lab.top}"
# SSL 证书邮箱(Let's Encrypt 用于过期/安全提醒)
SSL_EMAIL="${SSL_EMAIL:-admin@${DOMAIN}}"
# 跳过 certbot(本地测试 / 没解析的域名 时设 1)
SKIP_CERTBOT="${SKIP_CERTBOT:-0}"
PYTHON_BIN="python3.11"

# ============ 1. 系统依赖 ============
echo "[1/7] 安装系统依赖(Anolis 3 / RHEL 8+, dnf)..."
dnf update -y -q

# 配置国内 PyPI 镜像(ECS 访问海外 PyPI 超时)
cat > /etc/pip.conf <<'EOF'
[global]
index-url = https://mirrors.aliyun.com/pypi/simple/
trusted-host = mirrors.aliyun.com
timeout = 60
EOF
echo "  ✓ 配置阿里云 PyPI 镜像"
dnf install -y --nogpgcheck \
  python3.11 python3.11-devel python3.11-pip \
  gcc gcc-c++ make \
  nginx \
  certbot python3-certbot-nginx \
  bind-utils \
  curl jq which openssl

# 启用 nginx + firewalld
systemctl enable nginx firewalld 2>/dev/null || true

# ============ 2. 用户 + 目录 ============
echo "[2/7] 创建用户和目录..."
id -u "$APP_USER" &>/dev/null || useradd --system --create-home --home-dir /home/paddleocr --shell /usr/sbin/nologin "$APP_USER"
# 兜底:如果用户已存在但 /home/paddleocr 缺失(老部署)
mkdir -p /home/paddleocr
chown -R "$APP_USER:$APP_USER" /home/paddleocr
# 给 pip 缓存建好目录
sudo -u "$APP_USER" mkdir -p /home/paddleocr/.cache/pip

mkdir -p /opt/paddleocr/app
mkdir -p /etc/paddleocr
mkdir -p /var/log/paddleocr-api

cp -r app/* /opt/paddleocr/app/
chown -R "$APP_USER:$APP_USER" /opt/paddleocr
chown -R "$APP_USER:$APP_USER" /var/log/paddleocr-api

# ============ 3. Python 3.11 venv + 依赖 ============
echo "[3/7] 创建 Python 3.11 venv 并装依赖(模型会下 ~300MB,耐心等)..."
if [ ! -d /opt/paddleocr/.venv ]; then
  $PYTHON_BIN -m venv /opt/paddleocr/.venv
  chown -R "$APP_USER:$APP_USER" /opt/paddleocr/.venv
fi

sudo -u "$APP_USER" /opt/paddleocr/.venv/bin/pip install --upgrade pip wheel setuptools -q
sudo -u "$APP_USER" /opt/paddleocr/.venv/bin/pip install -r /opt/paddleocr/app/requirements.txt -q

# ============ 4. 生成 API key ============
echo "[4/7] 生成 API keys..."
mkdir -p /etc/paddleocr
if [ ! -f /etc/paddleocr/api.env ]; then
  LOCAL_KEY=$(openssl rand -hex 24)
  SERVICE_KEY=$(openssl rand -hex 24)
  cat > /etc/paddleocr/api.env <<EOF
# PaddleOCR API keys(逗号分隔,任一有效即放行)
OCR_API_KEYS=${LOCAL_KEY},${SERVICE_KEY}
OCR_MAX_IMAGE_MB=10
OCR_MODEL=PP-StructureV3
OCR_LANG=ch
EOF
  chmod 600 /etc/paddleocr/api.env
  echo ""
  echo "==================================================="
  echo "  生成两个 API key(已存 /etc/paddleocr/api.env):"
  echo "  本地用:  ${LOCAL_KEY}"
  echo "  服务用:  ${SERVICE_KEY}"
  echo "  一定要把这两个 key 记下来!!"
  echo "==================================================="
  echo ""
fi
chown -R "$APP_USER:$APP_USER" /etc/paddleocr

# ============ 5. systemd ============
echo "[5/7] 配置 systemd..."
cp deploy/paddleocr-api.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable paddleocr-api
systemctl restart paddleocr-api
sleep 3
systemctl status paddleocr-api --no-pager || true

# ============ 6. nginx(适配 Anolis/RHEL) ============
echo "[6/7] 配置 nginx..."

# Anolis / RHEL 没有 sites-enabled,用 /etc/nginx/conf.d/
cp deploy/nginx-paddleocr.conf /etc/nginx/conf.d/paddleocr.conf

# 替换 server_name 到当前 DOMAIN(模板里硬编码的是旧域名 ecs.lanhu-lab.top)
sed -i "s/server_name ecs.lanhu-lab.top;/server_name ${DOMAIN};/" /etc/nginx/conf.d/paddleocr.conf

# 确保主配置 include 了 conf.d
if ! grep -q "include /etc/nginx/conf.d/\*.conf;" /etc/nginx/nginx.conf; then
  # 备份
  cp /etc/nginx/nginx.conf /etc/nginx/nginx.conf.bak.$(date +%s)
  # 在 http { } 块末尾加 include(用 python 解析比 sed 安全)
  python3 -c "
import re
with open('/etc/nginx/nginx.conf') as f:
    c = f.read()
m = re.search(r'http\s*\{', c)
if m:
    idx = m.end()
    new = c[:idx] + '\n    include /etc/nginx/conf.d/*.conf;' + c[idx:]
    with open('/etc/nginx/nginx.conf', 'w') as f:
        f.write(new)
    print('Added include /etc/nginx/conf.d/*.conf')
"
fi

nginx -t
systemctl enable nginx
systemctl restart nginx

# ============ 7. certbot HTTPS 证书 ============
echo "[7/7] 配置 HTTPS 证书(certbot)..."

if [ "${SKIP_CERTBOT}" = "1" ]; then
  echo "  ⊘ SKIP_CERTBOT=1,跳过证书申请"
elif [ -d "/etc/letsencrypt/live/${DOMAIN}" ]; then
  echo "  ✓ 证书已存在:/etc/letsencrypt/live/${DOMAIN}(跳过)"
else
  # 7.1 DNS 检查
  RESOLVED_IP=$(dig +short "${DOMAIN}" 2>/dev/null | tail -1)
  if [ -z "$RESOLVED_IP" ]; then
    echo "  ✗ DNS 未解析:${DOMAIN}"
    echo "    请去域名服务商配 A 记录:${DOMAIN} → $(curl -fsS -m 5 http://100.100.100.100/latest/meta-data/public-ipv4 2>/dev/null || echo 'ECS 公网IP')"
    echo "    然后手动跑:sudo certbot --nginx -d ${DOMAIN}"
    echo ""
  else
    echo "  ✓ DNS 已解析:${DOMAIN} → ${RESOLVED_IP}"

    # 7.2 非交互签证书(certbot 自动加 listen 443 + SSL + HTTP→HTTPS redirect)
    # 用 if 直接判断 certbot 退出码(不用 $[?]防 set -e abort)
    if certbot --nginx --non-interactive --agree-tos \
        -m "${SSL_EMAIL}" \
        -d "${DOMAIN}" \
        --redirect; then
      echo "  ✓ HTTPS 已配:https://${DOMAIN}"
    else
      echo "  ✗ certbot 失败(看上面报错)"
      echo "    常见原因:DNS 未传播(等 5-30 分钟) / 80 被云防火墙挡 / 域名写错"
      echo "    手动跑:sudo certbot --nginx -d ${DOMAIN}"
    fi
  fi
fi

# ============ 防火墙(ECS 内部) ============
echo "[+] 配置 ECS 内 firewalld(外部安全组在阿里云控制台)..."
firewall-cmd --permanent --add-service=http 2>/dev/null || true
firewall-cmd --permanent --add-service=https 2>/dev/null || true
firewall-cmd --reload 2>/dev/null || true

echo ""
echo "==================================================="
echo "  部署完成!"
echo "  - API 内部:http://127.0.0.1:8080/api/v1/health"
echo "  - API HTTPS:https://${DOMAIN}/api/v1/health"
echo "  - 日志:journalctl -u paddleocr-api -f"
echo "  - 改 key:edit /etc/paddleocr/api.env && systemctl restart paddleocr-api"
echo ""
echo "  ⚠️ 别忘了:阿里云控制台 → 安全组 → 放行 80/443 端口"
echo "==================================================="