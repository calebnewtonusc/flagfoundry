"""
api_server.py - FlagFoundry REST + WebSocket API server.

Endpoints:
  POST /v1/solve      — solve a CTF challenge end-to-end
  POST /v1/hint       — get a scaffolded hint
  POST /v1/classify   — classify challenge category
  WS   /v1/stream     — streaming exploit generation
  GET  /health        — health check

Run: uvicorn deploy.api_server:app --host 0.0.0.0 --port 8080
"""

import asyncio
import json
import os
import time
from typing import Optional

from fastapi import FastAPI, HTTPException, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="FlagFoundry API", version="1.0.0")

# FF-23 FIX: Replace wildcard CORS with env-configurable allowed origins.
# Default to localhost only; set ALLOWED_ORIGINS env var (comma-separated) for production.
_cors_origins_raw = os.environ.get("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:8080")
_cors_origins = [o.strip() for o in _cors_origins_raw.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)

MODEL_PATH = os.environ.get("MODEL_PATH", "checkpoints/flagfoundry-final")
_orchestrator = None


def _load_orchestrator_sync():
    """Load (or return cached) orchestrator — called from a thread executor."""
    global _orchestrator
    if _orchestrator is None:
        from agents.orchestrator_agent import OrchestratorAgent
        _orchestrator = OrchestratorAgent(model_path=MODEL_PATH)
    return _orchestrator


async def get_orchestrator():
    """Return the orchestrator, loading it in a thread pool to avoid blocking the event loop."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _load_orchestrator_sync)


class SolveRequest(BaseModel):
    description: str
    file: Optional[str] = None  # base64-encoded file
    filename: Optional[str] = None
    category: Optional[str] = None


class HintRequest(BaseModel):
    description: str
    attempted_approach: Optional[str] = None
    hint_level: int = 1  # 1=category, 2=technique, 3=implementation


class ClassifyRequest(BaseModel):
    description: str
    filename: Optional[str] = None


@app.get("/health")
async def health():
    return {"status": "ok", "model": MODEL_PATH, "timestamp": time.time()}


@app.post("/v1/classify")
async def classify(req: ClassifyRequest):
    """Classify a CTF challenge into a category."""
    from core.challenge_classifier import ChallengeClassifier
    classifier = ChallengeClassifier()
    result = classifier.classify(description=req.description, filename=req.filename)
    return {
        "category": result.category,
        "confidence": result.confidence,
        "vuln_class": result.vuln_class,
        "routing_notes": result.routing_notes,
    }


@app.post("/v1/solve")
async def solve(req: SolveRequest):
    """Solve a CTF challenge end-to-end."""
    import base64

    file_bytes = None
    if req.file:
        try:
            file_bytes = base64.b64decode(req.file)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid base64 file data")

    orchestrator = await get_orchestrator()
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: orchestrator.solve(
                description=req.description,
                file_bytes=file_bytes,
                filename=req.filename,
                category_override=req.category,
            ),
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/v1/hint")
async def hint(req: HintRequest):
    """Generate a scaffolded hint for a CTF challenge."""
    from core.challenge_classifier import ChallengeClassifier

    classifier = ChallengeClassifier()
    classification = classifier.classify(req.description)

    hint_levels = {
        1: f"This appears to be a {classification.category} challenge.",
        2: f"Look at the {classification.vuln_class or 'main mechanism'} vulnerability.",
        3: f"Try using {_get_tool_hint(classification.category, classification.vuln_class)}.",
    }

    hint_text = hint_levels.get(req.hint_level, hint_levels[1])
    return {"hint": hint_text, "category": classification.category, "level": req.hint_level}


@app.websocket("/v1/stream")
async def stream_solve(websocket: WebSocket):
    """Stream exploit generation in real-time."""
    await websocket.accept()

    try:
        data = await websocket.receive_json()
        description = data.get("description", "")
        category = data.get("category")

        await websocket.send_json({"type": "status", "message": "Classifying challenge..."})

        from core.challenge_classifier import ChallengeClassifier
        classifier = ChallengeClassifier()
        classification = classifier.classify(description)

        await websocket.send_json({
            "type": "classification",
            "category": classification.category,
            "confidence": classification.confidence,
        })

        await websocket.send_json({"type": "status", "message": "Generating exploit..."})

        orchestrator = await get_orchestrator()
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: orchestrator.solve(description=description, category_override=category),
        )

        for i, step in enumerate(result.get("reasoning", [])):
            await websocket.send_json({"type": "reasoning", "step": i + 1, "text": step})

        await websocket.send_json({"type": "exploit", "code": result.get("exploit", "")})
        await websocket.send_json({"type": "complete", "flag": result.get("flag")})

    except Exception as e:
        await websocket.send_json({"type": "error", "message": str(e)})
    finally:
        await websocket.close()


def _get_tool_hint(category: str, vuln_class: Optional[str]) -> str:
    """Get tool hint for a category/vuln class."""
    hints = {
        "web": "requests library, Burp Suite proxy, or sqlmap",
        "pwn": "pwntools (pwn.ELF, pwn.remote, pwn.ROP)",
        "crypto": "pycryptodome, z3-solver, or sympy",
        "forensics": "binwalk, Wireshark/tshark, or Volatility",
        "rev": "Ghidra, IDA, or radare2 for disassembly",
        "osint": "sherlock, whois, or reverse image search",
        "steg": "zsteg, steghide, or stegsolve",
    }
    return hints.get(category, "standard CTF tools")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="info")
