from typing import Dict, List, Optional

import numpy as np

from backend.config import settings
from backend.embeddings import embed_texts
from backend.store import get_document
from backend.utils import format_timestamp
from backend.vector_store import search


def retrieve_top_k(doc_id: str, query: str, top_k: int = 5) -> List[Dict]:
    session = get_document(doc_id)
    query_embedding = embed_texts([query])[0]
    scores, indices = search(session.index, query_embedding, top_k)
    results = []
    for score, idx in zip(scores, indices):
        if idx == -1:
            continue
        chunk = session.chunks[idx]
        results.append(
            {
                "chunk_id": int(idx),
                "start": chunk["start"],
                "end": chunk["end"],
                "text": chunk["text"],
                "score": float(score),
            }
        )
    return results


def _sampled_chunks(chunks: List[dict], max_chars: int) -> List[dict]:
    joined_len = sum(len(c["text"]) for c in chunks)
    if joined_len <= max_chars or not chunks:
        return chunks
    avg_len = joined_len / len(chunks)
    target = max(1, int(max_chars / avg_len))
    positions = np.linspace(0, len(chunks) - 1, num=min(target, len(chunks)))
    indices = sorted(set(int(i) for i in positions))
    return [chunks[i] for i in indices]


def get_document_context(doc_id: str, max_chars: Optional[int] = None) -> str:
    """Plain text of the whole transcript (sampled if very long)."""
    if max_chars is None:
        max_chars = settings.MAX_CONTEXT_CHARS
    session = get_document(doc_id)
    chunks = _sampled_chunks(session.chunks, max_chars)
    return "\n\n".join(c["text"] for c in chunks)[:max_chars]


def get_timeline_context(doc_id: str, max_chars: Optional[int] = None) -> str:
    """Transcript with a [seconds] marker before each chunk, for chapters."""
    if max_chars is None:
        max_chars = settings.MAX_CONTEXT_CHARS
    session = get_document(doc_id)
    chunks = _sampled_chunks(session.chunks, max_chars)
    lines = [f"[{int(c['start'])}] {c['text']}" for c in chunks]
    return "\n\n".join(lines)[:max_chars]
