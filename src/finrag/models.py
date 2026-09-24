from typing import Literal

from pydantic import BaseModel, Field


class Block(BaseModel):
    page: int
    section: str = ""
    kind: Literal["text", "table"] = "text"
    content: str


class Document(BaseModel):
    id: str
    filename: str
    company: str = ""
    year: int | None = None
    pages: int
    parser: str
    blocks: list[Block]
    warnings: list[str] = Field(default_factory=list)
    chunk_count: int = 0


class Chunk(Block):
    id: str
    document_id: str
    filename: str
    company: str = ""
    year: int | None = None


class Source(BaseModel):
    label: str
    chunk: Chunk
    score: float


class Question(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    document_id: str | None = None
    top_k: int = Field(default=5, ge=1, le=12)


class GrowthRequest(BaseModel):
    document_id: str
    metric: str = Field(min_length=1, max_length=120)
    from_year: int = Field(ge=1900, le=2100)
    to_year: int = Field(ge=1900, le=2100)


class Answer(BaseModel):
    answer: str
    mode: str
    sources: list[Source]
    warnings: list[str] = Field(default_factory=list)
