"""Turn a YouTube URL into (metadata, transcript segments).

Strategy (fastest, most reliable first):
  1. Fetch video info with yt-dlp (one call: gives metadata + subtitle tracks).
  2. Download existing captions via yt-dlp's subtitle URLs (robust, free).
  3. Fall back to youtube-transcript-api if yt-dlp exposes no usable captions.
  4. Only if there are no captions at all, download the audio and transcribe
     it locally with faster-whisper.
"""
import functools
import os
import tempfile
from typing import List, Optional, Tuple

import requests

from backend.config import settings

_UA = {"User-Agent": "Mozilla/5.0"}


class IngestError(Exception):
    pass


def _extract_info(url: str) -> dict:
    try:
        import yt_dlp
    except ImportError as e:  # pragma: no cover
        raise IngestError("yt-dlp is not installed. Run: pip install yt-dlp") from e

    opts = {"quiet": True, "no_warnings": True, "skip_download": True, "noprogress": True}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False)
    except Exception as e:
        raise IngestError(f"Could not read this YouTube URL: {e}") from e


def _metadata_from_info(info: dict) -> dict:
    video_id = info.get("id")
    if not video_id:
        raise IngestError("Could not determine the video id from this URL.")
    return {
        "video_id": video_id,
        "title": info.get("title") or "Untitled video",
        "channel": info.get("uploader") or info.get("channel") or "Unknown channel",
        "duration": int(info.get("duration") or 0),
        "thumbnail": info.get("thumbnail") or "",
    }


# --------------------------------------------------------------------------- #
# Captions via yt-dlp subtitle tracks (primary)
# --------------------------------------------------------------------------- #
def _pick_lang(tracks: dict, languages: List[str]):
    """Return (lang_code, formats) for the best matching caption track."""
    if not tracks:
        return None
    for lang in languages:  # exact match
        if lang in tracks:
            return lang, tracks[lang]
    for lang in languages:  # prefix match (en matches en-US, en-GB, ...)
        for key in tracks:
            if key.split("-")[0].lower() == lang.lower():
                return key, tracks[key]
    return None


def _download_json3(url: str) -> Optional[List[dict]]:
    try:
        resp = requests.get(url, headers=_UA, timeout=20)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return None

    segments = []
    for event in data.get("events", []):
        segs = event.get("segs")
        if not segs:
            continue
        text = "".join(s.get("utf8", "") for s in segs).replace("\n", " ").strip()
        if not text or text == "[Music]":
            continue
        start = float(event.get("tStartMs", 0)) / 1000.0
        duration = float(event.get("dDurationMs", 0)) / 1000.0
        segments.append({"start": start, "end": start + duration, "text": text})
    return segments or None


def _captions_from_info(info: dict, languages: List[str]) -> Optional[Tuple[List[dict], str]]:
    wanted = list(languages) + ["en"]
    for tracks in (info.get("subtitles") or {}, info.get("automatic_captions") or {}):
        picked = _pick_lang(tracks, wanted)
        if not picked:
            continue
        lang, formats = picked
        fmt = next((f for f in formats if f.get("ext") == "json3"), None)
        if fmt is None:
            continue
        url = fmt.get("url")
        if not url:
            continue
        segments = _download_json3(url)
        if segments:
            return segments, lang
    return None


# --------------------------------------------------------------------------- #
# Captions via youtube-transcript-api (secondary fallback)
# --------------------------------------------------------------------------- #
def _captions_via_api(video_id: str, languages: List[str]) -> Optional[Tuple[List[dict], str]]:
    try:
        from youtube_transcript_api import (
            YouTubeTranscriptApi,
            NoTranscriptFound,
            TranscriptsDisabled,
        )
    except ImportError:
        return None

    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
    except (TranscriptsDisabled, NoTranscriptFound, Exception):
        return None

    transcript = None
    try:
        transcript = transcript_list.find_transcript(list(languages))
    except Exception:
        try:
            transcript = transcript_list.find_generated_transcript(list(languages))
        except Exception:
            for t in transcript_list:
                transcript = t
                break
    if transcript is None:
        return None

    try:
        raw = transcript.fetch()
    except Exception:
        return None

    segments = []
    for item in raw:
        text = (item.get("text") or "").replace("\n", " ").strip()
        if not text or text == "[Music]":
            continue
        start = float(item.get("start", 0.0))
        duration = float(item.get("duration", 0.0))
        segments.append({"start": start, "end": start + duration, "text": text})
    if not segments:
        return None
    return segments, getattr(transcript, "language_code", "en")


# --------------------------------------------------------------------------- #
# Whisper (final fallback)
# --------------------------------------------------------------------------- #
@functools.lru_cache(maxsize=1)
def _get_whisper_model():
    from faster_whisper import WhisperModel

    return WhisperModel(
        settings.WHISPER_MODEL,
        device=settings.WHISPER_DEVICE,
        compute_type=settings.WHISPER_COMPUTE_TYPE,
    )


