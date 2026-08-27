#!/usr/bin/env bash
# 端到端 OCR 测试 · 拿真实题目图测试
# 用法:
#   bash test/ocr-test.sh https://lanhu-lab.top <api_key> /path/to/test.jpg

set -euo pipefail

BASE="${1:?用法: $0 <base_url> <api_key> <image_path>}"
KEY="${2:?}"
IMG="${3:?需要提供图片路径}"

echo "==> 测试图片:${IMG}"
ls -lh "$IMG"

echo ""
echo "==> POST /api/v1/ocr/image ..."
curl -fsS -X POST \
  -H "X-API-Key: ${KEY}" \
  -F "image=@${IMG}" \
  "${BASE}/api/v1/ocr/image" | tee /tmp/ocr-response.json | python3 -m json.tool

echo ""
echo "==> 耗时 + 块数"
python3 -c "
import json
d = json.load(open('/tmp/ocr-response.json'))
print(f\"blocks: {len(d['blocks'])}\")
print(f\"elapsed: {d['stats']['elapsed_ms']} ms\")
print(f\"model: {d['stats']['model']}\")
for i, b in enumerate(d['blocks'][:5]):
    if b['type'] == 'text':
        preview = b.get('text', '')[:60]
    elif b['type'] == 'formula':
        preview = b.get('latex', '')[:60]
    elif b['type'] == 'table':
        preview = '[table html]'
    print(f\"  [{i}] {b['type']:7s} conf={b['confidence']:.2f} | {preview}\")
"