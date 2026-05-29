# RedNote AI Chat Agent

Chat with any RedNote (小红书) post or creator — paste a link, and the AI extracts the full content (text, images, video) and lets you have a real conversation about it.

> **Total cost: $0** — built entirely on free-tier APIs and open-source tools.

---

## What it does

- **Single post**: paste a note link → AI reads the full text, OCR-scans images, and transcribes video audio
- **Creator profile**: paste a profile link → AI ingests the creator's recent posts and lets you chat *as if you're talking to the creator*
- **Smart paste**: automatically extracts the URL from the messy share text RedNote copies to your clipboard
- **Multi-turn chat**: remembers the conversation history within each session

---

## Tech stack

| Layer | Tools |
|---|---|
| Frontend | Next.js 14, TypeScript, Tailwind CSS |
| Backend | Python, FastAPI, Playwright (headless Chrome) |
| AI | [Groq API](https://console.groq.com) — Llama 3.1 8B (free) |
| Video | faster-whisper (local Whisper transcription) + yt-dlp + ffmpeg |
| OCR | PaddleOCR (Chinese + English) |

---

## Project structure

```
RedNote-AI-Chat-Agent/
├── frontend/
│   └── app/
│       ├── page.tsx        # Main chat UI
│       └── layout.tsx
├── backend/
│   ├── main.py             # FastAPI app + TTL session store
│   ├── crawler.py          # Playwright-based RedNote scraper
│   ├── video_processor.py  # yt-dlp + ffmpeg + Whisper
│   ├── ocr_processor.py    # PaddleOCR image text extraction
│   └── requirements.txt
└── README.md
```

---

## Setup

### Prerequisites

```bash
# macOS
brew install python@3.11 node ffmpeg

# Ubuntu
sudo apt install python3.11 nodejs npm ffmpeg
```

### 1. Backend

```bash
cd backend
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
```

Create your `.env` file:

```bash
cp .env.example .env
```

Open `.env` and set your Groq API key (free at [console.groq.com](https://console.groq.com)):

```
GROQ_API_KEY=your_key_here
```

### 2. Frontend

```bash
cd frontend
npm install
```

---

## Running

Open **two terminals**:

**Terminal 1 — backend**
```bash
cd backend
source venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000
```

**Terminal 2 — frontend**
```bash
cd frontend
npm run dev
```

Then open **http://localhost:3000**

---

## How to use

1. Copy any RedNote share link (the whole text — URL extractor handles the extra copy text automatically)
2. Paste into the input box and click **Start Analysis**
3. Wait for processing (image posts ~10–30s, video posts ~1–5 min)
4. Chat freely about the content

---

## Optional: stay logged in to RedNote

If posts are blocked behind login, point the crawler at your real Chrome profile:

```bash
# In backend/.env
CHROME_USER_DATA_DIR="/Users/yourname/Library/Application Support/Google/Chrome"
```

The crawler uses a separate `_crawler` copy of the profile so it never conflicts with your running Chrome.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Crawl returns login page | Set `CHROME_USER_DATA_DIR` (see above) |
| Video transcription missing | Install `faster-whisper`: `pip install faster-whisper` |
| OCR not working | PaddleOCR requires Python ≤ 3.12; skip or use a compatible env |
| Groq rate limit | Lower request frequency or upgrade to a paid Groq plan |

---

## Deployment

| Service | Notes |
|---|---|
| Frontend | [Vercel](https://vercel.com) (free) |
| Backend | [Railway](https://railway.app) or [Render](https://render.com) (free tier available) |

> Note: the Playwright crawler requires a full Chrome install — serverless platforms won't work for the backend. Use a container-based host.
