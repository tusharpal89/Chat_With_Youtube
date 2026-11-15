"""Provider-agnostic LLM client (uses the OpenAI SDK against any compatible API).

Switch providers purely via .env:
  - gemini  -> Google Gemini (free tier) through its OpenAI-compatible endpoint
  - openai  -> OpenAI
  - ollama  -> a local Ollama server
"""
import functools
import json
import re
import time
from typing import Dict, List

from openai import OpenAI

from backend.config import settings
from backend.utils import format_timestamp


class LLMError(Exception):
    pass


_PROVIDER_BASE_URLS = {
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/",
    "groq": "https://api.groq.com/openai/v1",
    "openai": None,
    "ollama": "http://localhost:11434/v1",
}


def _resolve_base_url():
    if settings.LLM_BASE_URL:
        return settings.LLM_BASE_URL
    return _PROVIDER_BASE_URLS.get(settings.LLM_PROVIDER)


def _is_real_key(key: str) -> bool:
    key = (key or "").strip()
    return bool(key) and not key.lower().startswith("your_")


def _resolve_api_key() -> str:
    provider = settings.LLM_PROVIDER
    if provider == "gemini":
        if not _is_real_key(settings.GEMINI_API_KEY):
            raise LLMError(
                "GEMINI_API_KEY is not set. Get a free key at "
                "https://aistudio.google.com/apikey and add it to your .env file."
            )
        return settings.GEMINI_API_KEY
    if provider == "groq":
        if not _is_real_key(settings.GROQ_API_KEY):
            raise LLMError(
                "GROQ_API_KEY is not set. Get a free key at "
                "https://console.groq.com/keys and add it to your .env file."
            )
        return settings.GROQ_API_KEY
    if provider == "openai":
        if not _is_real_key(settings.OPENAI_API_KEY):
            raise LLMError("OPENAI_API_KEY is not set in your .env file.")
        return settings.OPENAI_API_KEY
    if provider == "ollama":
        return "ollama"  # Ollama ignores the key
    raise LLMError(f"Unknown LLM_PROVIDER '{provider}'. Use gemini, openai or ollama.")


def is_key_configured() -> bool:
    try:
        _resolve_api_key()
        return True
    except LLMError:
        return False


@functools.lru_cache(maxsize=1)
def get_client() -> OpenAI:
    base_url = _resolve_base_url()
    api_key = _resolve_api_key()
    if base_url:
        return OpenAI(api_key=api_key, base_url=base_url, timeout=90.0)
    return OpenAI(api_key=api_key, timeout=90.0)


_TRANSIENT_HINTS = (
    "503", "502", "429", "unavailable", "resource_exhausted",
    "high demand", "overloaded", "rate limit", "try again",
)


def _is_transient(error: Exception) -> bool:
    msg = str(error).lower()
    return any(hint in msg for hint in _TRANSIENT_HINTS)


def _create(**kwargs):
    """Call the LLM with a small retry on transient (503/429/overload) errors."""
    last_error = None
    for attempt in range(3):
        try:
            return get_client().chat.completions.create(**kwargs)
        except Exception as e:
            last_error = e
            if _is_transient(e) and attempt < 2:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise
    raise last_error


