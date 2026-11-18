## 项目结构

```
teacher-question-bank/
├── backend/                    # FastAPI 后端
│   ├── app/
│   │   ├── main.py             # 应用入口（挂载全部路由）
│   │   ├── database.py         # 连接与会话工厂
│   │   ├── models/             # 数据模型，按业务域拆包
│   │   │   ├── account.py      #   账号域：用户 / 会话 / 短信 / 邀请码
│   │   │   ├── question.py     #   题库域：分类 / 题目 / 标签 / 上传
│   │   │   ├── paper.py        #   试卷域：试卷 / 试卷题 / 分享链接
│   │   │   └── feedback.py     #   反馈域：老师反馈
│   │   ├── routers/            # HTTP 路由，一个文件一个业务域
│   │   ├── services/           # 业务逻辑
│   │   ├── migrations/         # SQL 迁移脚本
│   │   ├── scripts/            # 管理脚本（建账号 / 发邀请码）
│   │   └── templates/          # 试卷 PDF 模板
│   ├── tests/                  # pytest
│   ├── requirements.txt        # 依赖清单（钉死版本）
│   └── venv/                   # 本地虚拟环境（不入 git）
├── frontend/                   # Vue 3 + Vite 前端
│   ├── src/
│   │   ├── api/                # 按后端资源分的接口封装
│   │   ├── components/         # 通用组件
│   │   ├── composables/        # 可复用逻辑
│   │   ├── pages/              # 页面
│   │   ├── router/             # 路由 + 页面标题
│   │   └── utils/              # 纯函数工具
│   ├── public/                 # 静态资源（favicon / og 分享封面）
│   └── scripts/                # 图标生成 + 无头验证脚本
├── deploy/teacher-bank/        # 部署脚本与服务器配置
├── docs/                       # 学习文档与备案材料
├── prototype.html              # 低保真线框图原型（v0.2，含 OCR）
└── README.md                   # 本文件
```