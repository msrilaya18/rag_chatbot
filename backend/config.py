import os
from pathlib import Path
from dotenv import load_dotenv

# Load from current directory (backend/) first, then fallback to project root (.env)
load_dotenv(override=True)
load_dotenv(Path(__file__).parent.parent / ".env", override=True)

class Settings:
    GOOGLE_API_KEY: str = os.getenv("GOOGLE_API_KEY", "")
    CHROMA_PERSIST_DIR: str = os.getenv("CHROMA_PERSIST_DIR", "./chroma_data")
    MODEL_NAME: str = "gemini-1.5-flash"
    EMBEDDING_MODEL: str = "models/gemini-embedding-001"
    CHUNK_SIZE: int = 500
    CHUNK_OVERLAP: int = 50

    def validate(self) -> None:
        if not self.GOOGLE_API_KEY:
            raise ValueError(
                "GOOGLE_API_KEY is not configured. Please set the GOOGLE_API_KEY "
                "environment variable in backend/.env or your environment."
            )

settings = Settings()
