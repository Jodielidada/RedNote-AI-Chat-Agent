# backend/crawler.py

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
import asyncio
import json
import os
import re
from typing import Optional, Tuple, Any

try:
    import requests
except ImportError:
    requests = None

# 全局锁：保证一次只跑一个浏览器任务，避免多请求同时开多个 Chrome
CRAWL_LOCK = asyncio.Lock()


def _resolve_short_link(url: str) -> Optional[str]:
    """Resolve xhslink.com short URL to final xiaohongshu URL (desktop)."""
    if not requests or "xhslink.com" not in (url or ""):
        return None
    try:
        resp = requests.get(
            url,
            allow_redirects=True,
            timeout=15,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            },
        )
        final = (resp.url or "").strip()
        if final and ("xiaohongshu.com" in final or "xhslink.com" in final):
            return final
    except Exception:
        pass
    return None


def _get_chrome_profile_dir() -> Optional[str]:
    """
    若设置了 CHROME_USER_DATA_DIR，使用「爬虫专用副本」目录（原路径 + _crawler），
    避免与正在运行的 Chrome 抢同一配置（SingletonLock）。该副本首次为空，需在脚本里登录一次小红书后即可沿用。
    """
    profile = os.environ.get("CHROME_USER_DATA_DIR", "").strip()
    if not profile:
        return None
    base = os.path.expanduser(profile)
    # 使用独立目录，不与本机 Chrome 冲突，无需退出 Chrome
    crawler_dir = base.rstrip("/") + "_crawler"
    try:
        if not os.path.isdir(crawler_dir):
            os.makedirs(crawler_dir, exist_ok=True)
        print(f"📌 使用爬虫专用配置目录（与 Chrome 互不干扰）: {crawler_dir}")
        return crawler_dir
    except Exception as e:
        print(f"⚠️ 无法创建爬虫配置目录 {crawler_dir}: {e}")
        return None


def _common_browser_options(headless: bool = True):
    args = ["--disable-blink-features=AutomationControlled"]
    viewport = {"width": 1920, "height": 1080}
    user_agent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    return args, viewport, user_agent


async def _launch_context(p, headless: bool = True):
    """
    If CHROME_USER_DATA_DIR is set -> launch_persistent_context to reuse login.
    Else -> launch + new_context (then we can load cookies.json).
    Returns (context, browser_or_none).
    """
    args, viewport, user_agent = _common_browser_options(headless=headless)
    profile_dir = _get_chrome_profile_dir()

    if profile_dir:
        # ✅ persistent context reuses real Chrome profile (login/cookies/localstorage)
        try:
            context = await p.chromium.launch_persistent_context(
                user_data_dir=profile_dir,
                channel="chrome",
                headless=headless,
                args=args,
                viewport=viewport,
                user_agent=user_agent,
            )
            return context, None
        except Exception as e:
            err = str(e).lower()
            if "singletonlock" in err or "processsingleton" in err or "profile" in err:
                print("⚠️ 无法启动浏览器配置目录。若未使用 _crawler 副本，请完全退出 Chrome（⌘Q）后再试。")
            raise

    browser = await p.chromium.launch(
        channel="chrome",
        headless=headless,
        args=args,
    )
    context = await browser.new_context(
        viewport=viewport,
        user_agent=user_agent,
    )
    return context, browser


