#!/usr/bin/env bash
# 部署 · lesson-43（举报受理闭环 · 公开举报 + 管理员处置）
#
# 做六件事:
#   1. 后端代码 rsync 到 ECS
#   2. 执行 migration 017（reports 表）
#   3. 前端构建（本地）+ rsync dist 到 web 根目录
#   4. 修属主权限（app 归 teacherbank，web 归 nginx）
#   5. 重启 teacherbank-api
#   6. 线上验证（首页 + API + 表已建）
#
# 本次没有新增第三方依赖，不用装 SDK。

set -euo pipefail

ECS_HOST=8.160.177.222
ECS_USER=root
DOMAIN=tqb.lanhu-lab.top
APP_ROOT=/opt/teacher-bank
REPO_DIR=/Users/rrobot/Desktop/dev/teacher_question_bank

echo "=============================================="
echo "  部署 lesson-43 · 举报受理闭环 · $DOMAIN"
echo "=============================================="

echo "[1/6] 同步后端代码..."
rsync -az --delete --exclude 'venv' --exclude 'node_modules' --exclude '.git' --exclude 'dist' --exclude 'backups' --exclude '__pycache__' --exclude '.env' --exclude 'uploads' "$REPO_DIR/backend/" "$ECS_USER@$ECS_HOST:$APP_ROOT/app/"

echo "[2/6] 执行 migration 017（reports）..."
scp -q "$REPO_DIR/backend/app/migrations/017_add_reports.sql" "$ECS_USER@$ECS_HOST:/tmp/017_add_reports.sql"
ssh "$ECS_USER@$ECS_HOST" 'chmod 644 /tmp/017_add_reports.sql'
ssh "$ECS_USER@$ECS_HOST" 'cd /tmp && sudo -u postgres psql -d teacher_question_bank -v ON_ERROR_STOP=1 -f /tmp/017_add_reports.sql' | tail -8

echo "[3/6] 前端构建..."
cd "$REPO_DIR/frontend"
npm run build 2>&1 | grep -E "built in|error" | head -3

echo "[4/6] 同步前端产物..."
rsync -az --delete "$REPO_DIR/frontend/dist/" "$ECS_USER@$ECS_HOST:$APP_ROOT/web/"

echo "[5/6] 修属主 + 重启..."
ssh "$ECS_USER@$ECS_HOST" "chown -R teacherbank:teacherbank $APP_ROOT/app && chown -R nginx:nginx $APP_ROOT/web && find $APP_ROOT/web -type d -exec chmod 755 {} + && find $APP_ROOT/web -type f -exec chmod 644 {} + && systemctl restart teacherbank-api.service && sleep 8 && systemctl is-active teacherbank-api.service"

echo "[6/6] 线上验证..."
ssh "$ECS_USER@$ECS_HOST" "for p in / /api/questions/ /api/papers/; do printf '  %-20s -> %s\n' \"\$p\" \"\$(curl -s -o /dev/null -w '%{http_code}' -H 'Host: $DOMAIN' http://127.0.0.1\$p)\"; done"
ssh "$ECS_USER@$ECS_HOST" "sudo -u postgres psql -d teacher_question_bank -t -c \"select count(*) from reports;\""

echo ""
echo "=============================================="
echo " ✅ lesson-43 已部署"
echo "   https://$DOMAIN/"
echo "   日志: ssh $ECS_USER@$ECS_HOST 'journalctl -u teacherbank-api -f'"
echo "=============================================="
