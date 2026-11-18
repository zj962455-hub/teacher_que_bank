#!/usr/bin/env bash
# 部署 · lesson-39（手机号作为账号 + 短信验证码注册）
#
# 用法（在仓库根目录跑）:
#   bash deploy/teacher-bank/deploy-lesson39.sh
#
# 做六件事:
#   1. 后端代码 rsync 到 ECS（迁移文件也要在服务器上）
#   2. 服务器 venv 装阿里云 SDK（rebuild.sh 只 rsync 代码、不装依赖，新包必须单独装）
#   3. 执行 migration 012（users.phone + sms_attempts）
#   4. app.env 补齐短信变量占位（老大手动填值）
#   5. 前端构建 + 部署
#   6. 重启 + 线上验证
#
# 环境变量:
#   ECS_HOST=8.160.177.222   ECS_USER=root   DOMAIN=tqb.lanhu-lab.top

set -euo pipefail

ECS_HOST="${ECS_HOST:-8.160.177.222}"
ECS_USER="${ECS_USER:-root}"
DOMAIN="${DOMAIN:-tqb.lanhu-lab.top}"
APP_ROOT="/opt/teacher-bank"
REPO_DIR="$(cd "$(dirname "$0")/../.." && pwd)"

echo "=============================================="
echo "  部署 lesson-39 · 短信注册 · $DOMAIN · $ECS_HOST"
echo "=============================================="

# === 1. 后端代码 ===
echo "[1/6] 同步后端代码..."
rsync -az --delete --exclude 'venv' --exclude 'node_modules' --exclude '.git' --exclude 'dist' --exclude 'backups' --exclude '__pycache__' --exclude '.env' --exclude 'uploads' "$REPO_DIR/backend/" "$ECS_USER@$ECS_HOST:$APP_ROOT/app/"

# === 2. 服务器装 SDK ===
# ⚠️ rebuild.sh 只 rsync 代码，**不装依赖** —— 新加的包必须在这里补装，
#    否则线上 import 就 ModuleNotFoundError。
#    pip 走阿里云镜像（01-install.sh 配的 /etc/pip.conf），ECS 访问海外 PyPI 会超时。
echo "[2/6] 安装阿里云短信 SDK..."
ssh "$ECS_USER@$ECS_HOST" "sudo -u teacherbank $APP_ROOT/.venv/bin/pip install -q alibabacloud-dypnsapi20170525"
ssh "$ECS_USER@$ECS_HOST" "sudo -u teacherbank $APP_ROOT/.venv/bin/python -c 'import alibabacloud_dypnsapi20170525; print(\"  SDK ok\")'"

# === 3. 迁移 ===
echo "[3/6] 执行 migration 012..."
scp -q "$REPO_DIR/backend/app/migrations/012_add_phone_sms.sql" "$ECS_USER@$ECS_HOST:/tmp/012_add_phone_sms.sql"
# ⚠️ scp 落地是 root 独占的 600 —— postgres 用户读不了（Permission denied），
#    所以这里要放开读权限。/tmp 有 sticky 位，不影响别人改自己的文件。
ssh "$ECS_USER@$ECS_HOST" 'chmod 644 /tmp/012_add_phone_sms.sql'
ssh "$ECS_USER@$ECS_HOST" 'cd /tmp && sudo -u postgres psql -d teacher_question_bank -v ON_ERROR_STOP=1 -f /tmp/012_add_phone_sms.sql' | tail -4

# === 4. app.env 占位 ===
# ⚠️ 只补**空值占位**，不写老大的 AK —— 密钥由老大手动填（老大 2026-11-18 拍板自己填）。
echo "[4/6] 补 app.env 短信变量占位..."
scp -q "$REPO_DIR/deploy/teacher-bank/app.env.sms.example" "$ECS_USER@$ECS_HOST:/tmp/app.env.sms.example"
ssh "$ECS_USER@$ECS_HOST" 'chmod 644 /tmp/app.env.sms.example' && ssh "$ECS_USER@$ECS_HOST" "grep -q ALIYUN_SMS_ACCESS_KEY_ID /etc/teacherbank/app.env || cat /tmp/app.env.sms.example >> /etc/teacherbank/app.env"
ssh "$ECS_USER@$ECS_HOST" 'chown teacherbank:teacherbank /etc/teacherbank/app.env && chmod 600 /etc/teacherbank/app.env'

# === 5. 前端 ===
echo "[5/6] 构建并部署前端..."
cd "$REPO_DIR/frontend"
rm -rf dist
npm run build 2>&1 | grep -E "✓ built|error" | head -3
rsync -az --delete "$REPO_DIR/frontend/dist/" "$ECS_USER@$ECS_HOST:$APP_ROOT/web/"

# === 6. 权限 + 重启 + 验证 ===
echo "[6/6] 修权限 + 重启 + 验证..."
ssh "$ECS_USER@$ECS_HOST" "chown -R teacherbank:teacherbank $APP_ROOT/app && chown -R nginx:nginx $APP_ROOT/web && find $APP_ROOT/web -type d -exec chmod 755 {} + && find $APP_ROOT/web -type f -exec chmod 644 {} + && systemctl restart teacherbank-api.service && sleep 8 && systemctl is-active teacherbank-api.service"
ssh "$ECS_USER@$ECS_HOST" "for p in / /api/questions/ /api/papers/; do printf '  %-20s → %s\n' \"\$p\" \"\$(curl -s -o /dev/null -w '%{http_code}' -H 'Host: $DOMAIN' http://127.0.0.1\$p)\"; done"

echo ""
echo "=============================================="
echo " ✅ lesson-39 已部署"
echo "   https://$DOMAIN/"
echo "   日志: ssh $ECS_USER@$ECS_HOST 'journalctl -u teacherbank-api -f'"
echo ""
echo " ⚠️ 短信还没通 —— 老大手动填这两行再重启即可："
echo "    ssh $ECS_USER@$ECS_HOST"
echo "    sudo vi /etc/teacherbank/app.env"
echo "      ALIYUN_SMS_SIGN_NAME=<控制台赠送签名>"
echo "      ALIYUN_SMS_TEMPLATE_CODE=<控制台赠送模板CODE>"
echo "    sudo chmod 600 /etc/teacherbank/app.env"
echo "    sudo systemctl restart teacherbank-api"
echo ""
echo " 💡 凭据默认走 ECS 实例 RAM 角色（STS 临时凭据，服务器不存密钥）——"
echo "    绑定角色后需要重启实例才生效，步骤见 docs/lesson-39-sms-auth.md 第 8.3 节"
echo "    不想重启的话，就填 ALIYUN_SMS_ACCESS_KEY_ID / _SECRET 走静态 AK"
echo ""
echo " 自测："
echo "    /opt/teacher-bank/.venv/bin/python /opt/teacher-bank/app/scripts/sms_smoke_test.py send 13800138000"
echo "=============================================="