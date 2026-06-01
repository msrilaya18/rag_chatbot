"""
Transcript extraction for YouTube and Instagram videos.
"""

from __future__ import annotations

import logging
import re
import subprocess
import tempfile
from pathlib import Path

from youtube_transcript_api import YouTubeTranscriptApi

logger = logging.getLogger(__name__)


# ── Helpers ─────────────────────────────────────────────────────────────────

_YT_PATTERNS = [
    re.compile(r"(?:youtube\.com/watch\?.*v=)([A-Za-z0-9_-]{11})"),
    re.compile(r"(?:youtu\.be/)([A-Za-z0-9_-]{11})"),
    re.compile(r"(?:youtube\.com/shorts/)([A-Za-z0-9_-]{11})"),
    re.compile(r"(?:youtube\.com/embed/)([A-Za-z0-9_-]{11})"),
]


def _extract_youtube_id(url: str) -> str:
    """Return the 11-character YouTube video ID from *url*."""
    for pattern in _YT_PATTERNS:
        match = pattern.search(url)
        if match:
            return match.group(1)
    raise ValueError(f"Could not extract a YouTube video ID from: {url}")


# ── Public API ──────────────────────────────────────────────────────────────


def get_youtube_transcript(url: str) -> str:
    """Fetch the full transcript text for a YouTube video.

    Attempts English variants first, then falls back to any translatable
    transcript.

    Raises:
        ValueError: when no usable transcript is found.
    """
    video_id = _extract_youtube_id(url)

    # 1. Try direct fetch for English variants
    preferred_languages = ["en", "en-US", "en-GB"]
    try:
        entries = YouTubeTranscriptApi.get_transcript(
            video_id, languages=preferred_languages
        )
        return " ".join(entry["text"] for entry in entries)
    except Exception:
        logger.debug("Direct English transcript not available for %s", video_id)

    # 2. List all available transcripts and look for a translatable one
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)

        # Try manually created transcripts first
        for transcript in transcript_list:
            if transcript.language_code.startswith("en"):
                entries = transcript.fetch()
                return " ".join(entry["text"] for entry in entries)

        # Fall back to any transcript that can be translated to English
        for transcript in transcript_list:
            if transcript.is_translatable:
                translated = transcript.translate("en")
                entries = translated.fetch()
                return " ".join(entry["text"] for entry in entries)

    except Exception as exc:
        logger.warning("Transcript listing failed for %s: %s", video_id, exc)

    raise ValueError(
        f"No transcript available for YouTube video {video_id}. "
        "The video may not have captions enabled."
    )


def get_instagram_transcript(url: str) -> str:
    """Attempt to extract a transcript/subtitles from an Instagram Reel.

    Uses yt-dlp to look for embedded or auto-generated subtitles.
    Falls back to a descriptive placeholder when no text track is found
    (full Whisper-based transcription is not included in the MVP).
    """
    fallback_msg = (
        "[No transcript available – Instagram Reel audio could not be "
        "transcribed without Whisper. The metadata is still available "
        "for analysis.]"
    )

    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_template = str(Path(tmp_dir) / "reel")

            # Attempt to download subtitles only (skip the video itself)
            cmd = [
                "yt-dlp",
                "--skip-download",
                "--write-subs",
                "--write-auto-subs",
                "--sub-lang", "en",
                "--sub-format", "vtt",
                "-o", out_template,
                url,
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
            )

            # Look for any subtitle file that was written
            sub_files = list(Path(tmp_dir).glob("*.vtt")) + list(
                Path(tmp_dir).glob("*.srt")
            )

            if sub_files:
                raw = sub_files[0].read_text(encoding="utf-8", errors="replace")
                # Crude VTT/SRT cleaning: strip timing lines and headers
                lines: list[str] = []
                for line in raw.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    if line.startswith("WEBVTT") or line.startswith("Kind:"):
                        continue
                    if re.match(r"^\d{2}:\d{2}", line):
                        continue
                    if re.match(r"^\d+$", line):
                        continue
                    # Remove VTT position tags like <c>, </c>, etc.
                    line = re.sub(r"<[^>]+>", "", line)
                    if line:
                        lines.append(line)

                if lines:
                    return " ".join(lines)

            logger.info(
                "yt-dlp did not find subtitles for %s (stderr: %s)",
                url,
                result.stderr[:300] if result.stderr else "none",
            )

    except FileNotFoundError:
        logger.warning("yt-dlp is not installed or not on PATH.")
    except subprocess.TimeoutExpired:
        logger.warning("yt-dlp subtitle download timed out for %s", url)
    except Exception as exc:
        logger.warning("Instagram transcript extraction failed: %s", exc)

    return fallback_msg
