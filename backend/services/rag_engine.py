"""
RAG engine – retrieves transcript chunks and streams LLM responses.

Uses LangGraph for the retrieve → generate pipeline and exposes an
``async stream_chat`` generator consumed by the SSE endpoint.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any, AsyncGenerator

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from config import settings
from models.schemas import ChatChunk, Citation
from services.embeddings import VideoEmbeddingService

logger = logging.getLogger(__name__)


# ── LangGraph state schema ──────────────────────────────────────────────────


class RAGState(TypedDict, total=False):
    messages: list[Any]
    video_data: dict[str, Any]
    retrieved_chunks: list[dict[str, Any]]
    citations: list[dict[str, Any]]
    session_id: str
    current_query: str


# ── RAG engine ──────────────────────────────────────────────────────────────


class RAGEngine:
    """Retrieval-Augmented Generation engine for video comparison chat."""

    def __init__(self, embedding_service: VideoEmbeddingService) -> None:
        self._embeddings = embedding_service
        settings.validate()
        self._llm = ChatGoogleGenerativeAI(
            model=settings.MODEL_NAME,
            google_api_key=settings.GOOGLE_API_KEY,
            temperature=0.3,
            streaming=True,
        )
        self._graph = self._build_graph()

    # ── Graph construction ──────────────────────────────────────────────────

    def _build_graph(self):
        builder = StateGraph(RAGState)
        builder.add_node("retrieve", self._retrieve_node)
        builder.add_node("generate", self._generate_node)
        builder.add_edge(START, "retrieve")
        builder.add_edge("retrieve", "generate")
        builder.add_edge("generate", END)
        return builder.compile()

    # ── Graph nodes ─────────────────────────────────────────────────────────

    def _retrieve_node(self, state: RAGState) -> dict:
        query = state.get("current_query", "")
        session_id = state.get("session_id", "")

        # General search across both videos
        chunks = self._embeddings.search(query, session_id, video_id=None, k=4)

        # Targeted search if the user explicitly mentions a video
        query_lower = query.lower()
        if "video a" in query_lower or "youtube" in query_lower:
            extra = self._embeddings.search(query, session_id, video_id="A", k=2)
            chunks = self._merge_chunks(chunks, extra)
        if "video b" in query_lower or "instagram" in query_lower:
            extra = self._embeddings.search(query, session_id, video_id="B", k=2)
            chunks = self._merge_chunks(chunks, extra)

        return {"retrieved_chunks": chunks}

    def _generate_node(self, state: RAGState) -> dict:
        # This node is only used for the non-streaming graph invocation path.
        messages = self._build_messages(state)
        response = self._llm.invoke(messages)
        response_text = response.content if hasattr(response, "content") else str(response)
        citations = self._parse_citations(response_text, state.get("retrieved_chunks", []))

        history = list(state.get("messages", []))
        history.append(HumanMessage(content=state.get("current_query", "")))
        history.append(AIMessage(content=response_text))

        return {"messages": history, "citations": [c.model_dump() for c in citations]}

    # ── Streaming entry point ───────────────────────────────────────────────

    async def stream_chat(
        self,
        session_id: str,
        message: str,
        video_data: dict[str, Any],
        chat_history: list[dict[str, str]],
    ) -> AsyncGenerator[ChatChunk, None]:
        """Retrieve context, then stream the LLM response token-by-token.

        Yields ``ChatChunk`` instances suitable for SSE serialisation.
        """
        # Step 1 – retrieve
        state: RAGState = {
            "messages": [],
            "video_data": video_data,
            "retrieved_chunks": [],
            "citations": [],
            "session_id": session_id,
            "current_query": message,
        }

        retrieve_result = self._retrieve_node(state)
        state["retrieved_chunks"] = retrieve_result["retrieved_chunks"]

        # Step 2 – build full prompt
        lc_messages = self._build_messages(state, chat_history)

        # Step 3 – stream tokens with retry on 429
        # NOTE: LangChain's Gemini astream sends CUMULATIVE chunks (each chunk
        # contains the full text so far, not just the new token). We compute
        # the diff so the frontend only receives truly new content each time.
        full_response = ""
        MAX_RETRIES = 4
        for attempt in range(MAX_RETRIES):
            try:
                if attempt > 0:
                    yield ChatChunk(type="clear")
                async for chunk in self._llm.astream(lc_messages):
                    raw = chunk.content if hasattr(chunk, "content") else str(chunk)
                    if not raw:
                        continue
                    # Detect cumulative vs incremental chunk:
                    # If raw starts with everything we've accumulated so far,
                    # it's a cumulative chunk — only send the new tail.
                    if full_response and raw.startswith(full_response):
                        new_part = raw[len(full_response):]
                    else:
                        new_part = raw
                    if new_part:
                        full_response += new_part
                        yield ChatChunk(type="token", content=new_part)
                break  # success – exit retry loop
            except Exception as exc:
                err_str = str(exc)
                is_rate_limit = "429" in err_str or "quota" in err_str.lower() or "rate" in err_str.lower()
                if is_rate_limit and attempt < MAX_RETRIES - 1:
                    wait_secs = 15 * (attempt + 1)  # 15s, 30s, 45s back-off
                    logger.warning(
                        "Gemini 429 rate-limit hit (attempt %d/%d). Waiting %ds before retry...",
                        attempt + 1, MAX_RETRIES, wait_secs,
                    )
                    # Tell the frontend to wipe any partial tokens already streamed
                    yield ChatChunk(type="clear")
                    # Then show the waiting message fresh
                    yield ChatChunk(
                        type="token",
                        content=f"\u23f3 *Rate limit hit \u2014 retrying in {wait_secs}s (attempt {attempt + 1}/{MAX_RETRIES - 1})...*\n\n",
                    )
                    await asyncio.sleep(wait_secs)
                    full_response = ""  # reset accumulator
                    lc_messages = self._build_messages(state, chat_history)
                else:
                    logger.error("LLM streaming error (non-retriable): %s", exc)
                    yield ChatChunk(type="error", content=f"LLM error: {exc}")
                    return

        # Step 4 – emit citations
        citations = self._parse_citations(full_response, state.get("retrieved_chunks", []))
        if citations:
            yield ChatChunk(
                type="citation",
                citations=citations,
            )

        # Step 5 – done
        yield ChatChunk(type="done")

    # ── Prompt construction ─────────────────────────────────────────────────

    def _build_messages(
        self,
        state: RAGState,
        chat_history: list[dict[str, str]] | None = None,
    ) -> list:
        """Assemble the full LangChain message list for the LLM."""
        video_data = state.get("video_data", {})
        video_a = video_data.get("video_a", {})
        video_b = video_data.get("video_b", {})
        chunks = state.get("retrieved_chunks", [])
        query = state.get("current_query", "")

        # ── System prompt
        system_text = self._build_system_prompt(video_a, video_b, chunks)
        messages: list = [SystemMessage(content=system_text)]

        # ── Conversation history
        history = chat_history or []
        for turn in history:
            role = turn.get("role", "user")
            content = turn.get("content", "")
            if role == "user":
                messages.append(HumanMessage(content=content))
            else:
                messages.append(AIMessage(content=content))

        # ── Current user query
        messages.append(HumanMessage(content=query))

        return messages

    @staticmethod
    def _build_system_prompt(
        video_a: dict, video_b: dict, chunks: list[dict]
    ) -> str:
        chunk_section = ""
        if chunks:
            chunk_lines: list[str] = []
            for c in chunks:
                vid = c.get("video_id", "?")
                idx = c.get("chunk_index", "?")
                text = c.get("content", "")
                chunk_lines.append(f"  [Video {vid}, Chunk {idx}]: {text}")
            chunk_section = (
                "\n\n## Retrieved Transcript Excerpts\n" + "\n".join(chunk_lines)
            )

        return f"""You are a social media video performance analyst.

