from pydantic import BaseModel, model_validator
from typing import Optional, List


class VideoInput(BaseModel):
    # Preferred generic fields
    video_a_url: Optional[str] = None
    video_b_url: Optional[str] = None
    # Legacy aliases kept for backwards compat
    youtube_url: Optional[str] = None
    instagram_url: Optional[str] = None

    @model_validator(mode="after")
    def resolve_urls(self) -> "VideoInput":
        # Fill generic fields from legacy fields if not provided
        if not self.video_a_url and self.youtube_url:
            self.video_a_url = self.youtube_url
        if not self.video_b_url and self.instagram_url:
            self.video_b_url = self.instagram_url
        if not self.video_a_url or not self.video_b_url:
            raise ValueError("Both video URLs are required (video_a_url and video_b_url).")
        return self


class VideoMetadata(BaseModel):
    url: str
    platform: str
    title: str
    creator: str
    follower_count: Optional[int] = None
    views: int
    likes: int
    comments: int
    hashtags: List[str] = []
    upload_date: str
    duration: str
    engagement_rate: float
    thumbnail_url: Optional[str] = None


class AnalyzeResponse(BaseModel):
    session_id: str
    video_a: VideoMetadata
    video_b: VideoMetadata


class ChatRequest(BaseModel):
    session_id: str
    message: str


class Citation(BaseModel):
    video_id: str          # 'A' or 'B'
    chunk_text: str
    chunk_index: int


class ChatChunk(BaseModel):
    type: str              # 'token' | 'citation' | 'done' | 'error'
    content: str = ""
    citations: List[Citation] = []
