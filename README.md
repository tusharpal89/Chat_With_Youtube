# ClipMind — Chat with YouTube / Lectures 🎥🧠

Paste a YouTube lecture URL and turn it into **answers, notes, quizzes and chapters**.
ClipMind transcribes the video, indexes it with a RAG pipeline, and lets you chat with
it — every answer links to the exact **timestamp** in the video.

**Pipeline:** YouTube URL → `yt-dlp` (metadata) → captions (`youtube-transcript-api`) *or*
`faster-whisper` → timestamp-aware chunking → Sentence-Transformers embeddings → FAISS
vector search → Gemini LLM → Summary / Chat / Chapters / Notes / Quiz / Keywords / Entities.

## ✨ Features

| Feature | What it does |
|---|---|
| 💬 **Chat with video** | Ask anything; answers cite clickable `[MM:SS]` timestamps |
| 📄 **Summary** | A clear, structured overview of the lecture |
| ⏱️ **Auto chapters** | AI splits the video into clickable sections |
| 📝 **Study notes** | Exam-ready Markdown notes |
| 🎓 **Quiz** | Auto-generated MCQs you can answer and score |
| 🔑 **Keywords** & 🏷️ **Entities** | Key concepts + named entities |
| 📜 **Searchable transcript** | Full transcript; click any line to jump in the video |

Click any timestamp anywhere in the app and the embedded player seeks to that moment.

## 🧱 Tech stack

- **Backend:** FastAPI + Uvicorn, Pydantic
- **Ingestion:** `yt-dlp`, `youtube-transcript-api`, `faster-whisper` (fallback)
- **RAG:** `sentence-transformers` (`all-MiniLM-L6-v2`) + FAISS (`faiss-cpu`)
- **LLM:** Google **Gemini** (free tier) via its OpenAI-compatible API — swappable to OpenAI or Ollama through `.env`
- **Frontend:** React + Vite, `react-youtube`, `lucide-react`

## ▶️ Quick start (Windows)

After the one-time setup below, just **double-click `start.bat`** in this folder.
It launches the backend and frontend in their own windows and opens the app in your
browser. Keep those two windows open while using ClipMind; close them to stop it.

> If the app shows **"Failed to fetch"**, it almost always means the **backend isn't
> running** — start it again with `start.bat` (or the manual commands below).

## 🚀 Setup

### 1. Backend

```bash
python -m venv venv
venv\Scripts\Activate.ps1        # Windows PowerShell
pip install -r requirements.txt
```

> `faster-whisper` is only needed for videos **without** captions. It also needs
> [FFmpeg](https://ffmpeg.org/download.html) on your PATH.

Create your `.env` from the example and add a **free** Gemini API key
(get one at https://aistudio.google.com/apikey):

```bash
copy .env.example .env
```

### 2. Frontend

```bash
cd frontend
npm install
copy .env.example .env
```

## ▶️ Run

Terminal 1 — backend (from the project root):

```bash
uvicorn backend.main:app --reload --port 8000
```

Terminal 2 — frontend:

```bash
cd frontend
npm run dev
```

Open http://localhost:5173, paste a YouTube URL, and start exploring.
API docs: http://localhost:8000/docs.

## 🔧 Configuration (`.env`)

| Key | Default | Notes |
|---|---|---|
| `LLM_PROVIDER` | `groq` | `groq` \| `gemini` \| `openai` \| `ollama` |
| `LLM_MODEL` | `openai/gpt-oss-120b` | Groq: `openai/gpt-oss-20b` (faster), `qwen/qwen3.8-27b`; or `gemini-3.8-flash`, `gpt-4o-mini` |
| `GROQ_API_KEY` | — | **fast + free** key from https://console.groq.com/keys |
| `GEMINI_API_KEY` | — | free key from Google AI Studio |
| `GROQ_WHISPER_MODEL` | `whisper-large-v3-turbo` | fast cloud transcription when a Groq key is set |
| `TRANSCRIPT_LANGUAGES` | `en,hi` | preferred caption languages |
| `ENABLE_WHISPER_FALLBACK` | `true` | transcribe audio when no captions |
| `WHISPER_MODEL` | `base` | `tiny`/`base`/`small`/`medium`/`large-v3` |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Sentence-Transformers model |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | `1000` / `150` | chunking |
| `DEFAULT_TOP_K` | `5` | chunks retrieved for Q&A |

**Switch to a fully-local, free setup:** install [Ollama](https://ollama.com), run
`ollama pull llama3`, then set `LLM_PROVIDER=ollama` and `LLM_MODEL=llama3` in `.env`.

## 📝 Notes & limitations

- Sessions are held **in memory**; restarting the backend clears processed videos.
- Transcription of a long video without captions can take a few minutes (runs on CPU).
- `youtube-transcript-api` may be rate-limited by YouTube on shared/cloud IPs.
- Very long videos are sampled down to `MAX_CONTEXT_CHARS` for whole-video features.