def _download_audio(url: str, out_dir: str, fmt: str = "bestaudio/best") -> str:
    import yt_dlp

    out_template = os.path.join(out_dir, "audio.%(ext)s")
    opts = {
        "format": fmt,
        "outtmpl": out_template,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return ydl.prepare_filename(info)


def transcribe_with_whisper(url: str) -> Tuple[List[dict], str]:
    if not settings.ENABLE_WHISPER_FALLBACK:
        raise IngestError(
            "This video has no captions and Whisper fallback is disabled "
            "(set ENABLE_WHISPER_FALLBACK=true in .env)."
        )
    try:
        model = _get_whisper_model()
    except ImportError as e:
        raise IngestError(
            "This video has no captions and faster-whisper is not installed. "
            "Run: pip install faster-whisper"
        ) from e

    with tempfile.TemporaryDirectory() as tmp:
        try:
            audio_path = _download_audio(url, tmp)
        except Exception as e:
            raise IngestError(f"Could not download the audio: {e}") from e

        try:
            seg_iter, info = model.transcribe(audio_path, vad_filter=True)
            segments = [
                {"start": float(s.start), "end": float(s.end), "text": s.text.strip()}
                for s in seg_iter
                if s.text and s.text.strip()
            ]
        except Exception as e:
            raise IngestError(f"Transcription failed: {e}") from e

    if not segments:
        raise IngestError("Transcription produced no text.")
    return segments, getattr(info, "language", "en")


# --------------------------------------------------------------------------- #
# Groq Whisper (fast, free cloud transcription)
# --------------------------------------------------------------------------- #
_GROQ_AUDIO_EXTS = {
    ".flac", ".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".ogg", ".opus", ".wav", ".webm",
}


def _groq_available() -> bool:
    key = (settings.GROQ_API_KEY or "").strip()
    return bool(key) and not key.lower().startswith("your_")


def transcribe_with_groq(url: str) -> Tuple[List[dict], str]:
    from openai import OpenAI

    client = OpenAI(
        api_key=settings.GROQ_API_KEY,
        base_url="https://api.groq.com/openai/v1",
        timeout=120.0,
    )
    with tempfile.TemporaryDirectory() as tmp:
        try:
            # Prefer a small, Groq-accepted audio container (m4a/webm); never a
            # combined video stream (avoids 3gp etc. that Groq rejects).
            audio_path = _download_audio(
                url,
                tmp,
                fmt="worstaudio[ext=m4a]/worstaudio[ext=webm]/bestaudio[ext=m4a]"
                "/bestaudio[ext=webm]/worstaudio/bestaudio",
            )
        except Exception as e:
            raise IngestError(f"Could not download the audio: {e}") from e

        ext = os.path.splitext(audio_path)[1].lower()
        if ext not in _GROQ_AUDIO_EXTS:
            raise IngestError(
                f"Downloaded audio format '{ext}' is not supported by Groq."
            )

        size_mb = os.path.getsize(audio_path) / (1024 * 1024)
        if size_mb > 24:
            raise IngestError(
                f"Audio is ~{size_mb:.0f}MB, over Groq's free ~25MB limit. "
                "Try a shorter video, or one that has captions."
            )
        try:
            with open(audio_path, "rb") as f:
                result = client.audio.transcriptions.create(
                    model=settings.GROQ_WHISPER_MODEL,
                    file=f,
                    response_format="verbose_json",
                )
        except Exception as e:
            raise IngestError(f"Groq transcription failed: {e}") from e

    raw_segments = getattr(result, "segments", None)
    if raw_segments is None and isinstance(result, dict):
        raw_segments = result.get("segments")

    segments = []
    for s in raw_segments or []:
        get = (lambda k: s.get(k)) if isinstance(s, dict) else (lambda k: getattr(s, k, None))
        text = (get("text") or "").strip()
        if not text:
            continue
        segments.append(
            {"start": float(get("start") or 0.0), "end": float(get("end") or 0.0), "text": text}
        )
    if not segments:
        raise IngestError("Groq transcription returned no text.")

    language = getattr(result, "language", None)
    if language is None and isinstance(result, dict):
        language = result.get("language")
    return segments, language or "en"


def process_video(url: str) -> dict:
    """Return {meta..., segments, source, language}."""
    info = _extract_info(url)
    meta = _metadata_from_info(info)
    languages = list(settings.TRANSCRIPT_LANGUAGES)

    captions = _captions_from_info(info, languages)
    if captions is None:
        captions = _captions_via_api(meta["video_id"], languages)

    if captions is not None:
        segments, language = captions
        source = "captions"
    elif _groq_available():
        segments, language = transcribe_with_groq(url)
        source = "groq-whisper"
    else:
        segments, language = transcribe_with_whisper(url)
        source = "whisper"

    return {**meta, "segments": segments, "source": source, "language": language}