class XiaohongshuCrawler:
    def __init__(self):
        self.cookies_file = "cookies.json"

    def save_cookies_sync(self, cookies: list):
        """保存cookies避免重复登录（仅用于非 persistent 模式）"""
        try:
            with open(self.cookies_file, "w") as f:
                json.dump(cookies, f)
        except Exception:
            pass

    def load_cookies_sync(self) -> list:
        """加载已保存的cookies（仅用于非 persistent 模式）"""
        if os.path.exists(self.cookies_file):
            try:
                with open(self.cookies_file, "r") as f:
                    return json.load(f)
            except Exception:
                return []
        return []

    @staticmethod
    def is_profile_url(url: str) -> bool:
        """Check if URL is a user profile page (full or short link)."""
        u = (url or "").lower()
        return "/user/profile/" in u or "xhslink.com/m/" in u

    async def get_profile_post_links(self, profile_url: str, max_posts: int = 10) -> list[str]:
        """
        打开博主主页，通过「点击笔记卡片 → 等跳转到 /explore/<id> → 记录 URL → 返回」拿笔记链接。
        不依赖 DOM 里的 href（主页常只有 /explore/ 占位）。支持短链 xhslink.com 先解析再打开。
        """
        async with CRAWL_LOCK:
            async with async_playwright() as p:
                context, browser = await _launch_context(p, headless=True)

                if browser is not None:
                    cookies = self.load_cookies_sync()
                    if cookies:
                        try:
                            await context.add_cookies(cookies)
                        except Exception:
                            pass

                page = await context.new_page()
                links: list[str] = []

                try:
                    # 短链先解析成 profile URL 再打开
                    if "xhslink.com" in profile_url:
                        resolved = await asyncio.to_thread(_resolve_short_link, profile_url)
                        if resolved:
                            print(f"📂 短链解析结果: {resolved}")
                            profile_url = resolved

                    print(f"📂 正在打开博主主页: {profile_url}")
                    await page.goto(profile_url, wait_until="domcontentloaded", timeout=60_000)
                    await page.wait_for_timeout(2500)

                    # 滚动让卡片加载（多滚几次）
                    for _ in range(6):
                        await page.mouse.wheel(0, 1200)
                        await page.wait_for_timeout(800)

                    # 先尽量关掉可能遮挡的弹窗/遮罩
                    try:
                        await page.keyboard.press("Escape")
                    except Exception:
                        pass

                    sample = await page.evaluate(
                        """() => Array.from(document.querySelectorAll("a[href*='/explore/']")).slice(0,5).map(a=>a.getAttribute('href'))"""
                    )
                    print("🔎 explore href 样本前5条:", sample)

                    # 直接从 DOM 提取 explore 链接（不点击，避免不可见/弹层等问题）
                    links = await page.evaluate(
                        """() => {
  const base = 'https://www.xiaohongshu.com';
  const out = [];
  const seen = new Set();
  const anchors = Array.from(document.querySelectorAll("a[href*='/explore/']"));
  for (const a of anchors) {
    let href = (a.getAttribute("href") || "").trim();
    if (!href) continue;
    const m = href.match(/\\/explore\\/([a-zA-Z0-9]+)/);
    if (!m) continue;
    let full = base + "/explore/" + m[1];
    if (!seen.has(full)) {
      seen.add(full);
      out.push(full);
    }
  }
  return out;
}"""
                    )
                    if not isinstance(links, list):
                        links = []
                    result = links[:max_posts]
                    print(f"✅ 直接从 DOM 抽取到 {len(links)} 条笔记链接，将返回前 {len(result)} 条")

                    if browser is not None:
                        try:
                            ck = await context.cookies()
                            self.save_cookies_sync(ck)
                        except Exception:
                            pass

                    print(f"✅ 最终拿到 {len(links)} 条笔记链接")
                    return result

                except Exception as e:
                    print(f"❌ 解析博主主页失败: {str(e)}")
                    return []
                finally:
                    try:
                        await context.close()
                    except Exception:
                        pass
                    if browser is not None:
                        try:
                            await browser.close()
                        except Exception:
                            pass

    async def crawl(self, url: str):
        """
        爬取小红书笔记
        支持：图文笔记、视频笔记
        """
        async with CRAWL_LOCK:
            async with async_playwright() as p:
                context, browser = await _launch_context(p, headless=True)

                # 只有非 persistent 才加载 cookies.json（persistent 直接用本机 Chrome 登录态）
                if browser is not None:
                    cookies = self.load_cookies_sync()
                    if cookies:
                        try:
                            await context.add_cookies(cookies)
                        except Exception:
                            pass

                page = await context.new_page()

                captured_video_urls = []

                def handle_response(response):
                    try:
                        req_url = response.url
                        if not req_url or "blob:" in req_url:
                            return
                        req_url_lower = req_url.lower()
                        if (
                            ".mp4" in req_url_lower
                            or ".m3u8" in req_url_lower
                            or "video" in req_url_lower
                            or "media" in req_url_lower
                        ):
                            content_type = response.headers.get("content-type", "")
                            if "video" in content_type or "octet-stream" in content_type or ".mp4" in req_url_lower:
                                captured_video_urls.append(req_url)
                    except Exception:
                        pass

                page.on("response", lambda res: handle_response(res))

                try:
                    print(f"正在访问: {url}")
                    await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
                    try:
                        await page.wait_for_selector(
                            "#detail-desc, [class*='detail-desc'], [class*='note-desc'], article, video",
                            timeout=12_000,
                        )
                    except Exception:
                        pass
                    await page.wait_for_timeout(800)

                    # 提取标题
                    title = ""
                    title_selectors = [
                        "#detail-title",
                        '[class*="detail-title"]',
                        '[class*="Title"]',
                        ".title",
                        "h1",
                        '[class*="note-title"]',
                    ]
                    for sel in title_selectors:
                        try:
                            elem = page.locator(sel).first
                            if await elem.count() > 0:
                                t = (await elem.text_content()) or ""
                                t = t.strip()
                                if t and 2 < len(t) < 200:
                                    title = t
                                    break
                        except Exception:
                            continue
                    if not title:
                        try:
                            title = (await page.title() or "").strip()
                            if " - 小红书" in title:
                                title = title.replace(" - 小红书", "").strip()
                            if len(title) < 2:
                                title = ""
                        except Exception:
                            pass

                    # 提取正文内容
                    content = ""
                    content_selectors = [
                        "#detail-desc",
                        '[class*="detail-desc"]',
                        '[class*="Desc"]',
                        '[class*="note-desc"]',
                        '[class*="description"]',
                        ".desc",
                        '[class*="content"]',
                        "article",
                        ".note-text",
                    ]
                    for sel in content_selectors:
                        try:
                            elem = page.locator(sel).first
                            if await elem.count() > 0:
                                c = (await elem.text_content()) or ""
                                c = c.strip()
                                if c and len(c) > 10:
                                    content = c[:5000]
                                    break
                        except Exception:
                            continue

                    # 兜底：从主内容区提取所有可见文字
                    if not content or len(content) < 20:
                        try:
                            full_text = await page.evaluate(
                                """() => {
                                const main = document.querySelector('main') || document.querySelector('[class*="detail"]') || document.body;
                                return main ? main.innerText : document.body.innerText;
                            }"""
                            )
                            if full_text and isinstance(full_text, str):
                                lines = [l.strip() for l in full_text.split("\\n") if len(l.strip()) > 5]
                                content = "\\n".join(lines[:50])[:3000] if lines else content
                        except Exception:
                            pass

                    # 检测是否为视频
                    video_url = None
                    has_video_element = False
                    try:
                        out = await page.evaluate(
                            """() => {
                            const video = document.querySelector('video');
                            if (!video) return { url: null, hasVideo: false };
                            const u = video.src || video.currentSrc;
                            const hasVideo = true;
                            if (u && u.startsWith('http') && !u.startsWith('blob:')) return { url: u, hasVideo };
                            const s = video.querySelector('source');
                            if (s && s.src && !s.src.startsWith('blob:')) return { url: s.src, hasVideo };
                            if (s) { const src = s.getAttribute('src'); if (src && !src.startsWith('blob:')) return { url: src, hasVideo }; }
                            return { url: null, hasVideo };
                        }"""
                        )
                        if isinstance(out, dict):
                            video_url = out.get("url")
                            has_video_element = out.get("hasVideo", False)

                        if not video_url:
                            video_elem = page.locator("video").first
                            if await video_elem.count() > 0:
                                has_video_element = True
                                video_url = await video_elem.get_attribute("src")

                        if not video_url:
                            source = page.locator("video source").first
                            if await source.count() > 0:
                                video_url = await source.get_attribute("src")

                        if video_url and str(video_url).strip().lower().startswith("blob:"):
                            video_url = None

                        if not video_url and captured_video_urls:
                            seen = set()
                            for u in captured_video_urls:
                                if u not in seen and "http" in u and "blob" not in u:
                                    seen.add(u)
                                    video_url = u
                                    print("📎 从网络请求捕获视频 URL")
                                    break
                    except Exception:
                        pass

                    # 提取图片
                    images = []
                    try:
                        img_elements = await page.locator('img[class*="note"], img[class*="photo"]').all()
                        for img in img_elements[:10]:
                            src = await img.get_attribute("src")
                            if src and ("http" in src) and ("avatar" not in src):
                                images.append(src)
                    except Exception:
                        pass

                    # 非 persistent 模式保存 cookies.json（persistent 不需要）
                    if browser is not None:
                        try:
                            cookies = await context.cookies()
                            self.save_cookies_sync(cookies)
                        except Exception:
                            pass

                    if content and len(content) < 120:
                        print("⚠️ 正文偏短，可能未加载到真实内容/被风控")
                    if not title:
                        print("⚠️ 标题未提取到（可能 selector 失效或内容未加载）")

                    result = {
                        "success": True,
                        "url": url,
                        "title": title,
                        "content": content,
                        "type": "video" if (video_url or has_video_element) else "image",
                        "video_url": video_url,
                        "images": images,
                    }

                    print(f"✅ 爬取成功 | 标题:{title[:40] if title else '(未提取)'} | 正文:{len(content)}字")
                    return result

                except Exception as e:
                    print(f"❌ 爬取失败: {str(e)}")
                    return {
                        "success": False,
                        "error": str(e),
                        "url": url,
                    }
                finally:
                    try:
                        await context.close()
                    except Exception:
                        pass
                    if browser is not None:
                        try:
                            await browser.close()
                        except Exception:
                            pass


# 测试代码（需用 asyncio.run 运行）
if __name__ == "__main__":
    crawler = XiaohongshuCrawler()

    async def main():
        result = await crawler.crawl("https://www.xiaohongshu.com/explore/xxx")  # 替换为实际URL
        print(json.dumps(result, ensure_ascii=False, indent=2))

    asyncio.run(main())
