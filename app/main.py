"""
app/main.py
Application entry point. Mounts the API router and configures the FastAPI app.
"""

from fastapi import FastAPI

from app.api import router
from app.config import settings

app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    description=(
        "Real-time sports media rights intelligence kernel. "
        "Detects, matches, and evaluates unauthorized distribution of official sports content."
    ),
)

app.include_router(router)
