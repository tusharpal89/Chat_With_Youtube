import time
import uuid

from fastapi import APIRouter, HTTPException

from backend.chunking import build_chunks
from backend.config import settings
from backend.embeddings import embed_texts
from backend.ingest import IngestError, process_video
from backend.llm_client import (
    LLMError,
    generate_answer,
    generate_chapters,
    generate_entities,
    generate_keywords,
    generate_notes,
    generate_quiz,
    generate_summary,
    is_key_configured,
)
from backend.retriever import (
    get_document_context,
    get_timeline_context,
    retrieve_top_k,
)
from backend.schemas import (
    AskRequest,
    AskResponse,
    ChaptersResponse,
    DocRequest,
    EntitiesResponse,
    HealthResponse,
    KeywordsRequest,
    KeywordsResponse,
    NotesResponse,
    ProcessRequest,
    ProcessResponse,
    QuizRequest,
    QuizResponse,
    SourceChunk,
    SummaryResponse,
    TranscriptResponse,
)
from backend.store import DocumentSession, get_document, save_document
from backend.vector_store import build_index

router = APIRouter(prefix="/api")


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        llm_provider=settings.LLM_PROVIDER,
        llm_model=settings.LLM_MODEL,
        llm_key_configured=is_key_configured(),
        whisper_fallback=settings.ENABLE_WHISPER_FALLBACK,
    )


@router.post("/process", response_model=ProcessResponse)
def process(request: ProcessRequest) -> ProcessResponse:
    url = request.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="A YouTube URL is required.")

    try:
        data = process_video(url)
    except IngestError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception as e:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"Failed to process video: {e}") from e

    segments = data["segments"]
    try:
        chunks = build_chunks(segments, settings.CHUNK_SIZE, settings.CHUNK_OVERLAP)
        if not chunks:
            raise ValueError("No usable text found in the transcript.")
        embeddings = embed_texts([c["text"] for c in chunks])
        index = build_index(embeddings)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to index transcript: {e}") from e

    doc_id = uuid.uuid4().hex
    session = DocumentSession(
        doc_id=doc_id,
        video_id=data["video_id"],
        url=url,
        title=data["title"],
        channel=data["channel"],
        duration=data["duration"],
        thumbnail=data["thumbnail"],
        source=data["source"],
        language=data["language"],
        segments=segments,
        chunks=chunks,
        embeddings=embeddings,
        index=index,
        created_at=time.time(),
    )
    save_document(session)

    return ProcessResponse(
        doc_id=doc_id,
        video_id=data["video_id"],
        title=data["title"],
        channel=data["channel"],
        duration=data["duration"],
        thumbnail=data["thumbnail"],
        source=data["source"],
        language=data["language"],
        num_segments=len(segments),
        num_chunks=len(chunks),
    )


@router.post("/ask", response_model=AskResponse)
def ask(request: AskRequest) -> AskResponse:
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question must not be empty.")
    get_document(request.doc_id)
    chunks = retrieve_top_k(request.doc_id, request.question, request.top_k)
    try:
        answer = generate_answer(request.question, chunks)
    except LLMError as e:
        raise HTTPException(status_code=502, detail=f"LLM error: {e}") from e
    sources = [SourceChunk(**c) for c in chunks]
    return AskResponse(answer=answer, sources=sources)


@router.post("/summary", response_model=SummaryResponse)
def summary(request: DocRequest) -> SummaryResponse:
    context = get_document_context(request.doc_id)
    try:
        return SummaryResponse(summary=generate_summary(context))
    except LLMError as e:
        raise HTTPException(status_code=502, detail=f"LLM error: {e}") from e


@router.post("/chapters", response_model=ChaptersResponse)
def chapters(request: DocRequest) -> ChaptersResponse:
    context = get_timeline_context(request.doc_id)
    try:
        return ChaptersResponse(chapters=generate_chapters(context))
    except LLMError as e:
        raise HTTPException(status_code=502, detail=f"LLM error: {e}") from e


@router.post("/notes", response_model=NotesResponse)
def notes(request: DocRequest) -> NotesResponse:
    context = get_document_context(request.doc_id)
    try:
        return NotesResponse(notes=generate_notes(context))
    except LLMError as e:
        raise HTTPException(status_code=502, detail=f"LLM error: {e}") from e


@router.post("/quiz", response_model=QuizResponse)
def quiz(request: QuizRequest) -> QuizResponse:
    context = get_document_context(request.doc_id)
    try:
        return QuizResponse(quiz=generate_quiz(context, request.num_questions))
    except LLMError as e:
        raise HTTPException(status_code=502, detail=f"LLM error: {e}") from e


@router.post("/keywords", response_model=KeywordsResponse)
def keywords(request: KeywordsRequest) -> KeywordsResponse:
    context = get_document_context(request.doc_id)
    try:
        return KeywordsResponse(keywords=generate_keywords(context, request.max_keywords))
    except LLMError as e:
        raise HTTPException(status_code=502, detail=f"LLM error: {e}") from e


@router.post("/entities", response_model=EntitiesResponse)
def entities(request: DocRequest) -> EntitiesResponse:
    context = get_document_context(request.doc_id)
    try:
        return EntitiesResponse(entities=generate_entities(context))
    except LLMError as e:
        raise HTTPException(status_code=502, detail=f"LLM error: {e}") from e


@router.get("/transcript/{doc_id}", response_model=TranscriptResponse)
def transcript(doc_id: str) -> TranscriptResponse:
    session = get_document(doc_id)
    return TranscriptResponse(
        video_id=session.video_id,
        title=session.title,
        segments=session.segments,
    )
