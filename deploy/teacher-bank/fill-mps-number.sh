#!/usr/bin/env bash
# 回填公安备案号 · 一条命令版
#
# 官方《网站备案办事指南》第五步：审核通过后要自己进平台
#   【我的】->【我的网站】->【详情】->【下一步】，
#   点【点击下载备案编号图标】【点击复制备案编号HTML代码】，
#   再把 HTML 代码贴到网站页脚。
#   —— 备案号不会自动发到手上，是要**下载**的。所以这一步必须跑。
#
# 用法:
#   bash deploy/teacher-bank/fill-mps-number.sh 浙公网安备XXXXXXXXXXXXXX号
#
# 做五件事:
#   1. 校验备案号格式（省份简称 + 公网安备 + 14 位数字 + 号）
#   2. 改 site.config.js 的 MPS 常量（备案要改的字段都在那儿）
#   3. 前端构建 + 同步到 ECS（只动静态文件，不重启后端）
#   4. 修属主权限（nginx 要能读）
#   5. 无头验收（验链接 code 是数字 + 图标加载成功 + 无运行时错误）
#
# ⚠️ 只想在本地验一遍不部署？加 --dry-run：
#   bash deploy/teacher-bank/fill-mps-number.sh <号> --dry-run

set -euo pipefail

ECS_HOST=8.160.177.222
ECS_USER=root
APP_ROOT=/opt/teacher-bank
REPO_DIR=/Users/rrobot/Desktop/dev/teacher_question_bank

MPS_ARG=""
DRY_RUN="no"
for a in "$@"; do
  case "$a" in
    --dry-run) DRY_RUN="yes" ;;
    *) MPS_ARG="$a" ;;
  esac
done

if [ -z "$MPS_ARG" ]; then
  echo "用法: bash deploy/teacher-bank/fill-mps-number.sh 浙公网安备XXXXXXXXXXXXXX号 [--dry-run]"
  exit 2
fi

# ---------- 1) 格式校验 ----------
# ⚠️ 别用 grep -E 的中文方括号：[京津沪…] 在 C locale 下按**字节**匹配，
#    3 字节的汉字永远匹配不上单个字符 → 合规的号也会被误拒（今天踩到）。
#    这里改成：字面量 sed 切前缀/数字段，再用 case 逐个省份比对（与 locale 无关）。
echo "===== 1) 校验备案号格式 ====="
PREFIX=$(printf '%s' "$MPS_ARG" | sed -E 's/^([^0-9]*)[0-9]+号$/\1/')
TAIL=$(printf '%s' "$MPS_ARG" | sed -E 's/^[^0-9]*([0-9]+号)$/\1/')

FORMAT_OK="no"
case "$PREFIX" in
  京公网安备|津公网安备|沪公网安备|渝公网安备|冀公网安备|豫公网安备|云公网安备|\
  辽公网安备|黑公网安备|湘公网安备|皖公网安备|鲁公网安备|新公网安备|苏公网安备|\
  浙公网安备|赣公网安备|鄂公网安备|桂公网安备|甘公网安备|晋公网安备|蒙公网安备|\
  陕公网安备|吉公网安备|闽公网安备|贵公网安备|粤公网安备|藏公网安备|青公网安备|\
  川公网安备|宁公网安备|琼公网安备)
    if printf '%s' "$TAIL" | grep -qE '^[0-9]{14}号$'; then
      FORMAT_OK="yes"
    fi
    ;;
esac

if [ "$FORMAT_OK" != "yes" ]; then
  echo "❌ 备案号格式不对: $MPS_ARG"
  echo "   期望形如: 浙公网安备XXXXXXXXXXXXXX号"
  echo "   （省份简称 + 公网安备 + 14 位数字 + 号）"
  echo "   实际解析: 前缀=[$PREFIX] 数字段=[$TAIL]"
  exit 1
fi
CODE=$(printf '%s' "$TAIL" | sed 's/号$//')
echo "  ✅ 格式正确"
echo "  备案号: $MPS_ARG"
echo "  查询 code: $CODE   ← 公安查询链接只用这段数字"

# ---------- 2) 改 site.config.js ----------
echo "===== 2) 写入 site.config.js ====="
cd "$REPO_DIR"
python3 - "$MPS_ARG" <<'PYEOF'
import io
import re
import sys

mps = sys.argv[1]
p = "frontend/src/site.config.js"
s = io.open(p, encoding="utf-8").read()

new, n = re.subn(
    r"^export const MPS = '[^']*'.*$",
    "export const MPS = '" + mps + "'",
    s,
    count=1,
    flags=re.M,
)
if n == 0:
    raise SystemExit("!! 没找到 export const MPS = 这一行")
io.open(p, "w", encoding="utf-8").write(new)
print("  已写入: export const MPS = '" + mps + "'")
PYEOF
grep -n "^export const MPS = " frontend/src/site.config.js

if [ "$DRY_RUN" = "yes" ]; then
  echo ""
  echo "===== --dry-run：到此为止，不部署 ====="
  echo "  本地构建 + 无头验收可手动跑："
  echo "    cd frontend && npm run build"
  echo "    EXPECT_MPS=<真实备案号> node scripts/verify-beian-footer.cjs"
  exit 0
fi

# ---------- 3) 构建 + 同步 ----------
echo "===== 3) 构建 + 同步到 ECS ====="
cd "$REPO_DIR/frontend"
npm run build 2>&1 | grep -E "built in|error" | head -3
rsync -az --delete "$REPO_DIR/frontend/dist/" "$ECS_USER@$ECS_HOST:$APP_ROOT/web/"

# ---------- 4) 修权限（nginx 要能读） ----------
echo "===== 4) 修属主权限 ====="
ssh "$ECS_USER@$ECS_HOST" "chown -R nginx:nginx $APP_ROOT/web && find $APP_ROOT/web -type d -exec chmod 755 {} + && find $APP_ROOT/web -type f -exec chmod 644 {} + && echo '  权限已修'"

# ---------- 5) 无头验收 ----------
echo "===== 5) 无头验收（线上真实页面） ====="
cd "$REPO_DIR/frontend"
EXPECT_MPS="$MPS_ARG" node scripts/verify-beian-footer.cjs

echo ""
echo "=============================================="
echo " ✅ 公安备案号已回填并上线"
echo "   https://tqb.lanhu-lab.top/"
echo "   公安查询: https://beian.mps.gov.cn/#/query/webSearch?code=$CODE"
echo "=============================================="
