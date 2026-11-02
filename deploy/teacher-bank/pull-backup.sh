#!/usr/bin/env bash
# 教师题库系统 · 从 ECS 拉回备份到本地
# 装在 Mac mini 上: ~/teacher-bank-backup/pull-backup.sh
#
# 作用:ECS 上每天 03:30 生成备份 → 这里每晚 04:00 拉回本地
# 产物: ~/teacher-bank-backups/{db-*.sql.gz, uploads-*.tar.gz}
#
# 设计:
#   - 只在 ECS 上有新备份时才 rsync(避免每次都传)
#   - 本地保留 30 天(比 ECS 的 7 天长 —— 本地才是最终副本)
#   - 拉完做一次 gzip 完整性校验(备份坏了要能发现)

set -euo pipefail

REMOTE_HOST="${REMOTE_HOST:-ecs}"
REMOTE="${REMOTE_HOST}:/opt/teacher-bank/backups/"
LOCAL="${LOCAL_DIR:-$HOME/teacher-bank-backups}"
KEEP_DAYS=30

mkdir -p "$LOCAL"

# === 1. 看 ECS 上最新的备份时间戳 ===
REMOTE_LATEST=$(ssh -o BatchMode=yes -o ConnectTimeout=15 "$REMOTE_HOST" \
    'ls -1t /opt/teacher-bank/backups/ 2>/dev/null | head -1' 2>/dev/null | tr -d '\r\n ')

if [ -z "$REMOTE_LATEST" ]; then
    echo "[1/3] 连不上 ECS 或没有备份,跳过"
    exit 0
fi

# === 2. 本地已有同样的备份? ===
if [ -f "$LOCAL/$REMOTE_LATEST" ]; then
    echo "[1/3] 已有最新备份 $REMOTE_LATEST,无需拉取"
    exit 0
fi

echo "[1/3] 拉取新备份 $REMOTE_LATEST ..."
rsync -az --partial "$REMOTE" "$LOCAL/"

# === 3. 校验 + 清理 ===
echo "[2/3] 校验备份完整性 ..."
FAILED=0
for f in "$LOCAL"/db-*.sql.gz; do
    [ -e "$f" ] || continue
    if ! gunzip -t "$f" 2>/dev/null; then
        echo "  ❌ 损坏: $(basename "$f")"
        FAILED=$((FAILED + 1))
    fi
done
for f in "$LOCAL"/uploads-*.tar.gz; do
    [ -e "$f" ] || continue
    if ! tar -tzf "$f" >/dev/null 2>&1; then
        echo "  ❌ 损坏: $(basename "$f")"
        FAILED=$((FAILED + 1))
    fi
done

if [ "$FAILED" -gt 0 ]; then
    echo "  ⚠️ $FAILED 个备份损坏 —— 建议去 ECS 上手动跑一次 backup.sh 重生成"
else
    echo "  ✓ 全部备份完整"
fi

echo "[3/3] 清理本地 $KEEP_DAYS 天前的旧备份 ..."
find "$LOCAL" -type f \( -name "db-*.sql.gz" -o -name "uploads-*.tar.gz" \) -mtime +$KEEP_DAYS -delete 2>/dev/null || true

COUNT=$(ls -1 "$LOCAL" 2>/dev/null | wc -l | tr -d ' ')
SIZE=$(du -sh "$LOCAL" 2>/dev/null | cut -f1)
echo "  ✓ 本地保留 $COUNT 个文件 · 共 $SIZE"
echo "完成: $(date '+%Y-%m-%d %H:%M:%S')"
