"""
app/main.py
Application entry point. Mounts the API router and configures the FastAPI app.
"""

# load_dotenv() MUST run before any other project imports so that
# os.getenv("GEMINI_API_KEY") is available from the moment the app boots.
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402

from app.api import router  # noqa: E402
from app.config import settings  # noqa: E402

app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    description=(
        "Real-time sports media rights intelligence kernel. "
        "Detects, matches, and evaluates unauthorized distribution of official sports content."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/")
def serve_frontend() -> FileResponse:
    """Serve the Aegis MediaGuard frontend dashboard."""
    return FileResponse("index.html")
