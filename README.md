# 小红书博主AI对话系统

输入小红书笔记链接，自动提取内容（图片、视频、文字），基于内容与 AI 对话，像直接和博主聊天一样。

## 技术栈

- **前端**: Next.js 14 (App Router)、TypeScript、Tailwind CSS
- **后端**: Python FastAPI、Playwright、Whisper、PaddleOCR
- **AI**: Groq API（免费）、ChromaDB、sentence-transformers

**总成本 ¥0**

## 项目结构

```
xiaohongshu-chat/
├── frontend/           # Next.js 前端
│   ├── app/
│   │   ├── page.tsx
│   │   └── layout.tsx
│   └── package.json
├── backend/            # Python 后端
│   ├── main.py         # FastAPI 主程序
│   ├── crawler.py      # 小红书爬虫
│   ├── video_processor.py
│   ├── ocr_processor.py
│   └── requirements.txt
└── README.md
```

## 环境准备

### 系统依赖

```bash
# macOS
brew install python@3.11 node ffmpeg tesseract

# Ubuntu
sudo apt update
sudo apt install python3.11 python3-pip nodejs npm ffmpeg tesseract-ocr tesseract-ocr-chi-sim
```

### 后端

```bash
cd backend
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

复制环境变量并填写 Groq API Key（[免费申请](https://console.groq.com)）：

```bash
cp .env.example .env
# 编辑 .env，设置 GROQ_API_KEY=your_groq_api_key_here
```

### 前端

```bash
cd frontend
npm install
```

## 运行

**终端 1 - 后端**

```bash
cd backend
source venv/bin/activate
python main.py
```

API 文档: http://localhost:8000/docs

**终端 2 - 前端**

```bash
cd frontend
npm run dev
```

打开 http://localhost:3000

## 使用流程

1. 在首页输入小红书笔记链接
2. 点击「开始分析」（视频约 1–2 分钟，图文约 10–30 秒）
3. 进入对话页，基于该笔记内容提问

## 常见问题

- **爬虫失败**: 开发时可在 `crawler.py` 中设 `headless=False`，手动登录小红书后 cookies 会保存
- **视频下载失败**: 确保已安装 `yt-dlp` 和 `ffmpeg`
- **Groq 限流**: 可加重试或降低请求频率

## 部署建议

- 前端: Vercel（免费）
- 后端: Railway / Render（有免费额度）

祝开发顺利。
