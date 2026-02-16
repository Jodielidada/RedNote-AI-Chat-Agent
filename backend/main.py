# backend/main.py

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
from dotenv import load_dotenv
import hashlib

# 导入自定义模块
from crawler import XiaohongshuCrawler
from video_processor import VideoProcessor
from ocr_processor import OCRProcessor

# AI相关
from groq import Groq

# 加载环境变量
load_dotenv()

# 初始化FastAPI
app = FastAPI(title="RedNote AI Chat")


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Return JSON for unhandled errors so the frontend can show a proper message."""
    if isinstance(exc, HTTPException):
        raise exc
    import traceback
    traceback.print_exc()
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc), "message": "Internal server error"},
    )


# CORS设置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 初始化组件
print("🚀 正在初始化系统...")

crawler = XiaohongshuCrawler()
video_processor = VideoProcessor()
ocr_processor = OCRProcessor()

groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
# 简单内存存储（按 post_id 查找，无需向量数据库）
posts_store: dict[str, dict] = {}

print("✅ 系统初始化完成")

# 数据模型
class CrawlRequest(BaseModel):
    url: str
    max_posts: int = 3  # 博主主页默认只抓 3 条，减少超时；稳定后可让前端传更大值


class ChatRequest(BaseModel):
    message: str
    post_id: str


# API路由


@app.get("/")
async def root():
    return {"message": "RedNote AI Chat API"}


def _is_login_or_security_page(crawl_result: dict) -> bool:
    """Only treat as login/security page when content is clearly that (short + login keywords), not normal notes."""
    title = (crawl_result.get("title") or "").strip().lower()
    content = (crawl_result.get("content") or "").strip().lower()
    combined = f"{title} {content}"
    # Strong login-page phrases (title or full content)
    strong_keywords = [
        "account security", "expires in 1 minute", "scan the qr code", "scan qr code",
        "扫码登录", "请登录", "登录以继续", "安全验证",
    ]
    if any(k in combined for k in strong_keywords):
        # Only flag if content is short (real notes have more text)
        if len(combined) < 150:
            return True
        # Or if title itself is a login prompt
        if any(k in title for k in ["扫码", "请登录", "account security", "登录以继续"]):
            return True
    return False


def _build_full_content(crawl_result: dict, video_processor, ocr_processor) -> str:
    """Turn one crawl result into full_content (text + optional video transcript + OCR)."""
    full = f"Title: {crawl_result['title']}\n\n{crawl_result['content']}"
    if crawl_result["type"] == "video":
        if crawl_result.get("video_url"):
            print("🎬 检测到视频，开始处理...")
            video_result = video_processor.process_video(crawl_result["video_url"])
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
        ocr_text = ocr_processor.process_images(crawl_result["images"][:3])
        if ocr_text:
            full += f"\n\n[Image OCR text]\n{ocr_text}"
            print(f"✅ OCR完成: {len(ocr_text)}字")
    return full


@app.post("/api/crawl")
async def crawl_post(req: CrawlRequest):
    """
    Crawl a single post URL or a profile URL (first 5–10 posts merged).
    """
    try:
        print(f"\n{'='*50}")
        print(f"📥 收到爬取请求: {req.url}")

        is_profile = crawler.is_profile_url(req.url)

        if is_profile:
            # --- Profile: get post links, then crawl each and merge ---
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
                    print(f"⚠️ 跳过登录/安全页，不纳入内容")
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
            # --- Single post ---
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

        # Store
        posts_store[post_id] = {
            "content": full_content,
            "metadata": {
                "url": req.url,
                "title": display_title,
                "type": "profile" if is_profile else "single",
            },
        }
        print(f"💾 存储完成! PostID: {post_id} | 总字数: {len(full_content)}")
        print(f"{'='*50}\n")

        # 确保返回结构完整、字段可序列化，避免前端拿到 200 却解析失败
        content_preview = (full_content or "")[:500]
        if len(full_content or "") > 500:
            content_preview += "..."
        payload = {
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
        return payload

    except HTTPException:
        raise
    except Exception as e:
        import traceback

        print(f"❌ 错误: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/chat")
async def chat(req: ChatRequest):
    """
    基于笔记内容进行AI对话
    """
    try:
        print(f"\n💬 收到对话请求: {req.message}")

        # 1. 从存储获取笔记内容
        if req.post_id not in posts_store:
            raise HTTPException(
                status_code=404,
                detail="Post not found. Please analyze the link again.",
            )
        content = posts_store[req.post_id]["content"]
        metadata = posts_store[req.post_id]["metadata"]

        # 2. 构建提示词
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
1. Use only information from the post content above. Summarize or paraphrase; do not invent (e.g. no "scan QR code" unless the post says so).
2. Do not assume the user has a problem (e.g. account security) unless they or the post say so.
3. For questions like "what does he/she talk about", "what is this about", "what's in the video/post": always give a short summary using the title and any text or transcript you have. Do NOT reply "The post doesn't mention this" for these general-summary questions if you have at least a title or any content.
4. If the content says "[This post is a video" or "Video transcript" or "could not be transcribed", treat it as a video post: use [Video transcript] if present, or say it's a video and summarize the title and any text.
5. Only say "The post doesn't mention this" when the user asks about something specific (e.g. a name, a number, a step) that truly does not appear in the content.
6. Be friendly. Respond in English only; translate any Chinese when you cite it."""

        # 3. 调用Groq生成回答
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise HTTPException(
                status_code=500,
                detail="GROQ_API_KEY not configured. Please set it in .env",
            )
        print("🤖 调用AI生成回答...")
        response = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": req.message},
            ],
            temperature=0.4,
            max_tokens=1024,
        )

        reply = response.choices[0].message.content

        print("✅ AI回答生成完成")

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


# 启动服务
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
