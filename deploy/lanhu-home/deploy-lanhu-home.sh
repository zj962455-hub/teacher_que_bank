#!/usr/bin/env bash
# 部署 lanhu-lab.top（一级域名）静态首页
#
# 用法（本机跑）:
#   bash deploy/lanhu-home/deploy-lanhu-home.sh
#
# 环境变量:
#   ECS_HOST=8.160.177.222   ECS_USER=root
#
# 四步:
#   1. 本地渲染（从 site.config.js + .env.local 取备案信息）
#   2. rsync 到服务器 /opt/lanhu-home（nginx 属主、755/644）
#   3. 打 nginx 补丁（自带备份 + nginx -t 失败自动回滚）并 reload
#   4. 验证：首页 200 + 含站名/备案号 + OCR 接口与题库站不受影响

set -euo pipefail

ECS_HOST="${ECS_HOST:-8.160.177.222}"
ECS_USER="${ECS_USER:-root}"
REMOTE_DIR="/opt/lanhu-home"
BUILD_DIR="${BUILD_DIR:-/tmp/lanhu-home-build}"
REPO_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
HERE="$REPO_DIR/deploy/lanhu-home"

echo "=============================================="
echo "  一级域名首页 · lanhu-lab.top · $ECS_HOST"
echo "=============================================="

echo "[1/4] 本地渲染..."
python3 "$HERE/render.py" "$BUILD_DIR"

echo "[2/4] 同步到服务器..."
ssh "$ECS_USER@$ECS_HOST" "install -d -m 755 -o nginx -g nginx $REMOTE_DIR"
rsync -az --delete "$BUILD_DIR/" "$ECS_USER@$ECS_HOST:$REMOTE_DIR/"
ssh "$ECS_USER@$ECS_HOST" "chown -R nginx:nginx $REMOTE_DIR && \
  find $REMOTE_DIR -type d -exec chmod 755 {} + && \
  find $REMOTE_DIR -type f -exec chmod 644 {} +"

echo "[3/4] 打 nginx 补丁并 reload..."
scp -q "$HERE/patch_nginx.py" "$ECS_USER@$ECS_HOST:/tmp/patch_nginx.py"
ssh "$ECS_USER@$ECS_HOST" "python3 /tmp/patch_nginx.py && nginx -s reload && rm -f /tmp/patch_nginx.py"

echo "[4/4] 验证..."
# ⚠️ 页面正文落临时文件再 grep —— 不要用「echo "$BODY" | grep -q」：
#    grep -q 命中即退出，管道另一端收到 SIGPIPE；脚本开了 pipefail 时
#    整条管道退出码变成 141，&& 分支会被判成 FAIL（假阴性）。
TMP_HTML="$(mktemp -t lanhu-home-XXXXXX.html)"
trap 'rm -f "$TMP_HTML"' EXIT
curl -sS --max-time 15 https://lanhu-lab.top/ -o "$TMP_HTML"
CODE="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 15 https://lanhu-lab.top/)"
OCR="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 15 https://lanhu-lab.top/api/v1/health)"
TQB="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 15 https://tqb.lanhu-lab.top/)"

echo "  首页            : $CODE"
echo "  OCR 健康检查    : $OCR"
echo "  题库站          : $TQB"

check() {
  local label="$1" pattern="$2"
  if grep -qE "$pattern" "$TMP_HTML"; then
    echo "  $label : OK"
  else
    echo "  $label : FAIL"
    exit 1
  fi
}
check "含站名「蓝狐网」" '蓝狐网'
check "含工信部备案号" '浙ICP备[0-9]+号-[0-9]+'
check "备案号链工信部" 'beian\.miit\.gov\.cn'
check "含举报入口" '12377'

[ "$CODE" = "200" ] || { echo "首页不是 200，部署判定失败"; exit 1; }
[ "$OCR" = "200" ] || { echo "OCR 接口被影响，部署判定失败"; exit 1; }
[ "$TQB" = "200" ] || { echo "题库站被影响，部署判定失败"; exit 1; }

echo
echo "部署完成: https://lanhu-lab.top/"