Compare **Video A** and **Video B** using the data below.

## Video A
- Title: {video_a.get('title', 'N/A')}
- Platform: {video_a.get('platform', 'N/A')}
- Creator: {video_a.get('creator', 'N/A')}
- Views: {video_a.get('views', 'N/A')} | Likes: {video_a.get('likes', 'N/A')} | Comments: {video_a.get('comments', 'N/A')}
- Engagement Rate: {video_a.get('engagement_rate', 'N/A')}%
- Duration: {video_a.get('duration', 'N/A')} | Uploaded: {video_a.get('upload_date', 'N/A')}
- Hashtags: {', '.join(video_a.get('hashtags', [])) or 'None'}

## Video B
- Title: {video_b.get('title', 'N/A')}
- Platform: {video_b.get('platform', 'N/A')}
- Creator: {video_b.get('creator', 'N/A')}
- Views: {video_b.get('views', 'N/A')} | Likes: {video_b.get('likes', 'N/A')} | Comments: {video_b.get('comments', 'N/A')}
- Engagement Rate: {video_b.get('engagement_rate', 'N/A')}%
- Duration: {video_b.get('duration', 'N/A')} | Uploaded: {video_b.get('upload_date', 'N/A')}
- Hashtags: {', '.join(video_b.get('hashtags', [])) or 'None'}
{chunk_section}

## Instructions
- Use metadata AND transcript excerpts to answer the question.
- Cite transcripts as [Video A, Chunk X] or [Video B, Chunk Y].
- Be specific, data-driven, and concise.
- If transcript is unavailable, rely on metadata only.
"""

    # ── Citation parsing ────────────────────────────────────────────────────

    @staticmethod
    def _parse_citations(
        response_text: str, retrieved_chunks: list[dict]
    ) -> list[Citation]:
        """Extract ``[Video X, Chunk Y]`` references from the LLM response."""
        pattern = re.compile(r"\[Video\s+([AB]),\s*Chunk\s+(\d+)\]", re.IGNORECASE)
        matches = pattern.findall(response_text)

        # Build a lookup for fast matching
        chunk_lookup: dict[tuple[str, int], str] = {}
        for c in retrieved_chunks:
            key = (c.get("video_id", "").upper(), int(c.get("chunk_index", -1)))
            chunk_lookup[key] = c.get("content", "")

        seen: set[tuple[str, int]] = set()
        citations: list[Citation] = []
        for vid_letter, chunk_idx_str in matches:
            vid = vid_letter.upper()
            idx = int(chunk_idx_str)
            if (vid, idx) in seen:
                continue
            seen.add((vid, idx))

            chunk_text = chunk_lookup.get((vid, idx), "")
            citations.append(
                Citation(video_id=vid, chunk_text=chunk_text, chunk_index=idx)
            )

        return citations

    # ── Utility ─────────────────────────────────────────────────────────────

    @staticmethod
    def _merge_chunks(
        base: list[dict], extra: list[dict]
    ) -> list[dict]:
        """Merge *extra* chunks into *base*, avoiding duplicates by id."""
        seen_ids = {
            (c.get("video_id"), c.get("chunk_index")) for c in base
        }
        for c in extra:
            key = (c.get("video_id"), c.get("chunk_index"))
            if key not in seen_ids:
                base.append(c)
                seen_ids.add(key)
        return base
