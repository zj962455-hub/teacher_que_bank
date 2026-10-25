#!/usr/bin/env bash
# 增量更新脚本 · teacher-question-bank
#
# 用法（在本机跑，会自动 rsync 到 ECS）:
#   bash rebuild.sh
#
# 做四件事:
#   1. rsync 代码到 ECS
#   2. 重启 systemd 服务
#   3. 修静态文件权限（nginx 要能读）
#   4. 验证服务活着
#
# 环境变量:
#   ECS_HOST=8.160.177.222
#   ECS_USER=root
#   DOMAIN=tqb.lanhu-lab.top

set -euo pipefail

ECS_HOST="${ECS_HOST:-8.160.177.222}"
ECS_USER="${ECS_USER:-root}"
DOMAIN="${DOMAIN:-tqb.lanhu-lab.top}"
APP_ROOT="/opt/teacher-bank"
REPO_DIR="$(cd "$(dirname "$0")/../.." && pwd)"

echo "=============================================="
echo " 增量更新 · $DOMAIN · $ECS_HOST"
echo "=============================================="

# === 1. 前端构建（本地，避开 ECS 内存压力）===
echo "[1/5] 前端构建..."
cd "$REPO_DIR/lesson-03"
rm -rf dist
npm run build 2>&1 | grep -E "✓ built|error" | head -3

# === 2. rsync ===
echo "[2/5] 同步代码到 ECS..."
rsync -az --delete \
  --exclude 'venv' --exclude 'node_modules' --exclude '.git' --exclude 'dist' \
  --exclude 'backups' --exclude '__pycache__' --exclude '.env' --exclude 'uploads' \
  "$REPO_DIR/lesson-02/" "$ECS_USER@$ECS_HOST:$APP_ROOT/app/"

rsync -az --delete \
  --exclude 'node_modules' --exclude '.git' --exclude 'dist' \
  --exclude '__pycache__' --exclude '.env*' \
  "$REPO_DIR/lesson-03/" "$ECS_USER@$ECS_HOST:$APP_ROOT/frontend/"

rsync -az --delete "$REPO_DIR/lesson-03/dist/" "$ECS_USER@$ECS_HOST:$APP_ROOT/web/"

# === 3. 权限 ===
echo "[3/5] 修权限（nginx 要能读静态文件）..."
ssh "$ECS_USER@$ECS_HOST" "chown -R teacherbank:teacherbank $APP_ROOT && \
  find $APP_ROOT/web -type d -exec chmod 755 {} \; && \
  find $APP_ROOT/web -type f -exec chmod 644 {} \;"

# === 4. 重启 ===
echo "[4/5] 重启服务..."
ssh "$ECS_USER@$ECS_HOST" "systemctl restart teacherbank-api.service && sleep 8 && \
  systemctl is-active teacherbank-api.service"

# === 5. 验证 ===
echo "[5/5] 验证..."
ssh "$ECS_USER@$ECS_HOST" "for p in / /api/questions/ /api/papers/; do
  printf '  %-20s → %s\n' \"\$p\" \"\$(curl -s -o /dev/null -w '%{http_code}' -H 'Host: $DOMAIN' http://127.0.0.1\$p)\"
done"

echo ""
echo "=============================================="
echo " ✅ 更新完成"
echo "   https://$DOMAIN/"
echo "   日志: ssh $ECS_USER@$ECS_HOST 'journalctl -u teacherbank-api -f'"
echo "=============================================="
