#!/bin/bash
# 启动本机强模型 OCR 服务（契约和线上完全一致）
cd /Users/rrobot/.openclaw/workspace
export OCR_API_KEYS="${OCR_API_KEYS:-local-dev-key}"
exec ./ocr-local-venv/bin/python local_ocr_service.py
