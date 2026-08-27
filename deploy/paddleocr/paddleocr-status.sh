#!/bin/bash
# PaddleOCR 服务健康检查 · 一键五维度
GREEN='\033[0;32m'; RED='\033[0;31m'; YEL='\033[0;33m'; NC='\033[0m'

echo "======================================="
echo "  PaddleOCR API 健康检查"
echo "======================================="

# 1. systemctl
echo "[1/5] systemctl 状态"
STATE=$(systemctl is-active paddleocr-api 2>/dev/null)
if [ "$STATE" = "active" ]; then
  echo -e "  ✓ $STATE"
else
  echo -e "  ✗ $STATE"
fi
echo ""

# 2. 进程
echo "[2/5] 进程"
if pgrep -f "uvicorn main:app" > /dev/null; then
  PID=$(pgrep -f "uvicorn main:app" | head -1)
  MEM=$(ps -o rss= -p "$PID" 2>/dev/null | awk '{printf "%.0fMB\n", $1/1024}')
  echo -e "  ✓ uvicorn PID=$PID MEM=$MEM"
else
  echo -e "  ✗ uvicorn 进程不在"
fi
echo ""

# 3. 端口
echo "[3/5] 端口 8080"
if ss -tlnp 2>/dev/null | grep -q ":8080"; then
  echo -e "  ✓ 8080 LISTEN"
  ss -tlnp | grep 8080 | sed 's/^/    /'
else
  echo -e "  ✗ 8080 未监听"
fi
echo ""

# 4. 健康检查
echo "[4/5] 健康检查 API"
HEALTH=$(curl -s -m 3 http://127.0.0.1:8080/api/v1/health)
if echo "$HEALTH" | grep -q '"ok"'; then
  echo -e "  ✓ $HEALTH"
else
  echo -e "  ✗ $HEALTH"
fi
echo ""

# 5. 资源
echo "[5/5] 资源占用"
echo "    内存:$(free -h | awk '/^Mem:/ {print $3 "/" $2}')"
echo "    磁盘:$(df -h / | tail -1 | awk '{print $5 " used (" $4 " free)"}')"
echo "    负载:$(cat /proc/loadavg | awk '{print $1, $2, $3}')"
echo ""

# 6. 最近 stderr
echo "[最近 5 行 stderr]"
journalctl -u paddleocr-api -n 5 --no-pager -o cat 2>/dev/null | grep -v '^$' | sed 's/^/    /' | tail -5
echo ""
echo "======================================="