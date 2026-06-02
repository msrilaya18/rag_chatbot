import logging
import uuid
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from config import settings
from models.schemas import (
    VideoInput,
    VideoMetadata,
    AnalyzeResponse,
    ChatRequest,
    ChatChunk,
)
from services.transcript import get_youtube_transcript, get_instagram_transcript
from services.metadata import get_youtube_metadata, get_instagram_metadata
from services.embeddings import VideoEmbeddingService
from services.rag_engine import RAGEngine


def _is_youtube(url: str) -> bool:
    return "youtube.com" in url or "youtu.be" in url


def _get_metadata(url: str) -> dict:
    if _is_youtube(url):
        return get_youtube_metadata(url)
    return get_instagram_metadata(url)


def _get_transcript(url: str) -> str:
    if _is_youtube(url):
        return get_youtube_transcript(url)
    return get_instagram_transcript(url)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="RAG Video Comparison Chatbot API",
    description="Backend API for comparing YouTube and Instagram videos with LangGraph RAG",
)

# CORS middleware to allow the frontend to communicate with the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global service instances
embeddings_service: VideoEmbeddingService = None  # type: ignore
rag_engine: RAGEngine = None  # type: ignore

import json
import os

SESSIONS_FILE = os.path.join(os.path.dirname(__file__), "sessions_db.json")

