"""Group transcript segments into overlapping chunks, keeping start/end times
so every chunk can be cited back to an exact moment in the video.
"""
from typing import Dict, List


def _make_chunk(window: List[dict]) -> Dict:
    return {
        "text": " ".join(s["text"] for s in window),
        "start": window[0]["start"],
        "end": window[-1]["end"],
    }


def build_chunks(
    segments: List[dict], chunk_size: int = 1000, overlap: int = 150
) -> List[Dict]:
    chunks: List[Dict] = []
    window: List[dict] = []
    current_len = 0

    for seg in segments:
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        item = {"start": float(seg["start"]), "end": float(seg["end"]), "text": text}

        if window and current_len + len(text) + 1 > chunk_size:
            chunks.append(_make_chunk(window))
            # carry a tail of segments forward so context isn't cut mid-thought
            tail: List[dict] = []
            tail_len = 0
            for s in reversed(window):
                if tail_len + len(s["text"]) > overlap:
                    break
                tail.insert(0, s)
                tail_len += len(s["text"]) + 1
            window = tail
            current_len = tail_len

        window.append(item)
        current_len += len(text) + 1

    if window:
        chunks.append(_make_chunk(window))

    return chunks
