#!/usr/bin/env bash
# 部署 · lesson-42（监管与执法配合工作机制 · 审计导出 + 调阅台账）
#
# 用法（在仓库根目录跑）:
#   bash deploy/teacher-bank/deploy-lesson42.sh
#
# 做四件事:
#   1. 后端代码 rsync 到 ECS
#   2. 执行 migration 016（regulatory_requests 表）
#   3. 修属主 + 重启 teacherbank-api
#   4. 线上验证（首页 + API + 服务状态 + 表已建）
#
# 本次没有新增第三方依赖，不用装 SDK。

set -euo pipefail

ECS_HOST=8.160.177.222
ECS_USER=root
DOMAIN=tqb.lanhu-lab.top
APP_ROOT=/opt/teacher-bank
REPO_DIR=/Users/rrobot/Desktop/dev/teacher_question_bank

echo "=============================================="
echo "  部署 lesson-42 · 监管配合机制 · $DOMAIN"
echo "=============================================="

echo "[1/4] 同步后端代码..."
rsync -az --delete --exclude 'venv' --exclude 'node_modules' --exclude '.git' --exclude 'dist' --exclude 'backups' --exclude '__pycache__' --exclude '.env' --exclude 'uploads' "$REPO_DIR/backend/" "$ECS_USER@$ECS_HOST:$APP_ROOT/app/"

echo "[2/4] 执行 migration 016（regulatory_requests）..."
scp -q "$REPO_DIR/backend/app/migrations/016_add_regulatory_requests.sql" "$ECS_USER@$ECS_HOST:/tmp/016_add_regulatory_requests.sql"
ssh "$ECS_USER@$ECS_HOST" 'chmod 644 /tmp/016_add_regulatory_requests.sql'
ssh "$ECS_USER@$ECS_HOST" 'cd /tmp && sudo -u postgres psql -d teacher_question_bank -v ON_ERROR_STOP=1 -f /tmp/016_add_regulatory_requests.sql' | tail -6

echo "[3/4] 修属主 + 重启服务..."
ssh "$ECS_USER@$ECS_HOST" "chown -R teacherbank:teacherbank $APP_ROOT/app && systemctl restart teacherbank-api.service && sleep 8 && systemctl is-active teacherbank-api.service"

echo "[4/4] 线上验证..."
ssh "$ECS_USER@$ECS_HOST" "for p in / /api/questions/ /api/papers/; do printf '  %-20s -> %s\n' \"\$p\" \"\$(curl -s -o /dev/null -w '%{http_code}' -H 'Host: $DOMAIN' http://127.0.0.1\$p)\"; done"
ssh "$ECS_USER@$ECS_HOST" "sudo -u postgres psql -d teacher_question_bank -t -c \"select count(*) from regulatory_requests;\""

echo ""
echo "=============================================="
echo " ✅ lesson-42 已部署"
echo "   https://$DOMAIN/"
echo "   日志: ssh $ECS_USER@$ECS_HOST 'journalctl -u teacherbank-api -f'"
echo "=============================================="
