"""
Embedding service: chunk transcripts, store in ChromaDB, and query.
"""

from __future__ import annotations

import logging
from typing import Any

import chromadb
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from config import settings

logger = logging.getLogger(__name__)


# ── ChromaDB-compatible embedding wrapper ───────────────────────────────────


class _ChromaEmbeddingFunction:
    """Wraps LangChain's GoogleGenerativeAIEmbeddings so ChromaDB can call it."""

    def __init__(self, langchain_embeddings: GoogleGenerativeAIEmbeddings) -> None:
        self._embeddings = langchain_embeddings

    def __call__(self, input: list[str]) -> list[list[float]]:  # noqa: A002
        return self._embeddings.embed_documents(input)


# ── Public service class ────────────────────────────────────────────────────


class VideoEmbeddingService:
    """Manages transcript chunking, embedding, and retrieval via ChromaDB."""

    def __init__(self) -> None:
        settings.validate()

        # LangChain embedding model (Google Generative AI)
        self._lc_embeddings = GoogleGenerativeAIEmbeddings(
            model=settings.EMBEDDING_MODEL,
            google_api_key=settings.GOOGLE_API_KEY,
        )

        # ChromaDB – persistent client so data survives server reloads
        self._chroma_client = chromadb.PersistentClient(path=settings.CHROMA_PERSIST_DIR)

        # Wrap the LangChain embeddings for Chroma
        self._chroma_ef = _ChromaEmbeddingFunction(self._lc_embeddings)

        # Single collection for all video transcripts (isolated by session_id)
        self._collection = self._chroma_client.get_or_create_collection(
            name="video_transcripts",
            embedding_function=self._chroma_ef,  # type: ignore[arg-type]
        )

        # Text splitter
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.CHUNK_SIZE,
            chunk_overlap=settings.CHUNK_OVERLAP,
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""],
        )

    # ── Write ───────────────────────────────────────────────────────────────

    def embed_video_transcript(
        self,
        transcript: str,
        video_id: str,
        metadata: dict[str, Any],
        session_id: str,
    ) -> int:
        """Chunk and embed a transcript into ChromaDB.

        Args:
            transcript: Full transcript text.
            video_id:   ``"A"`` or ``"B"``.
            metadata:   Dict with at least ``platform``, ``title``, ``creator``.
            session_id: Unique session identifier for isolation.

        Returns:
            Number of chunks stored.
        """
        if not transcript or not transcript.strip():
            logger.warning("Empty transcript for video %s – skipping embedding.", video_id)
            return 0

        chunks = self._splitter.split_text(transcript)
        if not chunks:
            return 0

        ids: list[str] = []
        documents: list[str] = []
        metadatas: list[dict[str, Any]] = []

        for i, chunk in enumerate(chunks):
            ids.append(f"{session_id}_{video_id}_{i}")
            documents.append(chunk)
            metadatas.append(
                {
                    "video_id": video_id,
                    "session_id": session_id,
                    "chunk_index": i,
                    "platform": metadata.get("platform", "Unknown"),
                    "title": metadata.get("title", "Unknown"),
                    "creator": metadata.get("creator", "Unknown"),
                }
            )

        self._collection.add(ids=ids, documents=documents, metadatas=metadatas)
        logger.info(
            "Stored %d chunks for video %s in session %s", len(chunks), video_id, session_id
        )
        return len(chunks)

    # ── Read ────────────────────────────────────────────────────────────────

    def search(
        self,
        query: str,
        session_id: str,
        video_id: str | None = None,
        k: int = 5,
    ) -> list[dict[str, Any]]:
        """Retrieve the top-*k* relevant chunks for *query*.

        Results are always scoped to the given *session_id*. Optionally
        further filtered to a single *video_id* (``"A"`` or ``"B"``).
        """
        where_filter: dict[str, Any] = {"session_id": session_id}
        if video_id:
            where_filter = {
                "$and": [
                    {"session_id": session_id},
                    {"video_id": video_id},
                ]
            }

        try:
            results = self._collection.query(
                query_texts=[query],
                n_results=k,
                where=where_filter,
            )
        except Exception as exc:
            logger.error("ChromaDB query failed: %s", exc)
            return []

        items: list[dict[str, Any]] = []
        if results and results.get("documents"):
            docs = results["documents"][0]
            metas = results["metadatas"][0] if results.get("metadatas") else [{}] * len(docs)

            for doc, meta in zip(docs, metas):
                items.append(
                    {
                        "content": doc,
                        "video_id": meta.get("video_id", "?"),
                        "chunk_index": meta.get("chunk_index", -1),
                        "metadata": meta,
                    }
                )

        return items

    # ── Cleanup ─────────────────────────────────────────────────────────────

    def clear_session(self, session_id: str) -> None:
        """Remove all stored chunks for a given session."""
        try:
            self._collection.delete(where={"session_id": session_id})
            logger.info("Cleared embeddings for session %s", session_id)
        except Exception as exc:
            logger.warning("Failed to clear session %s: %s", session_id, exc)
