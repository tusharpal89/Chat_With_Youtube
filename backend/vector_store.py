from typing import Tuple

import faiss
import numpy as np


def build_index(embeddings: np.ndarray) -> "faiss.IndexFlatIP":
    # Inner product on normalized vectors == cosine similarity.
    index = faiss.IndexFlatIP(embeddings.shape[1])
    index.add(embeddings)
    return index


def search(
    index: "faiss.IndexFlatIP", query_embedding: np.ndarray, top_k: int = 5
) -> Tuple[np.ndarray, np.ndarray]:
    scores, indices = index.search(query_embedding.reshape(1, -1), top_k)
    return scores[0], indices[0]
