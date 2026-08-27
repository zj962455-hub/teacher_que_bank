#!/bin/bash
# 重建 venv 切到 Python 3.10(pyclipper 在 3.10 上稳定)
# 用法:scp 到 ECS 后,bash rebuild.sh
set -e

echo "=== 1/5 装 python3.10 ==="
dnf install -y python3.10 python3.10-devel 2>&1 | tail -3

echo "=== 2/5 停服务 ==="
systemctl stop paddleocr-api

echo "=== 3/5 删旧 venv + 用 python3.10 建新 venv ==="
rm -rf /opt/paddleocr/.venv
python3.10 -m venv /opt/paddleocr/.venv
chown -R paddleocr:paddleocr /opt/paddleocr/.venv

echo "=== 4/5 重装 pip 依赖(从阿里云镜像) ==="
sudo -u paddleocr /opt/paddleocr/.venv/bin/pip install --upgrade pip wheel setuptools 2>&1 | tail -3
sudo -u paddleocr /opt/paddleocr/.venv/bin/pip install -r /opt/paddleocr/app/requirements.txt 2>&1 | tail -8

echo "=== 5/5 测试 pyclipper(应该 OK) ==="
sudo -u paddleocr /opt/paddleocr/.venv/bin/python3.10 -c 'import pyclipper; print("pyclipper python3.10 OK")'

echo "=== 6/5 重启服务 + 健康检查 ==="
systemctl start paddleocr-api
sleep 15
curl -s http://127.0.0.1:8080/api/v1/health
echo ""
echo "=== 7/5 看 stderr 是否有错 ==="
tail -10 /var/log/paddleocr-api/stderr.log

echo "=== DONE ==="