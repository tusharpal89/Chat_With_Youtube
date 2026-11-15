from typing import List

from pydantic import BaseModel, Field

from backend.config import settings


class ProcessRequest(BaseModel):
    url: str


class ProcessResponse(BaseModel):
    doc_id: str
    video_id: str
    title: str
    channel: str
    duration: int
    thumbnail: str
    source: str
    language: str
    num_segments: int
    num_chunks: int


class SourceChunk(BaseModel):
    chunk_id: int
    start: float
    end: float
    text: str
    score: float


class AskRequest(BaseModel):
    doc_id: str
    question: str
    top_k: int = Field(default=settings.DEFAULT_TOP_K, ge=1, le=50)


class AskResponse(BaseModel):
    answer: str
    sources: List[SourceChunk]


class DocRequest(BaseModel):
    doc_id: str


class SummaryResponse(BaseModel):
    summary: str


class Chapter(BaseModel):
    start: float
    title: str


class ChaptersResponse(BaseModel):
    chapters: List[Chapter]


class NotesResponse(BaseModel):
    notes: str


class QuizRequest(BaseModel):
    doc_id: str
    num_questions: int = Field(default=5, ge=1, le=20)


class QuizItem(BaseModel):
    question: str
    options: List[str]
    answer: int
    explanation: str = ""


class QuizResponse(BaseModel):
    quiz: List[QuizItem]


class KeywordsRequest(BaseModel):
    doc_id: str
    max_keywords: int = Field(default=15, ge=1, le=50)


class KeywordsResponse(BaseModel):
    keywords: List[str]


class EntityItem(BaseModel):
    text: str
    type: str


class EntitiesResponse(BaseModel):
    entities: List[EntityItem]


class TranscriptSegment(BaseModel):
    start: float
    end: float
    text: str


class TranscriptResponse(BaseModel):
    video_id: str
    title: str
    segments: List[TranscriptSegment]


class HealthResponse(BaseModel):
    status: str
    llm_provider: str
    llm_model: str
    llm_key_configured: bool
    whisper_fallback: bool
