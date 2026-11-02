#!/usr/bin/env bash
# 教师题库系统 · 每日备份脚本
# 装到 ECS:/opt/teacher-bank/deploy/backup.sh
#
# 备份两样东西:
#   1. PostgreSQL 数据库(teacher_question_bank)→ pg_dump | gzip
#   2. 上传的图片 + OCR 历史(/opt/teacher-bank/app/uploads)→ tar.gz
#
# 产物:
#   /opt/teacher-bank/backups/db-<时间戳>.sql.gz
#   /opt/teacher-bank/backups/uploads-<时间戳>.tar.gz
#
# 保留策略:ECS 上留最近 7 天(更早的自动删)
# 本地副本:Mac mini 上每晚 rsync 拉回(见 deploy/teacher-bank/pull-backup.sh)

set -euo pipefail

BACKUP_DIR="/opt/teacher-bank/backups"
DB_NAME="teacher_question_bank"
DB_USER="teacherbank"
UPLOAD_DIR="/opt/teacher-bank/app/uploads"
KEEP_DAYS=7

TS=$(date +%Y%m%d-%H%M%S)

mkdir -p "$BACKUP_DIR"

# === 1. 数据库 ===
# PGPASSWORD 从 systemd 的 EnvironmentFile 读(不写进脚本)
if [ -f /etc/teacherbank/app.env ]; then
    set -a
    # shellcheck disable=SC1091
    source /etc/teacherbank/app.env
    set +a
fi

# 从 DATABASE_URL 里抠出密码(格式 postgresql+psycopg://user:pass@host:port/db)
DB_PASS=$(echo "${DATABASE_URL:-}" | sed -n 's|.*://[^:]*:\([^@]*\)@.*|\1|p')

echo "[1/3] 备份数据库 $DB_NAME ..."
if [ -z "$DB_PASS" ]; then
    echo "  ⚠️ 拿不到数据库密码(检查 /etc/teacherbank/app.env),跳过数据库备份"
else
    PGPASSWORD="$DB_PASS" pg_dump -h 127.0.0.1 -U "$DB_USER" -d "$DB_NAME" \
        | gzip -9 > "$BACKUP_DIR/db-$TS.sql.gz"
    echo "  ✓ db-$TS.sql.gz ($(du -h "$BACKUP_DIR/db-$TS.sql.gz" | cut -f1))"
fi

# === 2. 上传文件 ===
if [ -d "$UPLOAD_DIR" ]; then
    echo "[2/3] 备份上传目录 ..."
    tar -czf "$BACKUP_DIR/uploads-$TS.tar.gz" -C "$(dirname "$UPLOAD_DIR")" "$(basename "$UPLOAD_DIR")" 2>/dev/null
    echo "  ✓ uploads-$TS.tar.gz ($(du -h "$BACKUP_DIR/uploads-$TS.tar.gz" | cut -f1))"
else
    echo "[2/3] 上传目录不存在,跳过"
fi

# === 3. 清理过期 ===
echo "[3/3] 清理 $KEEP_DAYS 天前的备份 ..."
find "$BACKUP_DIR" -type f -name "db-*.sql.gz" -mtime +$KEEP_DAYS -delete 2>/dev/null || true
find "$BACKUP_DIR" -type f -name "uploads-*.tar.gz" -mtime +$KEEP_DAYS -delete 2>/dev/null || true
COUNT=$(ls -1 "$BACKUP_DIR" 2>/dev/null | wc -l | tr -d ' ')
echo "  ✓ 当前保留 $COUNT 个文件"

echo "完成: $(date '+%Y-%m-%d %H:%M:%S')"
