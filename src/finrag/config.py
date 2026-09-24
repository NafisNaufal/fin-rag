from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FINRAG_", env_file=".env", extra="ignore")
    data_dir: Path = Path("data")
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    answer_mode: Literal["excerpts", "ollama"] = "excerpts"
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:3b"
    parser: Literal["pymupdf", "layout", "docling"] = "pymupdf"
    ocr_language: str = "eng"
    max_upload_mb: int = Field(default=50, ge=1, le=500)
    max_pages: int = Field(default=500, ge=1, le=2000)
    chunk_words: int = Field(default=220, ge=40, le=1000)
    overlap_words: int = Field(default=30, ge=0, le=100)

    def prepare(self):
        for name in ("raw", "parsed", "index", "tmp"):
            (self.data_dir / name).mkdir(parents=True, exist_ok=True)
