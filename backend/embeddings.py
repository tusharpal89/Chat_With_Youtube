import functools
import os
from typing import List

import numpy as np
from fastembed import TextEmbedding

from backend.config import settings


def _resolve_model_name(name: str) -> str:
    # fastembed expects the full repo id, e.g. "sentence-transformers/all-MiniLM-L6-v2"
    return name if "/" in name else f"sentence-transformers/{name}"


@functools.lru_cache(maxsize=1)
def get_model() -> TextEmbedding:
    # ONNX-based embeddings: same MiniLM model as sentence-transformers but far
    # lighter (no PyTorch), so it fits small free-tier instances.
    return TextEmbedding(
        model_name=_resolve_model_name(settings.EMBEDDING_MODEL),
        cache_dir=os.getenv("FASTEMBED_CACHE") or None,
    )


def embed_texts(texts: List[str]) -> np.ndarray:
    vectors = list(get_model().embed(list(texts)))
    arr = np.asarray(vectors, dtype="float32")
    if arr.ndim == 1:
        arr = arr.reshape(1, -1)
    # L2-normalise so FAISS inner-product search equals cosine similarity.
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return arr / norms
