#!/usr/bin/env bash
# 部署 · 课 34（灰度试用入口 + 老师反馈收集）
#
# 用法（在仓库根目录跑）:
#   bash deploy/teacher-bank/deploy-lesson34.sh
#
# 做五件事:
#   1. 后端代码 rsync 到 ECS（先同步，再跑迁移 —— 迁移文件也要在服务器上）
#   2. 在服务器上执行 migration 008（幂等：IF NOT EXISTS）
#   3. 回填账号标记：test1 → 管理员；test2 → 共享账号禁改密
#   4. 前端构建 + 部署（照 rebuild.sh 的路径约定）
#   5. 重启 + 线上验证
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
echo " 部署课 34 · $DOMAIN · $ECS_HOST"
echo "=============================================="

# === 1. 后端代码 ===
echo "[1/5] 同步后端代码..."
rsync -az --delete \
  --exclude 'venv' --exclude 'node_modules' --exclude '.git' --exclude 'dist' \
  --exclude 'backups' --exclude '__pycache__' --exclude '.env' --exclude 'uploads' \
  "$REPO_DIR/lesson-02/" "$ECS_USER@$ECS_HOST:$APP_ROOT/app/"

# === 2. 迁移 ===
echo "[2/5] 执行 migration 008..."
scp -q "$REPO_DIR/lesson-02/app/migrations/008_add_invites_feedbacks.sql" \
  "$ECS_USER@$ECS_HOST:/tmp/008_add_invites_feedbacks.sql"
ssh "$ECS_USER@$ECS_HOST" 'sudo -u postgres psql -d teacher_question_bank \
  -v ON_ERROR_STOP=1 -f /tmp/008_add_invites_feedbacks.sql' | tail -5

# === 3. 账号标记 ===
echo "[3/5] 回填账号标记..."
ssh "$ECS_USER@$ECS_HOST" "sudo -u postgres psql -d teacher_question_bank -v ON_ERROR_STOP=1 -c \"
  UPDATE users SET is_admin = true WHERE username = 'test1';
  UPDATE users SET allow_password_change = false WHERE username = 'test2';
  SELECT username, is_admin, allow_password_change, is_active FROM users ORDER BY id;
\""

# === 4. 前端 ===
echo "[4/5] 构建并部署前端..."
cd "$REPO_DIR/lesson-03"
rm -rf dist
npm run build 2>&1 | grep -E "✓ built|error" | head -3
rsync -az --delete "$REPO_DIR/lesson-03/dist/" "$ECS_USER@$ECS_HOST:$APP_ROOT/web/"

# === 5. 权限 + 重启 + 验证 ===
echo "[5/5] 修权限 + 重启 + 验证..."
ssh "$ECS_USER@$ECS_HOST" "chown -R teacherbank:teacherbank $APP_ROOT && \
  find $APP_ROOT/web -type d -exec chmod 755 {} \; && \
  find $APP_ROOT/web -type f -exec chmod 644 {} \; && \
  systemctl restart teacherbank-api.service && sleep 8 && \
  systemctl is-active teacherbank-api.service"

ssh "$ECS_USER@$ECS_HOST" "for p in / /api/questions/ /api/papers/ /api/feedback; do
  printf '  %-20s → %s\n' \"\$p\" \"\$(curl -s -o /dev/null -w '%{http_code}' -H 'Host: $DOMAIN' http://127.0.0.1\$p)\"
done"

echo ""
echo "=============================================="
echo " ✅ 课 34 已部署"
echo "   https://$DOMAIN/"
echo "   管理员: test1   共享试用账号: test2（禁改密）"
echo "=============================================="
