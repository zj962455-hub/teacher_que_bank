#!/usr/bin/env bash
# 回填公安备案号 / 主体信息 —— 一条命令版
#
# 官方《网站备案办事指南》第五步：审核通过后要自己进平台
#   【我的】 -> 【我的网站】 -> 【详情】 -> 【下一步】
#   点【点击下载备案编号图标】【点击复制备案编号HTML代码】，
#   再把 HTML 代码贴到网站页脚。
#   —— 备案号不会自动发到手上，是要**下载**的。所以这一步必须跑。
#
# 用法：
#   bash deploy/teacher-bank/fill-mps-number.sh 浙公网安备XXXXXXXXXXXXXX号
#   bash deploy/teacher-bank/fill-mps-number.sh --operator "公司全称" --contact "13800000000"
#   bash deploy/teacher-bank/fill-mps-number.sh 浙公网安备XXXXXXXXXXXXXX号 --dry-run
#
# ⚠️ --dry-run **不写文件、不构建、不部署**，只做格式校验 + 预演。
#    （2026-11-19 修：老版本 dry-run 会先把号写进 site.config.js 再退出，
#     等于把样例号留在仓库里 —— 差点真上线一个假备案号。）

set -euo pipefail

ECS_HOST=8.160.177.222
ECS_USER=root
APP_ROOT=/opt/teacher-bank
REPO_DIR=/Users/rrobot/Desktop/dev/teacher_question_bank

MPS_ARG=""
OPERATOR_ARG=""
CONTACT_ARG=""
DRY_RUN="no"

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN="yes"; shift ;;
    --operator)
      if [ $# -lt 2 ]; then echo "--operator 后面要跟值"; exit 2; fi
      OPERATOR_ARG="$2"; shift 2 ;;
    --contact)
      if [ $# -lt 2 ]; then echo "--contact 后面要跟值"; exit 2; fi
      CONTACT_ARG="$2"; shift 2 ;;
    -*) echo "未知参数: $1"; echo "用法见本脚本头部"; exit 2 ;;
    *) MPS_ARG="$1"; shift ;;
  esac
done

if [ -z "$MPS_ARG" ] && [ -z "$OPERATOR_ARG" ] && [ -z "$CONTACT_ARG" ]; then
  echo "用法: bash deploy/teacher-bank/fill-mps-number.sh 浙公网安备XXXXXXXXXXXXXX号 [--dry-run]"
  echo "      [--operator 主办单位全称] [--contact 应急联系电话/邮箱]"
  exit 2
fi

# 读出 site.config.js 里三个字段的**当前真实值**
# 用途：验收脚本的期望值必须跟线上实际渲染的一致，
#      否则「只改主体信息」时，验收会拿旧的空值去对，白报失败。
read_site_cfg() {
  python3 - "$REPO_DIR/frontend/src/site.config.js" "$REPO_DIR/frontend/.env.local" <<'PYEOF'
import io
import os
import re
import shlex
import sys

cfg_path, env_path = sys.argv[1], sys.argv[2]

# MPS：公开的备案号，在 site.config.js（入库文件）
s = io.open(cfg_path, encoding="utf-8").read()
m = re.search(r"^export const MPS = '([^']*)'", s, flags=re.M)
print("CFG_MPS=" + shlex.quote(m.group(1) if m else ""))

# OPERATOR / CONTACT：个人信息，在 .env.local（不入库）
env = io.open(env_path, encoding="utf-8").read() if os.path.exists(env_path) else ""
for name, key in (("OPERATOR", "VITE_OPERATOR"), ("CONTACT", "VITE_CONTACT")):
    m = re.search(r"^" + key + r"=(.*)$", env, flags=re.M)
    print("CFG_" + name + "=" + shlex.quote(m.group(1).strip() if m else ""))
PYEOF
}

CODE=""
if [ -n "$MPS_ARG" ]; then
  echo "===== 1) 校验备案号格式 ====="
  # ⚠️ 别用 grep -E 的中文方括号：[京津沪…] 在 C locale 下按**字节**匹配，
  #    3 字节的汉字永远匹配不上单个字符 → 合规的号也会被误拒（今天踩到）。
  #    这里改成：字面量 sed 切前缀/数字段，再用 case 逐个省份比对（与 locale 无关）。
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
else
  echo "===== 1) 跳过备案号校验（本次只改主体信息） ====="
fi

echo "===== 2) 写入 site.config.js ====="
cd "$REPO_DIR"

if [ "$DRY_RUN" = "yes" ]; then
  echo "  --dry-run：**不写文件**，以下只是将要写入的内容："
  echo "    MPS      = $MPS_ARG"
  echo "    OPERATOR = $OPERATOR_ARG"
  echo "    CONTACT  = $CONTACT_ARG"
  echo "  真正写入请去掉 --dry-run 再跑一次。"
  exit 0
fi

python3 "$REPO_DIR/deploy/teacher-bank/_set_site_fields.py" \
  "$MPS_ARG" "$OPERATOR_ARG" "$CONTACT_ARG" \
  "$REPO_DIR/frontend/src/site.config.js"
echo "  site.config.js（入库 · 公开信息）："
grep -n "^export const MPS = " "$REPO_DIR/frontend/src/site.config.js"
echo "  .env.local（不入库 · 个人信息）："
grep -nE "^VITE_(OPERATOR|CONTACT)=" "$REPO_DIR/frontend/.env.local" 2>/dev/null || echo "    （还没有 .env.local）"

eval "$(read_site_cfg)"
echo "  写入后当前值：MPS=[$CFG_MPS] OPERATOR=[$CFG_OPERATOR] CONTACT=[$CFG_CONTACT]"

# ---------- 3) 构建 + 同步 ----------
echo "===== 3) 构建 + 同步到 ECS ====="
cd "$REPO_DIR/frontend"
npm run build 2>&1 | grep -E "built in|error" | head -3
rsync -az --delete "$REPO_DIR/frontend/dist/" "$ECS_USER@$ECS_HOST:$APP_ROOT/web/"

# ---------- 4) 修权限（nginx 要能读） ----------
echo "===== 4) 修属主权限 ====="
ssh "$ECS_USER@$ECS_HOST" "chown -R nginx:nginx $APP_ROOT/web && find $APP_ROOT/web -type d -exec chmod 755 {} + && find $APP_ROOT/web -type f -exec chmod 644 {} + && echo '  权限已修'"

# ---------- 5) 无头验收（用**写入后的真实值**做期望值） ----------
echo "===== 5) 无头验收（线上真实页面） ====="
cd "$REPO_DIR/frontend"
EXPECT_MPS="$CFG_MPS" node scripts/verify-beian-footer.cjs
EXPECT_MPS="$CFG_MPS" EXPECT_OPERATOR="$CFG_OPERATOR" EXPECT_CONTACT="$CFG_CONTACT" \
  node scripts/verify-privacy-public.cjs

echo ""
echo "=============================================="
echo " ✅ 备案信息已回填并上线"
echo "   https://tqb.lanhu-lab.top/"
if [ -n "$CODE" ]; then
  echo "   公安查询: https://beian.mps.gov.cn/#/query/webSearch?code=$CODE"
fi
echo "=============================================="
