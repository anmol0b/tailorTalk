from datetime import datetime
from typing import Any, Dict

from fastapi import FastAPI

from app.routers import chat
from app.services import calendar_service, agent_service

app = FastAPI(
    title="TailorTalk API",
    description="AI-powered calendar booking assistant",
    version="1.0.0",
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(chat.router)


# ── Health ────────────────────────────────────────────────────────────────────
@app.get("/health")
async def health_check():
    info: Dict[str, Any] = {
        "status":             "healthy",
        "timestamp":          datetime.now().isoformat(),
        "calendar_available": calendar_service.is_available(),
        "agent_available":    agent_service.get_status()["agent_available"],
    }
    if calendar_service.is_available():
        try:
            info["calendar"] = calendar_service.get_calendar_info()
        except Exception:
            pass
    info["agent"] = agent_service.get_status()
    return info


@app.get("/")
async def root():
    return {"message": "TailorTalk API v1.0", "docs": "/docs"}