# backend/main.py

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
import time
import hashlib
from dotenv import load_dotenv

from crawler import XiaohongshuCrawler
from video_processor import VideoProcessor
from ocr_processor import OCRProcessor

from groq import Groq

load_dotenv()

app = FastAPI(title="RedNote AI Chat")


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    if isinstance(exc, HTTPException):
        raise exc
    import traceback
    traceback.print_exc()
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc), "message": "Internal server error"},
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── TTL-bounded in-memory store (max 200 entries, 2-hour TTL) ─────────────────
class TTLStore:
    def __init__(self, max_size: int = 200, ttl: int = 7200):
        self._store: dict = {}
        self._times: dict = {}
        self._max_size = max_size
        self._ttl = ttl

    def _evict_one(self, key: str):
        if key in self._times and time.time() - self._times[key] > self._ttl:
            self._store.pop(key, None)
            self._times.pop(key, None)

    def _evict_expired(self):
        now = time.time()
        stale = [k for k, t in list(self._times.items()) if now - t > self._ttl]
        for k in stale:
            self._store.pop(k, None)
            self._times.pop(k, None)

    def __contains__(self, key: str) -> bool:
        self._evict_one(key)
        return key in self._store

    def __getitem__(self, key: str):
        self._evict_one(key)
        return self._store[key]

    def __setitem__(self, key: str, value):
        self._evict_expired()
        if key not in self._store and len(self._store) >= self._max_size:
            oldest = min(self._times, key=lambda k: self._times[k])
            self._store.pop(oldest, None)
            self._times.pop(oldest, None)
        self._store[key] = value
        self._times[key] = time.time()

    def get(self, key: str, default=None):
        return self._store[key] if key in self else default


# ─────────────────────────────────────────────────────────────────────────────

print("🚀 正在初始化系统...")

_api_key = os.getenv("GROQ_API_KEY")
if not _api_key:
    raise RuntimeError("GROQ_API_KEY is not set. Please add it to .env before starting.")

crawler = XiaohongshuCrawler()
video_processor = VideoProcessor()
ocr_processor = OCRProcessor()  # lazy — no heavy init until first image is processed

groq_client = Groq(api_key=_api_key)

posts_store = TTLStore(max_size=200, ttl=7200)

print("✅ 系统初始化完成")


# ── Data models ───────────────────────────────────────────────────────────────

class CrawlRequest(BaseModel):
    url: str
    max_posts: int = 3


class ChatRequest(BaseModel):
    message: str
    post_id: str


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_login_or_security_page(crawl_result: dict) -> bool:
    title = (crawl_result.get("title") or "").strip().lower()
    content = (crawl_result.get("content") or "").strip().lower()
    combined = f"{title} {content}"
    strong_keywords = [
        "account security", "expires in 1 minute", "scan the qr code", "scan qr code",
        "扫码登录", "请登录", "登录以继续", "安全验证",
    ]
    if any(k in combined for k in strong_keywords):
        if len(combined) < 150:
            return True
        if any(k in title for k in ["扫码", "请登录", "account security", "登录以继续"]):
            return True
    return False


def _build_full_content(crawl_result: dict, vp: VideoProcessor, op: OCRProcessor) -> str:
    full = f"Title: {crawl_result['title']}\n\n{crawl_result['content']}"
    if crawl_result["type"] == "video":
        if crawl_result.get("video_url"):
            print("🎬 检测到视频，开始处理...")
            video_result = vp.process_video(crawl_result["video_url"])
            if video_result.get("success"):
                full += f"\n\n[Video transcript]\n{video_result['transcript']}"
                print(f"✅ 视频转录完成: {len(video_result['transcript'])}字")
            else:
                full += "\n\n[This post is a video. Audio could not be transcribed.]"
                print(f"⚠️ 视频处理失败: {video_result.get('error')}")
        else:
            full += "\n\n[This post is a video. Video URL could not be extracted from the page.]"
    if crawl_result.get("images"):
        print(f"📷 检测到{len(crawl_result['images'])}张图片，开始OCR...")
        ocr_text = op.process_images(crawl_result["images"][:3])
        if ocr_text:
            full += f"\n\n[Image OCR text]\n{ocr_text}"
            print(f"✅ OCR完成: {len(ocr_text)}字")
    return full


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {"message": "RedNote AI Chat API"}


