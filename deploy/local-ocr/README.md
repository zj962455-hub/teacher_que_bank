# 本机强模型 OCR（验证用）

老大说「符号识别还是不行」之后，用本机把更强的模型跑了一遍，
确认**2C4G 线上机器确实是瓶颈** —— 不是规则能救的问题，是模型能力问题。

## 这是什么

用 **PP-StructureV3**（内含 PP-FormulaNet_plus-L，直接输出 LaTeX）
起一个和线上**完全同契约**的本地 OCR 服务：

    GET  /api/v1/health
    POST /api/v1/ocr/image   multipart 字段 image，头 X-API-Key
    -> {"ok": true, "blocks": [...], "stats": {...}}

所以 PADDLEOCR_BASE_URL 指过来就能对比，线上代码一行不用改。

## 跑起来（本机 M4/16G）

    cd /Users/rrobot/.openclaw/workspace
    ./ocr-local-venv/bin/pip install -r deploy/local-ocr/requirements.txt  # 首次
    ./run_local_ocr.sh          # 监听 127.0.0.1:8099

冒烟：

    curl -s http://127.0.0.1:8099/api/v1/health
    curl -s -H 'X-API-Key: local-dev-key' -F 'image=@某张题.png;type=image/png' http://127.0.0.1:8099/api/v1/ocr/image

## 对比结果（同一批 5 张灰度样本）

| 样本 | 线上 PP-OCRv4 mobile + 规则纠错 | 本机 PP-StructureV3 |
|---|---|---|
| A | ∠B=∠C=60°（规则还原）、DE⊥AB（规则还原） | 真正的 LaTeX，模型直接给出 |
| B | PE//OA（∥→//） | PE/OA（∥→/，仍差一个符号） |
| C | ①ZA+ZB=ZC（∠→Z） | ①\angle A+\angle B=\angle C ✓ |
| D | PQ=-BP2（分数拼不回） | PQ={\frac{1}{2}}BP ✓ |
| E | A.A=B=3C（∠ 整个吞掉） | \angle A=\angle B=3\angle C ✓ |

强模型还多给一样东西：**图形区域被版面模型标成 image 块**（带 bbox），
三角形示意图的位置是模型直接给的，比启发式裁图准。

## 代价

- 本机：18~21 秒/张，内存 3.46GB
- 线上 2C4G：**装不下**（PP-StructureV3 实测 RSS 2.4GB，机器只剩 116MB）
- 线上就算升到 8G，单张大概 40~80 秒（ECS 的 CPU 比 M4 慢一大截）

## 注意

线上后端在 ECS 上，**它调不到你 Mac 上的服务**。
所以本地服务现阶段只能用于：本地开发验证 / 对比测试。
要让线上用上强模型，得选一条路（升配 / 隧道 / 混合），
见 docs/lesson-35-ocr-upgrade.md 第九节。
