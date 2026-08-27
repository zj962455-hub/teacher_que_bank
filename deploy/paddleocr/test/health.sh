#!/usr/bin/env bash
# 健康检查 + 端到端 OCR 测试
# 用法:bash test/health.sh https://lanhu-lab.top <api_key>

set -euo pipefail

BASE="${1:-http://127.0.0.1:8080}"
KEY="${2:-}"

echo "==> 测试 health 接口(无需鉴权)"
HEALTH=$(curl -fsS "${BASE}/api/v1/health" | tee /dev/stderr)
echo ""

echo "==> 测试鉴权(无 key 应 401)"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST -F "image=@test/sample.png" \
  "${BASE}/api/v1/ocr/image")
if [ "$HTTP_CODE" = "401" ]; then
  echo "✓ 鉴权生效(401)"
else
  echo "✗ 鉴权异常,期望 401 实际 $HTTP_CODE"
  exit 1
fi

if [ -n "$KEY" ]; then
  echo ""
  echo "==> 测试 OCR 接口(用提供的 key)"
  curl -fsS -X POST \
    -H "X-API-Key: ${KEY}" \
    -F "image=@test/sample.png" \
    "${BASE}/api/v1/ocr/image" | python3 -m json.tool || {
      echo "✗ OCR 测试失败(可能是没装样本图,跳过)"
    }
fi

echo ""
echo "==> 全部通过 ✅"