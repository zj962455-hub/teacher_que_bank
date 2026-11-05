#!/usr/bin/env bash
# 教培题库 · 备份恢复演练
#
# 用途(2026-11-05 备案要求):
#   证明备份**真的能恢复** —— 不是「有文件」,是「恢复出来数据对得上」。
#   演练完自动删掉临时库,线上库不受影响。
#
# 做的事:
#   1. 校验最新 dump 的 TOC(表清单)
#   2. 建临时库 → pg_restore → 逐表比对行数(线上 vs 恢复出来的)
#   3. 删临时库
#
# 用法: teacherbank-restore-drill.sh [dump文件路径]
#   不给参数就用 backups/ 里最新的 db-*.dump
#
# 实现说明(两处坑):
#   a. 不用 `--schema` 临时 schema 方案:pg_dump 出来的对象显式带 public 限定,
#      pg_restore --schema <别的schema> 会把它们全过滤掉(表根本没建),
#      结果永远是「恢复 0 行」—— 那不是备份坏,是演练方法错了。
#   b. 临时库不能用应用账号从 TCP 连:pg_hba 只对 teacher_question_bank 这个库
#      配了 scram-sha-256,其它库落到 ident 规则 → "Ident authentication failed"。
#      所以临时库的 restore/计数一律用 postgres 超级用户走 local peer。
set -uo pipefail

ENV_FILE=/etc/teacherbank/app.env
set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a

# ---- 解析 DATABASE_URL(与备份脚本同一套逻辑)----
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

TABLES="users sessions uploads tags categories question_tags questions papers paper_questions"

if [ $# -ge 1 ]; then
  DUMP="$1"
else
  DUMP=$(ls -t /opt/teacher-bank/backups/db-*.dump 2>/dev/null | head -1)
fi
[ -f "$DUMP" ] || { echo "❌ 找不到 dump"; exit 1; }

TMPDB="restore_drill_$(date +%H%M%S)"
# postgres 要能读 dump:复制一份到 backups/ 并给 postgres 组读权限
COPY="/opt/teacher-bank/backups/.drill-$(basename "$DUMP")"
cp "$DUMP" "$COPY"
chgrp postgres "$COPY" 2>/dev/null || true
chmod 640 "$COPY"
cleanup_copy() { rm -f "$COPY"; }
trap cleanup_copy EXIT

echo "=== ① 校验 dump ==="
echo "  文件: $DUMP  ($(stat -c%s "$DUMP") bytes)"
echo "  TOC 表清单:"
pg_restore -l "$DUMP" 2>/dev/null | grep "TABLE DATA" | sed -E 's/.*TABLE DATA public ([a-z_]+) .*/    \1/' | sort | tr '\n' ' '
echo
echo "  TOC 数据条目数: $(pg_restore -l "$DUMP" 2>/dev/null | grep -c 'TABLE DATA')"

echo
echo "=== ② 恢复演练(临时库 $TMPDB) ==="
if ! su - postgres -c "createdb -O $DB_USER $TMPDB" 2>/dev/null; then
  echo "  ❌ 建临时库失败(需要 postgres 超级用户 createdb 权限)"
  exit 1
fi
echo "  临时库已建: $TMPDB (owner=$DB_USER)"

echo "  --- pg_restore ---"
su - postgres -c "pg_restore -d $TMPDB $COPY" 2>&1 \
  | grep -viE "^$|warning: errors ignored on restore" | head -8
echo "  (restore 完成)"

echo
echo "=== ③ 逐表行数比对(线上 vs 恢复) ==="
printf "  %-18s %8s %8s  %s\n" "表" "线上" "恢复" ""
FAIL=0
for t in $TABLES; do
  live=$(psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -tAc \
    "select count(*) from public.$t" 2>/dev/null | tr -d ' ')
  rest=$(su - postgres -c "psql -d $TMPDB -tAc 'select count(*) from public.$t'" 2>/dev/null | tr -d ' ')
  [ -z "$rest" ] && rest="-"
  ok="✅"
  if [ "$live" != "$rest" ]; then ok="❌"; FAIL=1; fi
  printf "  %-18s %8s %8s  %s\n" "$t" "${live:-?}" "${rest:-?}" "$ok"
done

echo
echo "=== ④ 清理 ==="
su - postgres -c "dropdb --if-exists $TMPDB" 2>/dev/null && echo "  临时库已删除" || echo "  ⚠️ 临时库清理失败,请手动 dropdb $TMPDB"

echo
if [ "$FAIL" = "0" ]; then
  echo "✅ 演练通过:9 张表行数全部一致,备份可恢复"
else
  echo "❌ 演练失败:有表行数不一致"
fi
exit "$FAIL"
