from dataclasses import dataclass, field
from typing import Dict, List

import numpy as np
from fastapi import HTTPException


@dataclass
class DocumentSession:
    doc_id: str
    video_id: str
    url: str
    title: str
    channel: str
    duration: int
    thumbnail: str
    source: str  # "captions" or "whisper"
    language: str
    segments: List[dict]  # [{start, end, text}, ...]
    chunks: List[dict]  # [{start, end, text}, ...]
    embeddings: np.ndarray
    index: object
    created_at: float = field(default=0.0)


# In-memory session store (keyed by doc_id). Cleared when the backend restarts.
DOCUMENT_STORE: Dict[str, DocumentSession] = {}

# Cache of processed transcripts keyed by YouTube video_id, so the same video
# is never downloaded / transcribed twice while the backend is running.
TRANSCRIPT_CACHE: Dict[str, dict] = {}


def save_document(session: DocumentSession) -> None:
    DOCUMENT_STORE[session.doc_id] = session


def get_document(doc_id: str) -> DocumentSession:
    session = DOCUMENT_STORE.get(doc_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail="Video session not found or expired. Please process the video again.",
        )
    return session
