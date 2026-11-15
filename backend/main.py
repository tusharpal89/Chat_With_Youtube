import logging
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.routes import router

logger = logging.getLogger("uvicorn.error")

app = FastAPI(title="Chat With YouTube API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):517[0-9]",
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.exception_handler(Exception)
def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error while processing %s", request.url)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


# In production the React app is built to frontend/dist and served from this same
# origin (so the UI and API share one URL, no CORS needed). In local dev there is
# no dist folder, so expose a small JSON root and run Vite separately.
_DIST = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend", "dist")
if os.path.isdir(_DIST):
    app.mount("/", StaticFiles(directory=_DIST, html=True), name="frontend")
else:
    @app.get("/")
    def root():
        return {"name": "Chat With YouTube API", "docs": "/docs", "health": "/api/health"}