def _chat(
    messages: List[Dict[str, str]],
    temperature: float = 0.3,
    json_mode: bool = False,
    max_tokens: int = 1024,
) -> str:
    base_kwargs = {
        "model": settings.LLM_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    try:
        if json_mode:
            try:
                resp = _create(**base_kwargs, response_format={"type": "json_object"})
            except Exception as e:
                if _is_transient(e):
                    raise
                # Some providers/models reject response_format; retry plainly.
                resp = _create(**base_kwargs)
        else:
            resp = _create(**base_kwargs)
    except Exception as e:
        raise LLMError(str(e)) from e

    content = resp.choices[0].message.content
    if not content:
        raise LLMError("The LLM returned an empty response.")
    return content


def _safe_json(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z]*\n?|\n?```$", "", raw).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
    raise LLMError("Failed to parse the LLM's JSON response.")


# --------------------------------------------------------------------------- #
# Features
# --------------------------------------------------------------------------- #
def generate_answer(question: str, chunks: List[Dict]) -> str:
    context = "\n\n".join(
        f"[{format_timestamp(c['start'])}] {c['text']}" for c in chunks
    )
    messages = [
        {
            "role": "system",
            "content": (
                "You are a helpful assistant that answers questions about a YouTube "
                "video/lecture using ONLY the provided transcript excerpts. Each excerpt "
                "is prefixed with its timestamp like [12:34]. Cite the timestamp(s) you "
                "used in your answer, e.g. (12:34). If the answer is not in the transcript, "
                "say so clearly. Do not use outside knowledge."
            ),
        },
        {"role": "user", "content": f"Transcript excerpts:\n{context}\n\nQuestion: {question}"},
    ]
    return _chat(messages, temperature=0.2, max_tokens=700)


def generate_summary(context: str) -> str:
    messages = [
        {
            "role": "system",
            "content": (
                "You summarize video lecture transcripts. Write a clear, well-structured "
                "summary covering the main topics and key takeaways. Use short paragraphs "
                "and bullet points where helpful."
            ),
        },
        {"role": "user", "content": f"Transcript:\n{context}"},
    ]
    return _chat(messages, temperature=0.3, max_tokens=900)


def generate_chapters(timeline_context: str) -> List[Dict]:
    messages = [
        {
            "role": "system",
            "content": (
                "You split a video lecture into chapters. The transcript lines are prefixed "
                "with their start time in seconds, like [125]. Identify the major sections "
                "and respond with STRICT JSON: "
                '{"chapters": [{"start": <integer seconds>, "title": "<short title>"}, ...]}. '
                "The first chapter should start at 0. Use 4-12 chapters. "
                "'start' must be an integer number of seconds copied from the markers."
            ),
        },
        {"role": "user", "content": f"Transcript:\n{timeline_context}"},
    ]
    raw = _chat(messages, temperature=0.2, json_mode=True, max_tokens=900)
    data = _safe_json(raw)
    chapters = []
    for item in data.get("chapters", []):
        try:
            chapters.append({"start": float(item["start"]), "title": str(item["title"]).strip()})
        except (KeyError, ValueError, TypeError):
            continue
    chapters.sort(key=lambda c: c["start"])
    return chapters


def generate_notes(context: str) -> str:
    messages = [
        {
            "role": "system",
            "content": (
                "You create clean, exam-ready study notes from a lecture transcript. "
                "Use Markdown: a short title, clear headings, bullet points, and a "
                "'Key terms' and 'Key takeaways' section. Be concise but complete."
            ),
        },
        {"role": "user", "content": f"Lecture transcript:\n{context}"},
    ]
    return _chat(messages, temperature=0.3, max_tokens=1400)


def generate_quiz(context: str, num_questions: int = 5) -> List[Dict]:
    messages = [
        {
            "role": "system",
            "content": (
                f"Create {num_questions} multiple-choice questions that test understanding "
                "of the lecture. Each question has exactly 4 options and one correct answer. "
                'Respond with STRICT JSON: {"quiz": [{"question": "...", "options": ["a","b","c","d"], '
                '"answer": <0-based index of the correct option>, "explanation": "..."}, ...]}.'
            ),
        },
        {"role": "user", "content": f"Lecture transcript:\n{context}"},
    ]
    raw = _chat(messages, temperature=0.4, json_mode=True, max_tokens=1600)
    data = _safe_json(raw)
    quiz = []
    for item in data.get("quiz", []):
        options = item.get("options") or []
        if not isinstance(options, list) or len(options) < 2:
            continue
        try:
            answer = int(item.get("answer", 0))
        except (ValueError, TypeError):
            answer = 0
        answer = max(0, min(answer, len(options) - 1))
        quiz.append(
            {
                "question": str(item.get("question", "")).strip(),
                "options": [str(o) for o in options],
                "answer": answer,
                "explanation": str(item.get("explanation", "")).strip(),
            }
        )
    return quiz


def generate_keywords(context: str, max_keywords: int = 15) -> List[str]:
    messages = [
        {
            "role": "system",
            "content": (
                f"Extract up to {max_keywords} of the most important keywords / key phrases "
                'from the lecture transcript. Respond with STRICT JSON: {"keywords": ["...", ...]}.'
            ),
        },
        {"role": "user", "content": f"Transcript:\n{context}"},
    ]
    raw = _chat(messages, temperature=0.2, json_mode=True, max_tokens=500)
    return [str(k) for k in _safe_json(raw).get("keywords", [])]


def generate_entities(context: str) -> List[Dict]:
    messages = [
        {
            "role": "system",
            "content": (
                "Extract named entities from the lecture transcript. Classify each into one of: "
                "PERSON, ORGANIZATION, LOCATION, DATE, CONCEPT, MISC. Respond with STRICT JSON: "
                '{"entities": [{"text": "...", "type": "..."}, ...]}. Avoid duplicates.'
            ),
        },
        {"role": "user", "content": f"Transcript:\n{context}"},
    ]
    raw = _chat(messages, temperature=0.1, json_mode=True, max_tokens=1200)
    entities = []
    seen = set()
    for item in _safe_json(raw).get("entities", []):
        text = str(item.get("text", "")).strip()
        etype = str(item.get("type", "MISC")).strip().upper()
        key = (text.lower(), etype)
        if text and key not in seen:
            seen.add(key)
            entities.append({"text": text, "type": etype})
    return entities
