# RedNote (Xiaohongshu AI Chat) — Technology Roadmap

## 1. System Architecture Overview

```mermaid
flowchart TB
    subgraph User["User"]
        Browser[Browser]
    end

    subgraph Frontend["Frontend · localhost:3000"]
        Next[Next.js 14]
        React[React 18 + TypeScript]
        Tailwind[Tailwind CSS]
        Next --> React
        Next --> Tailwind
    end

    subgraph Proxy["Next Rewrites"]
        API["/api/* → 127.0.0.1:8000"]
    end

    subgraph Backend["Backend · 127.0.0.1:8000"]
        FastAPI[FastAPI]
        Crawler[Playwright Crawler]
        Groq[Groq API]
        OCR[PaddleOCR]
        Video[Video Transcript]
        Store[(posts_store in-memory)]
        FastAPI --> Crawler
        FastAPI --> Groq
        FastAPI --> OCR
        FastAPI --> Video
        FastAPI --> Store
    end

    subgraph External["External"]
        XHS[Xiaohongshu]
        GroqCloud[Groq Cloud]
    end

    Browser --> Next
    Next --> API
    API --> FastAPI
    Crawler --> XHS
    Groq --> GroqCloud
```

---

## 2. Tech Stack by Layer

```mermaid
flowchart LR
    subgraph Presentation["Presentation"]
        A1[Next.js]
        A2[React]
        A3[TypeScript]
        A4[Tailwind]
    end

    subgraph Gateway["Gateway / Proxy"]
        B1[Next rewrites]
        B2[127.0.0.1 proxy]
    end

    subgraph Service["Service"]
        C1[FastAPI]
        C2[Pydantic]
        C3[Uvicorn]
    end

    subgraph Crawl["Crawler & Enrichment"]
        D1[Playwright]
        D2[asyncio.Lock]
        D3[Short-link resolve]
    end

    subgraph AI["AI & Multimodal"]
        E1[Groq]
        E2[PaddleOCR]
        E3[yt-dlp / video]
    end

    subgraph Data["Data"]
        F1[In-memory posts_store]
    end

    Presentation --> Gateway --> Service
    Service --> Crawl
    Service --> AI
    Service --> Data
```

---

## 3. Crawl Flow (/api/crawl)

```mermaid
sequenceDiagram
    participant U as User
    participant F as Frontend
    participant B as FastAPI
    participant C as Crawler
    participant P as Playwright
    participant X as Xiaohongshu

    U->>F: Enter URL
    F->>B: POST /api/crawl { url, max_posts? }
    B->>B: is_profile_url?
    alt Profile page
        B->>C: get_profile_post_links(url, max_posts)
        Note over C: async with CRAWL_LOCK
        C->>P: async_playwright()
        P->>X: Open profile + resolve short link
        X-->>P: DOM
        C->>C: page.evaluate extract explore links
        C-->>B: [url1, url2, ...]
        loop Each post
            B->>C: crawl(post_url)
            Note over C: async with CRAWL_LOCK
            C->>P: goto + extract title/content/images/video
            P->>X: Load note page
            X-->>C: Content
            C-->>B: crawl_result
        end
        B->>B: Merge content + video transcript + OCR
    else Single post
        B->>C: crawl(url)
        C->>P: Open page and extract
        P->>X: Load
        X-->>B: Single result
        B->>B: Video transcript + OCR
    end
    B->>B: Write to posts_store
    B-->>F: { success, post_id, data }
    F-->>U: Enter chat
```

---

## 4. Chat Flow (/api/chat)

```mermaid
sequenceDiagram
    participant U as User
    participant F as Frontend
    participant B as FastAPI
    participant S as posts_store
    participant G as Groq

    U->>F: Enter message
    F->>B: POST /api/chat { message, post_id }
    B->>S: Get posts_store[post_id]
    S-->>B: full_content
    B->>B: Build system + history + current message
    B->>G: Groq API generate reply
    G-->>B: Reply text
    B-->>F: Stream or single response
    F-->>U: Show AI reply
```

---

## 5. Technology Summary

| Layer   | Technology        | Description |
|---------|-------------------|-------------|
| Frontend| Next.js 14        | React framework, App Router, rewrites proxy |
| Frontend| React 18          | UI and interaction |
| Frontend| TypeScript        | Types and interfaces |
| Frontend| Tailwind CSS      | Styling |
| Backend | FastAPI           | API, validation, error handling |
| Backend | Uvicorn           | ASGI server |
| Crawler | Playwright (async)| Browser automation, short-link resolve, DOM extraction |
| Crawler | asyncio.Lock      | Global lock, one browser task at a time |
| AI      | Groq              | LLM chat |
| Multimodal | PaddleOCR     | Image text recognition |
| Multimodal | yt-dlp / video | Video download and transcript (optional faster-whisper) |
| Tooling | python-dotenv     | Environment variables |
| Tooling | requests         | Short-link HTTP resolve |

---

## 6. How to View the Diagrams

### In Cursor / VS Code (recommended)

1. **Open this file**  
   Click `TECH_ROADMAP.md` in the file tree, or press `Cmd+P` (Mac) / `Ctrl+P` (Windows) and type `TECH_ROADMAP`.

2. **Open Markdown preview**  
   - Shortcut: **`Cmd+Shift+V`** (Mac) or **`Ctrl+Shift+V`** (Windows)  
   - Or: right-click this file → **Open Preview**  
   - Or: click the “Open preview to the side” icon in the editor toolbar

3. **If Mermaid diagrams don’t render**  
   Install one of these extensions and reopen the preview:  
   - **Markdown Preview Mermaid Support** (search for `Mermaid` or `bierner.markdown-mermaid`)  
   - Or **Mermaid** (by Mermaid)

4. **Side-by-side live preview**  
   `Cmd+K V` (Mac) or `Ctrl+K V` (Windows) to open preview in the side; diagrams update as you edit.

### Other options

- **GitHub**: Push the repo and open this file in the repo; Mermaid will render there.
- **Online**: Copy a ` ```mermaid ` code block into [Mermaid Live Editor](https://mermaid.live) to view or export as PNG/SVG.
