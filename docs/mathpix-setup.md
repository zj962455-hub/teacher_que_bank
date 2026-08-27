> ⚠️ **DEPRECATED · 2026-08-26**
>
> **Mathpix 已弃用,不再作为项目 OCR 引擎使用。**
>
> **废弃原因**:Mathpix 新版要求**创建组织才能生成 API key**(需要付费),旧版 API 已无法访问,免费个人账号拿不到 key,这条路走不通。
>
> **当前 OCR 方案**:**自托管 PaddleOCR(阿里云 ECS · Anolis 3)**,部署在 `8.160.177.222:8080`。
> 详细部署见 `projects/teacher-question-bank/deploy/paddleocr/`,配置文档见 `docs/paddleocr-ecs-setup.md`(待写)。
>
> **优势**:
> - 零 token / API key 风险,完全自托管
> - 长期可控,不受 Mathpix 政策变化影响
> - 阿里云 ECS 2C4G 即可,部署成本低
> - 中文 OCR 准确率高(适合高中信信场景)
> - 数学公式 + 表格识别(API 返回结构化 blocks)
>
> **代价**:
> - 公式识别稍弱于 Mathpix(高中信信公式少,够用)
> - 需要维护自己的 ECS(老大已确认承担)
>
> 以下是**弃用前的选型记录**,作为决策历史保留(121 行原文)。

---

# Mathpix 账号注册 + API Key 申请

> 教培题库的 OCR + 公式识别靠 Mathpix 提供。**第五课会用到 API key**。

---

## 1️⃣ 注册账号

访问：https://accounts.mathpix.com/

点 **Sign Up**，用邮箱注册（推荐用常用邮箱，能收到 API key 通知）。

---

## 2️⃣ 申请 API Key

登录后访问：https://mathpix.com/ocr

或者：Dashboard → API → Create new key

**Key 名字**随便起，比如 `teacher-question-bank-dev`。

复制 key 字符串，类似：

```
abcd1234efgh5678ijkl9012mnop3456qrst7890
```

---

## 3️⃣ 看价格方案

| 方案 | 价格 | 额度 | 适合 |
|---|---|---|---|
| Free | $0 | 50 次/月 | 试 API |
| **Pro** | **$4.99/月** | **1000 次/月** | **MVP 阶段推荐** ⭐ |
| Pay-as-you-go | $0.004/次 | 无上限 | 大规模 |

**50 个老师 × 每月 20 题 × 50% 图片题 = 500 次/月** —— Pro 套餐完全够用。

---

## 4️⃣ 升级到 Pro

Dashboard → Plans → 选 Pro → 绑定信用卡/借记卡。

⚠️ 提前确认：
- **你有一张能国际支付的卡**（Visa/Mastercard/带外币功能的）
- **支付宝/微信** 不直接支持 Mathpix，需要用支持外币的卡
- 如果没有 → 告诉我，我帮你看替代方案（比如另一个 OCR 服务）

---

## 5️⃣ 把 API Key 给我

拿到 key 后**直接发我**（QQ 消息），我帮你：

1. 配到项目的 `.env` 文件（本地 + 服务器）
2. 加到 `.gitignore`，**不会提交到 GitHub**
3. 写个测试脚本，验证能用

---

## 6️⃣ 重要注意事项

### 🔒 Key 安全

- ✅ **不要**把 key 提交到 GitHub
- ✅ **不要**发到群里分享给别人
- ✅ 存到项目根目录的 `.env` 文件
- ✅ 我会在项目里写好 `.env.example` 模板

### 💰 用量监控

- Dashboard → Usage 看月度用量
- 月度用量预警：建议在 Pro 套餐（1000 次）用到 800 次时提醒

### 🧪 测试

注册完 Free 套餐（50 次）后，告诉我，我帮你写个 Python 测试脚本：

```python
import requests

response = requests.post(
    "https://api.mathpix.com/v3/text",
    headers={"app_id": "你的_app_id", "app_key": "你的_key"},
    json={
        "src": "https://example.com/equation.png",
        "formats": ["text", "latex"]
    }
)
print(response.json)
```

跑成功就能正式用了。

---

## 🔄 备用方案（万一主方案卡住）

如果 Mathpix 注册 / 支付卡有问题，可考虑：

| 服务 | 公式识别 | 价格 | 评估 |
|---|---|---|---|
| **Mathpix** | ✅ 业界最强 | $4.99/月 | ⭐ 首选 |
| 百度 OCR | ❌ 公式识别差 | ¥0.005/次 | 备选 |
| 腾讯 OCR | ❌ 公式识别差 | 类似 | 备选 |
| 自建 (PaddleOCR) | ⚠️ 需训练 | 0 | 重投入 |

**MVP 阶段强烈建议 Mathpix**。

---

## ✅ 你的下一步

1. 注册 Mathpix 账号
2. 拿到 API key 发我
3. 如果卡在支付（国际信用卡问题）—— 告诉我，我们换方案

不急，第五课用之前搞定就行。

---

## 🗒 弃用追溯(2026-08-26)

- **触发**:老大评估 PaddleOCR 替代方案(参考 OpenMathpix 与 mathpix-markdown-it 两个开源工具)
- **决策**:2026-08-26 21:07(00:00 后 ECS 部署成功 OCR 端到端测试通过),Mathpix 路线正式弃用
- **替代**:阿里云 ECS 自托管 PaddleOCR PP-StructureV3,部署在 `projects/teacher-question-bank/deploy/paddleocr/`
- **API endpoint**:`http://8.160.177.222:8080/api/v1/ocr/image`
- **lesson-06 影响**:`docs/lesson-06-notes.md` + `teacher_question_bank/app/services/ocr.py` 需要同步改造