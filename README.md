# RAG Social Video Chatbot

A full-stack RAG (Retrieval-Augmented Generation) chatbot that compares two social media videos — YouTube Shorts and Instagram Reels — using real transcript data, engagement metrics, and an AI chat interface.

## Demo

> Live demo: [localhost:3000](http://localhost:3000)  
> Stack: Next.js + FastAPI + LangGraph + ChromaDB + Gemini

---

## Features

- **Two-video comparison** — paste any YouTube and Instagram Reel URL
- **Transcript extraction** — via `youtube-transcript-api` + `yt-dlp`
- **Metadata scraping** — views, likes, comments, creator, follower count, hashtags, upload date, duration
- **Engagement rate computation** — `(likes + comments) / views × 100`
- **Chunked embeddings** — transcripts chunked and stored in ChromaDB, tagged with `video_id` (A or B)
- **LangGraph RAG pipeline** — retrieve → generate with full context
- **Streaming responses** — token-by-token SSE streaming to the frontend
- **Source citations** — every answer cites which video + which chunk it came from
- **Multi-turn memory** — conversation history maintained per session
- **Session persistence** — localStorage-backed session recovery on page refresh

---

## Tech Stack

| Layer | Choice | Reason |
|---|---|---|
| **Frontend** | Next.js 15 (App Router) | SSE streaming support, server-side proxying, React |
| **Backend** | FastAPI + Uvicorn | Async-first, native SSE, fast startup |
| **Orchestration** | LangGraph | Stateful graph pipeline for retrieve → generate |
| **Embeddings** | `gemini-embedding-001` | Free tier, 3072-dim vectors, zero infra |
| **Vector DB** | ChromaDB (persistent) | Zero infra, runs in-process, easy to swap to Pinecone |
| **LLM** | Gemini 2.5 Flash | Best speed/cost ratio; 1M token context |
| **Transcript** | `youtube-transcript-api` + `yt-dlp` | Free, no API key needed |

---

## Architecture

```
Browser (Next.js)
    │  POST /api/analyze  →  FastAPI
    │                          ├── yt-dlp / youtube-transcript-api  → transcript
    │                          ├── yt-dlp metadata scraper           → metadata
    │                          └── ChromaDB embed + store            → vector DB
    │
    │  POST /api/chat     →  FastAPI
    │                          └── LangGraph (retrieve → generate)
    │                               ├── ChromaDB similarity search
    │                               └── Gemini 2.5 Flash streaming
    │
    └── SSE stream  ←  token chunks + citations
```

---

## Scalability & Cost Analysis

### At 1,000 creators/day

| Component | Current (free tier) | At scale |
|---|---|---|
| Embeddings | Gemini free (1500 req/day) | Switch to `text-embedding-3-small` @ $0.02/1M tokens |
| LLM | Gemini 2.5 Flash free | ~$0.075/1M input tokens — ~$0.003 per chat turn |
| Vector DB | ChromaDB local | Migrate to Pinecone Serverless ($0.096/1M reads) |
| Transcript | `youtube-transcript-api` free | Free — no cost scaling |
| Infra | Local | Containerize with Docker; deploy to Cloud Run (auto-scales, pay-per-request) |

**Estimated cost at 1,000 creators/day (10 chat turns each):**
- Embeddings: ~$0.10/day
- LLM (10 turns × 2k tokens): ~$3.00/day
- Pinecone: ~$0.50/day
- **Total: ~$3.60/day** at 1,000 creators (< $0.004 per creator)

### Why this stack wins on cost/quality:
1. **Gemini 2.5 Flash** has the best tokens-per-dollar ratio of any frontier model
2. **ChromaDB → Pinecone** is a one-line swap (same interface via LangChain)
3. **LangGraph** makes it trivial to add caching, parallelism, or fallback LLMs
4. **FastAPI + Cloud Run** = zero idle cost, scales to 0 automatically

---

## Setup

### Prerequisites
- Python 3.10+
- Node.js 18+
- Google API Key (free at [aistudio.google.com](https://aistudio.google.com/apikey))

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Mac/Linux

pip install -r requirements.txt

cp ../.env.example .env
# Edit .env and set your GOOGLE_API_KEY

uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000)

---

## Deployment Guide

### 1. Backend Deployment (Render or Railway)
Deploy the FastAPI backend container to Render or Railway using the included `Dockerfile`:
* **Render.com Setup:**
  1. Create a free account on [Render.com](https://render.com) and click **New +** -> **Web Service**.
  2. Connect your GitHub repository.
  3. Set the **Root Directory** to `backend/`.
  4. Select **Docker** as the Runtime (Render will automatically detect the `Dockerfile`).
  5. Under **Environment Variables**, add:
     * `GOOGLE_API_KEY`: Your Gemini API key from AI Studio.
  6. Click **Deploy Web Service**. Once deployed, copy your live backend URL (e.g., `https://rag-chatbot-backend.onrender.com`).

### 2. Frontend Deployment (Vercel)
Deploy the Next.js frontend to Vercel (free, automatic builds on push):
1. Sign up on [Vercel](https://vercel.com) and import this GitHub repository.
2. Set the **Root Directory** to `frontend/`.
3. Under **Environment Variables**, add:
   * `BACKEND_URL`: Your live backend URL from the step above (e.g., `https://rag-chatbot-backend.onrender.com`).
4. Click **Deploy**. Vercel will generate your live frontend URL (e.g., `https://rag-chatbot.vercel.app`).

---

## Usage

1. Paste a **YouTube** URL (video, short, or regular) into **Video A**
2. Paste an **Instagram Reel** URL into **Video B**
3. Click **Analyze & Initialize Chat**
4. Ask questions in the chat panel:
   - *"Why did Video A get more engagement than Video B?"*
   - *"What's the engagement rate of each?"*
   - *"Compare the hooks in the first 5 seconds."*
   - *"Who's the creator of Video B and what's their follower count?"*
   - *"Suggest improvements for B based on what worked in A."*

---

## Project Structure

```
proj/
├── backend/
│   ├── main.py                  # FastAPI app + endpoints
│   ├── config.py                # Settings / env vars
│   ├── requirements.txt
│   ├── .env.example
│   ├── models/
│   │   └── schemas.py           # Pydantic models
│   └── services/
│       ├── embeddings.py        # ChromaDB + embedding service
│       ├── metadata.py          # yt-dlp metadata scraper
│       ├── rag_engine.py        # LangGraph RAG pipeline
│       └── transcript.py        # Transcript extraction
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── page.js          # Main page
│   │   │   ├── layout.js
│   │   │   └── globals.css
│   │   └── components/
│   │       ├── ChatPanel.js     # SSE streaming chat
│   │       ├── InputForm.js     # URL input + validation
│   │       ├── MessageBubble.js # Chat message renderer
│   │       └── VideoCard.js     # Video metadata card
│   └── next.config.mjs          # API proxy to backend
├── .env.example
├── .gitignore
└── README.md
```

---

## API Reference

### `POST /api/analyze`
Analyze two video URLs. Returns session ID + metadata for both videos.

**Body:**
```json
{
  "video_a_url": "https://youtube.com/shorts/...",
  "video_b_url": "https://www.instagram.com/reel/..."
}
```

### `POST /api/chat`
Stream a chat response (SSE).

**Body:**
```json
{
  "session_id": "uuid",
  "message": "What's the engagement rate of each?"
}
```

### `GET /api/session/{session_id}`
Get session metadata and chat history.

### `DELETE /api/session/{session_id}`
Delete a session and clear its vector store entries.

---

## Environment Variables

```env
GOOGLE_API_KEY=your_gemini_api_key_here
CHROMA_PERSIST_DIR=./chroma_data
BACKEND_PORT=8000
FRONTEND_PORT=3000
```

---

## Trade-offs & Known Limitations

- **Instagram metadata**: yt-dlp can extract basic metadata but follower counts require authenticated scraping (Instagram blocks unauthenticated API calls). The system gracefully falls back to available data.
- **Transcript availability**: Some YouTube Shorts and all Instagram Reels lack auto-generated captions. The system falls back to metadata-only answers in these cases.
- **Free-tier rate limits**: Gemini free tier has per-minute token limits. The backend implements automatic retry with exponential backoff.
- **ChromaDB**: Not production-grade for high concurrency. Swap to Pinecone Serverless for production.

---

## License

MIT
