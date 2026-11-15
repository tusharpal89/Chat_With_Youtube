import functools
from typing import List

import numpy as np
from sentence_transformers import SentenceTransformer

from backend.config import settings


@functools.lru_cache(maxsize=1)
def get_model() -> SentenceTransformer:
    return SentenceTransformer(settings.EMBEDDING_MODEL)


def embed_texts(texts: List[str]) -> np.ndarray:
    embeddings = get_model().encode(
        texts, batch_size=32, normalize_embeddings=True, show_progress_bar=False
    )
    return np.asarray(embeddings, dtype="float32")
