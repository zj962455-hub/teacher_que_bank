#!/usr/bin/env bash
# PaddleOCR 重装脚本（代码目录被删后恢复）
# 用法:scp 到 ECS 后,bash reinstall-paddleocr.sh
#
# ⚠️ 重要前提
#   1. 不碰 certbot —— 备案还在审核,HTTP-01 验证会被 Beaver 拦,还可能弄坏现有证书
#   2. 不碰 nginx 配置 —— teacherbank.conf 在同目录,覆盖了会挂掉题库
#   3. 不删 /etc/paddleocr/api.env —— API key 在里面,删了题库那边要改配置
#   4. 用 python3.11 —— 跟当前跑着的进程一致(rebuild.sh 里说的 3.10 是历史方案)
#
# 预计耗时:依赖 5-10 分钟 + 模型首启 10-20 分钟(300MB 自动下载)

set -euo pipefail

APP_DIR="/opt/paddleocr"
APP_USER="paddleocr"
PY_BIN="python3.11"

echo "=============================================="
echo " PaddleOCR 重装"
echo "=============================================="

# === 0. 前置检查 ===
echo "[0/7] 前置检查..."
if [ ! -d "$APP_DIR/app" ]; then
  echo "  ❌ $APP_DIR/app 不存在(代码没传上来)"; exit 1
fi
if [ ! -f /etc/paddleocr/api.env ]; then
  echo "  ❌ /etc/paddleocr/api.env 不存在 —— API key 没了,别继续!"; exit 1
fi
echo "  ✓ 代码就位"
echo "  ✓ api.env 保留(key 不变,题库那边不用改)"

# pip 阿里云镜像(ECS 访问海外 PyPI 超时)
cat > /etc/pip.conf <<'EOF'
[global]
index-url = https://mirrors.aliyun.com/pypi/simple/
trusted-host = mirrors.aliyun.com
timeout = 60
EOF

# === 1. Python 版本 ===
echo "[1/7] Python..."
$PY_BIN --version 2>&1 | head -1 || {
  echo "  安装 python3.11..."
  dnf install -y -q python3.11 python3.11-devel
}

# === 2. 目录权限 ===
echo "[2/7] 目录权限..."
mkdir -p "$APP_DIR" "$APP_DIR/app"
mkdir -p /var/log/paddleocr-api
chown -R "$APP_USER:$APP_USER" "$APP_DIR" /var/log/paddleocr-api
sudo -u "$APP_USER" mkdir -p "/home/$APP_USER/.cache/pip"
echo "  ✓ 权限就绪"

# === 3. venv ===
echo "[3/7] 创建 venv..."
if [ ! -d "$APP_DIR/.venv" ]; then
  $PY_BIN -m venv "$APP_DIR/.venv"
  chown -R "$APP_USER:$APP_USER" "$APP_DIR/.venv"
fi
echo "  ✓ venv 就绪"

# === 4. 依赖 ===
echo "[4/7] 安装依赖(阿里云镜像,5-10 分钟)..."
sudo -u "$APP_USER" "$APP_DIR/.venv/bin/pip" install -q --upgrade pip wheel setuptools
sudo -u "$APP_USER" "$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/app/requirements.txt" 2>&1 | tail -6

# === 5. 依赖自检 ===
echo "[5/7] 依赖自检..."
sudo -u "$APP_USER" "$APP_DIR/.venv/bin/python" -c "
import paddleocr, paddle, numpy, cv2, fastapi
print(f'  ✓ paddleocr {paddleocr.__version__}')
print(f'  ✓ paddle {paddle.__version__}')
print(f'  ✓ numpy {numpy.__version__} (必须 <2.0)')
print(f'  ✓ opencv {cv2.__version__} (必须 <4.8)')
import pyclipper
print('  ✓ pyclipper 编译成功')
" || { echo "  ❌ 依赖自检失败 —— 可能是 pyclipper 在 3.11 编译不过"; exit 1; }

# === 6. 切换服务 ===
echo "[6/7] 重启服务(首次启动会自动下模型 300MB,慢)..."
systemctl stop paddleocr-api.service
sleep 2
systemctl start paddleocr-api.service
echo "  等待模型下载 + 加载(10-20 分钟)..."
for i in $(seq 1 40); do
  sleep 30
  CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 http://127.0.0.1:8080/api/v1/health 2>/dev/null || echo 000)
  echo "    [$((i*30))s] health → $CODE"
  if [ "$CODE" = "200" ]; then
    echo "  ✓ 服务健康!"
    curl -s http://127.0.0.1:8080/api/v1/health; echo ""
    break
  fi
done

# === 7. 验证 ===
echo "[7/7] 最终验证..."
systemctl status paddleocr-api.service --no-pager | head -8
echo ""
echo "--- stderr 尾部 ---"
tail -8 /var/log/paddleocr-api/stderr.log 2>/dev/null
echo ""
echo "--- 端到端 OCR 测试 ---"
if [ -f "$APP_DIR/app/test/ocr-test.sh" ]; then
  bash "$APP_DIR/app/test/ocr-test.sh" 2>&1 | tail -10
else
  echo "  (测试脚本在 deploy/paddleocr/test/,需单独传)"
fi
echo ""
echo "=============================================="
echo " ✅ 重装完成"
echo "   健康检查: curl http://127.0.0.1:8080/api/v1/health"
echo "   日志:     journalctl -u paddleocr-api -f"
echo "   题库侧:   curl -X POST http://127.0.0.1:8000/api/ocr/ ..."
echo "=============================================="
