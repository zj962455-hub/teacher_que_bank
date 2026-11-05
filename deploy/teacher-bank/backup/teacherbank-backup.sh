#!/usr/bin/env bash
# 教培题库 · 每日自动备份
#
# 背景(2026-11-05 心跳自检发现):
#   之前唯一的备份是 11-03 迁移前的一次性手工 dump ——
#   只有 3 张表(paper_questions/papers/questions),线上实际 9 张,
#   users/sessions/uploads/tags/categories/question_tags 一行都没有;
#   其中一个 dump 还是 0 字节(失败的)。11-03 之后新增的数据全无备份。
#
# 本脚本做两件事:
#   1. pg_dump 全库(pg_dump -Fc 自定义格式,支持并行恢复)
#   2. 打包 uploads/ 目录(上传的图片不在数据库里,必须单独备)
# 保留 14 天,旧的自动清理。
#
# 装到 root crontab: 17 4 * * * /usr/local/bin/teacherbank-backup.sh >> /var/log/teacherbank-backup.log 2>&1
set -euo pipefail

APP_ROOT=/opt/teacher-bank
BAK_DIR="$APP_ROOT/backups"
KEEP_DAYS=14
ENV_FILE=/etc/teacherbank/app.env
TS="$(date +%Y%m%d-%H%M%S)"

mkdir -p "$BAK_DIR"

# ---- 从 app.env 取连接参数(不打印密码)----
set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a
URL="${DATABASE_URL#postgresql+psycopg://}"
URL="${URL#postgresql://}"

DB_USER="${URL%%:*}"
REST="${URL#*:}"
DB_PASS="${REST%%@*}"
HOSTPORT="${REST#*@}"
HOSTPORT="${HOSTPORT%%/*}"
DB_NAME="${REST##*/}"
DB_NAME="${DB_NAME%%\?*}"
DB_HOST="${HOSTPORT%%:*}"
DB_PORT="${HOSTPORT##*:}"

export PGPASSWORD="$DB_PASS"

# ---- 1. 数据库全量 ----
DB_FILE="$BAK_DIR/db-$TS.dump"
pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -Fc -f "$DB_FILE"

# ---- 2. uploads 目录 ----
UP_FILE="$BAK_DIR/uploads-$TS.tar.gz"
if [ -d "$APP_ROOT/app/uploads" ]; then
  tar -czf "$UP_FILE" -C "$APP_ROOT/app" uploads
else
  echo "warn: $APP_ROOT/app/uploads 不存在,跳过"
fi

# ---- 3. 权限 + 保留策略 ----
chmod 600 "$DB_FILE" 2>/dev/null || true
[ -f "$UP_FILE" ] && chmod 600 "$UP_FILE" 2>/dev/null || true

find "$BAK_DIR" -name 'db-*.dump'      -type f -mtime "+$KEEP_DAYS" -delete
find "$BAK_DIR" -name 'uploads-*.tar.gz' -type f -mtime "+$KEEP_DAYS" -delete
# 清掉 0 字节的坏 dump(失败遗留),避免以后误判成有效备份
find "$BAK_DIR" -type f -size 0 -delete

echo "backup done: $(basename "$DB_FILE") ($(stat -c%s "$DB_FILE") bytes)"
