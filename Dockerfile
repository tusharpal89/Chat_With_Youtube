# ---------- Stage 1: build the React frontend ----------
FROM node:20-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build          # outputs /app/frontend/dist (production -> same-origin API)

# ---------- Stage 2: Python backend serving the built frontend ----------
FROM python:3.12-slim
WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Bake the embedding model into the image so the first request is fast and the
# container does not need to download it on every cold start.
ENV FASTEMBED_CACHE=/app/models
RUN python -c "import os; from fastembed import TextEmbedding; TextEmbedding('sentence-transformers/all-MiniLM-L6-v2', cache_dir=os.environ['FASTEMBED_CACHE'])"

COPY backend/ ./backend/
COPY --from=frontend /app/frontend/dist ./frontend/dist

# Listen on the platform's $PORT (Render / Koyeb / Railway set it); default 7860.
EXPOSE 7860
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-7860}"]