@app.post("/api/crawl")
async def crawl_post(req: CrawlRequest):
    try:
        print(f"\n{'='*50}")
        print(f"📥 收到爬取请求: {req.url}")

        is_profile = crawler.is_profile_url(req.url)

        if is_profile:
            post_urls = await crawler.get_profile_post_links(req.url, max_posts=req.max_posts)
            if not post_urls:
                raise HTTPException(
                    status_code=500,
                    detail="Could not find any post links on this profile. Check the URL or try again.",
                )
            full_content_parts = []
            first_title = ""
            total_images = 0
            has_video = False
            for i, post_url in enumerate(post_urls, 1):
                print(f"\n--- 正在抓取第 {i}/{len(post_urls)} 条笔记 ---")
                crawl_result = await crawler.crawl(post_url)
                if not crawl_result["success"]:
                    print(f"⚠️ 跳过失败: {crawl_result.get('error')}")
                    continue
                if _is_login_or_security_page(crawl_result):
                    print("⚠️ 跳过登录/安全页，不纳入内容")
                    continue
                part = _build_full_content(crawl_result, video_processor, ocr_processor)
                full_content_parts.append(f"\n\n--- Post {i} ---\n{part}")
                if i == 1:
                    first_title = crawl_result.get("title") or "Profile"
                total_images += len(crawl_result.get("images") or [])
                if crawl_result.get("video_url"):
                    has_video = True
            if not full_content_parts:
                raise HTTPException(
                    status_code=500,
                    detail="All posts from this profile failed to crawl.",
                )
            full_content = "\n".join(full_content_parts)
            post_id = hashlib.md5(req.url.encode()).hexdigest()[:12]
            display_title = "Happy to talk with you"
        else:
            crawl_result = await crawler.crawl(req.url)
            if not crawl_result["success"]:
                raise HTTPException(
                    status_code=500,
                    detail=f"Crawl failed: {crawl_result.get('error', 'Unknown error')}",
                )
            if _is_login_or_security_page(crawl_result):
                raise HTTPException(
                    status_code=400,
                    detail="This link opened a login or security page, not a post. Try logging in on the site first, or use a direct post link.",
                )
            post_id = hashlib.md5(req.url.encode()).hexdigest()[:12]
            full_content = _build_full_content(crawl_result, video_processor, ocr_processor)
            display_title = crawl_result["title"]
            total_images = len(crawl_result.get("images") or [])
            has_video = bool(crawl_result.get("video_url"))

        posts_store[post_id] = {
            "content": full_content,
            "history": [],  # multi-turn chat history
            "metadata": {
                "url": req.url,
                "title": display_title,
                "type": "profile" if is_profile else "single",
            },
        }
        print(f"💾 存储完成! PostID: {post_id} | 总字数: {len(full_content)}")
        print(f"{'='*50}\n")

        content_preview = (full_content or "")[:500]
        if len(full_content or "") > 500:
            content_preview += "..."
        return {
            "success": True,
            "post_id": str(post_id),
            "data": {
                "title": str(display_title or ""),
                "content": content_preview,
                "type": "profile" if is_profile else "single",
                "has_video": bool(has_video),
                "image_count": int(total_images),
                "total_content_length": int(len(full_content or "")),
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"❌ 错误: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/chat")
async def chat(req: ChatRequest):
    try:
        print(f"\n💬 收到对话请求: {req.message}")

        if req.post_id not in posts_store:
            raise HTTPException(
                status_code=404,
                detail="Post not found. Please analyze the link again.",
            )

        entry = posts_store[req.post_id]
        content = entry["content"]
        metadata = entry["metadata"]
        history: list = entry["history"]

        if not content or len(content.strip()) < 5:
            raise HTTPException(
                status_code=400,
                detail="No valid text extracted from this post. Try another link.",
            )

        is_profile = metadata.get("type") == "profile"
        if is_profile:
            system_prompt = f"""You are roleplaying as the creator of the posts below. Chat as them in first person ("I", "my", "I like...").

【Content from this creator's posts】
{content}

【Rules】
1. Answer as the creator: use first person. Example: "I love eating..." not "The author likes...".
2. Base answers only on the content above. For personal questions (e.g. favorite food, hobbies), infer from what their posts show or say; if nothing fits, say something like "I haven't shared that in my posts yet."
3. Stay in character and friendly. Respond in English only; if you quote their words, translate Chinese to English."""
        else:
            system_prompt = f"""You are an AI assistant. Answer using ONLY the post content below. Do not invent details that are not in the content.

【Post content】
{content}

【Rules】
1. Use only information from the post content above. Summarize or paraphrase; do not invent.
2. Do not assume the user has a problem (e.g. account security) unless they or the post say so.
3. For general summary questions ("what does he/she talk about", "what is this about"): always give a short summary using the title and any text or transcript you have.
4. If the content says "[This post is a video" or "Video transcript" or "could not be transcribed", treat it as a video post.
5. Only say "The post doesn't mention this" when the user asks about something specific that truly does not appear in the content.
6. Be friendly. Respond in English only; translate any Chinese when you cite it."""

        messages = [{"role": "system", "content": system_prompt}]
        # include previous turns (keep last 20 to stay within token budget)
        messages.extend(history[-20:])
        messages.append({"role": "user", "content": req.message})

        print("🤖 调用AI生成回答...")
        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=messages,
            temperature=0.4,
            max_tokens=1024,
        )

        reply = response.choices[0].message.content
        print("✅ AI回答生成完成")

        # persist this turn into history
        history.append({"role": "user", "content": req.message})
        history.append({"role": "assistant", "content": reply})

        return {
            "success": True,
            "reply": reply,
            "post_title": metadata.get("title", ""),
            "context_length": len(content),
        }

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"❌ 对话错误: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