def load_sessions() -> dict:
    if os.path.exists(SESSIONS_FILE):
        try:
            with open(SESSIONS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error("Failed to load sessions from disk: %s", e)
    return {}

def save_sessions(data: dict):
    try:
        with open(SESSIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error("Failed to save sessions to disk: %s", e)

# Persistent session store loaded from disk
sessions: dict[str, dict] = load_sessions()


@app.on_event("startup")
async def startup_event():
    global embeddings_service, rag_engine
    logger.info("Initializing services on startup...")
    try:
        embeddings_service = VideoEmbeddingService()
        rag_engine = RAGEngine(embeddings_service)
        logger.info("Services initialized successfully.")

        # Purge sessions whose embeddings no longer exist in ChromaDB
        # (happens when ChromaDB data is cleared but sessions_db.json persists)
        stale_ids = []
        for sid in list(sessions.keys()):
            try:
                results = embeddings_service._collection.get(
                    where={"session_id": sid}, limit=1
                )
                if not results or not results.get("ids"):
                    stale_ids.append(sid)
            except Exception:
                stale_ids.append(sid)

        if stale_ids:
            for sid in stale_ids:
                del sessions[sid]
            save_sessions(sessions)
            logger.info("Purged %d stale session(s) with no embeddings.", len(stale_ids))

    except Exception as exc:
        logger.error("Failed to initialize services during startup: %s", exc)
        # We don't crash the server immediately so that configuration errors
        # can be diagnosed via endpoint errors or logs, but logs are explicit.


@app.get("/api/health")
def health_check():
    return {"status": "ok", "google_api_key_configured": bool(settings.GOOGLE_API_KEY)}


@app.post("/api/analyze", response_model=AnalyzeResponse)
async def analyze_videos(payload: VideoInput):
    """Analyze a YouTube video and an Instagram video, extract transcripts and metadata, and index transcripts."""
    if not embeddings_service or not rag_engine:
        raise HTTPException(
            status_code=500,
            detail="AI services are not fully initialized. Check backend environment configuration.",
        )

    # Validate that we have the API key
    try:
        settings.validate()
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    url_a = payload.video_a_url
    url_b = payload.video_b_url
    logger.info("Analyzing Video A: %s", url_a)
    logger.info("Analyzing Video B: %s", url_b)

    # 1. Fetch metadata (auto-detects platform)
    try:
        metadata_a = _get_metadata(url_a)
    except Exception as exc:
        logger.error("Failed to fetch Video A metadata: %s", exc)
        raise HTTPException(
            status_code=400,
            detail=f"Failed to fetch Video A metadata: {str(exc)}",
        )

    try:
        metadata_b = _get_metadata(url_b)
    except Exception as exc:
        logger.error("Failed to fetch Video B metadata: %s", exc)
        raise HTTPException(
            status_code=400,
            detail=f"Failed to fetch Video B metadata: {str(exc)}",
        )

    # 2. Fetch transcripts
    transcript_a = ""
    try:
        transcript_a = _get_transcript(url_a)
    except Exception as exc:
        logger.warning("Failed to fetch Video A transcript: %s", exc)
        transcript_a = f"[Transcript unavailable for Video A. Error: {str(exc)}]"

    transcript_b = ""
    try:
        transcript_b = _get_transcript(url_b)
    except Exception as exc:
        logger.warning("Failed to fetch Video B transcript: %s", exc)
        transcript_b = f"[Transcript unavailable for Video B. Error: {str(exc)}]"

    # 3. Create session
    session_id = str(uuid.uuid4())

    # 4. Embed transcripts
    try:
        embeddings_service.embed_video_transcript(
            transcript=transcript_a,
            video_id="A",
            metadata=metadata_a,
            session_id=session_id,
        )
    except Exception as exc:
        logger.error("Failed to embed YouTube transcript: %s", exc)

    try:
        embeddings_service.embed_video_transcript(
            transcript=transcript_b,
            video_id="B",
            metadata=metadata_b,
            session_id=session_id,
        )
    except Exception as exc:
        logger.error("Failed to embed Instagram transcript: %s", exc)

    # 5. Store session data
    sessions[session_id] = {
        "video_a": metadata_a,
        "video_b": metadata_b,
        "chat_history": [],
    }
    save_sessions(sessions)

    return AnalyzeResponse(
        session_id=session_id,
        video_a=VideoMetadata(**metadata_a),
        video_b=VideoMetadata(**metadata_b),
    )


@app.post("/api/chat")
async def chat_sse(payload: ChatRequest):
    """Streaming chat endpoint using Server-Sent Events (SSE)."""
    if not embeddings_service or not rag_engine:
        raise HTTPException(
            status_code=500,
            detail="AI services are not fully initialized.",
        )

    session_id = payload.session_id
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found.")

    session_data = sessions[session_id]
    video_data = {
        "video_a": session_data["video_a"],
        "video_b": session_data["video_b"],
    }
    chat_history = session_data["chat_history"]

    async def event_generator():
        full_response = ""
        citations = []

        try:
            async for chunk in rag_engine.stream_chat(
                session_id=session_id,
                message=payload.message,
                video_data=video_data,
                chat_history=chat_history,
            ):
                # Accumulate the response content to update the history later
                if chunk.type == "token":
                    full_response += chunk.content
                elif chunk.type == "citation":
                    citations.extend(chunk.citations)

                # Yield in SSE format
                yield {
                    "event": "message",
                    "data": chunk.model_dump_json(),
                }

            # Update session chat history
            chat_history.append({"role": "user", "content": payload.message})
            chat_history.append({"role": "assistant", "content": full_response})
            save_sessions(sessions)

        except Exception as exc:
            logger.error("Error in event_generator: %s", exc)
            err_chunk = ChatChunk(type="error", content=str(exc))
            yield {
                "event": "message",
                "data": err_chunk.model_dump_json(),
            }

    return EventSourceResponse(event_generator())


@app.get("/api/session/{session_id}")
async def get_session(session_id: str):
    """Retrieve session metadata and chat history."""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found.")
    return sessions[session_id]


@app.delete("/api/session/{session_id}")
async def delete_session(session_id: str):
    """Delete session data and clean up vector store entries."""
    if session_id in sessions:
        try:
            embeddings_service.clear_session(session_id)
        except Exception as exc:
            logger.error("Failed to clear vector store for session %s: %s", session_id, exc)
        del sessions[session_id]
        save_sessions(sessions)
        return {"status": "deleted"}
    raise HTTPException(status_code=404, detail="Session not found.")
