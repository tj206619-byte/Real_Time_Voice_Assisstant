import os
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from backend.config import settings
from backend.database.db import init_db
from backend.database.models import Reminder, Task
from backend.tools.reminder_tool import get_all_reminders
from backend.tools.task_tool import get_all_tasks
from backend.websocket.voice_session import VoiceSession
from backend.agent.agent import VoicePilotAgent

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("voicepilot.main")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context for DB setup and teardown."""
    logger.info("Initializing VoicePilot Database...")
    await init_db()
    logger.info("VoicePilot Database initialized successfully.")
    yield
    logger.info("Shutting down VoicePilot application.")

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    lifespan=lifespan
)

# Enable CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API Endpoints
@app.get("/api/health")
async def health_check():
    return {
        "status": "online",
        "app": settings.APP_NAME,
        "version": settings.VERSION,
        "openai_configured": bool(settings.OPENAI_API_KEY and not settings.OPENAI_API_KEY.startswith("your_")),
        "deepgram_configured": bool(settings.DEEPGRAM_API_KEY and not settings.DEEPGRAM_API_KEY.startswith("your_")),
        "elevenlabs_configured": bool(settings.ELEVENLABS_API_KEY and not settings.ELEVENLABS_API_KEY.startswith("your_"))
    }

@app.get("/api/reminders")
async def get_reminders_endpoint():
    reminders = await get_all_reminders()
    return {"reminders": reminders}

@app.get("/api/tasks")
async def get_tasks_endpoint():
    tasks = await get_all_tasks()
    return {"tasks": tasks}

class TestTurnRequest(BaseModel):
    message: str

@app.post("/api/test/turn")
async def test_agent_turn(req: TestTurnRequest):
    """Test endpoint to process text turn without audio/websocket."""
    agent = VoicePilotAgent()
    tokens = []
    tools_called = []
    
    async def on_start(name, args):
        tools_called.append({"tool": name, "args": args})

    async for token in agent.process_turn(req.message, on_tool_start=on_start):
        tokens.append(token)
        
    return {
        "user_message": req.message,
        "tools_called": tools_called,
        "response_text": "".join(tokens)
    }

# WebSocket Voice Session Endpoint
@app.websocket("/ws/voice")
async def websocket_voice_endpoint(websocket: WebSocket):
    await websocket.accept()
    session = VoiceSession(websocket)
    logger.info("Client connected to /ws/voice")
    
    try:
        while True:
            message_text = await websocket.receive_text()
            await session.handle_client_message(message_text)
    except WebSocketDisconnect:
        logger.info("Client disconnected from /ws/voice")
    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
    finally:
        await session.close()

# Mount Frontend static files
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

    @app.get("/")
    async def serve_index():
        return FileResponse(FRONTEND_DIR / "index.html")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG
    )
