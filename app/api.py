"""FastAPI backend for PharmaVigil AI.

Exposes REST endpoints for the React dashboard:
- POST /api/investigate — trigger a full multi-agent investigation
- GET  /api/signals     — list detected safety signals
- GET  /api/reports     — list generated reports
- GET  /api/reports/:id — get a specific report
- GET  /api/health      — system health
- WS   /ws/progress/:id — real-time investigation progress
"""

import logging
import json
import uuid
import asyncio
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.config import settings
from app.elastic_client import elastic_agent_client
from app.graph.graph import run_investigation, stream_investigation

logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ── In-memory store (lightweight for hackathon demo) ─────

investigations_store: dict = {}
active_websockets: dict[str, list[WebSocket]] = {}


# ── Pydantic Models ──────────────────────────────────────

class InvestigateRequest(BaseModel):
    query: Optional[str] = (
        "Scan for any emerging drug safety signals in the FAERS database "
        "from the last 90 days. Look for drugs with unusual spikes in adverse "
        "event reporting, particularly for serious reactions like cardiac events, "
        "hepatotoxicity, and rhabdomyolysis."
    )


class InvestigateResponse(BaseModel):
    investigation_id: str
    status: str
    message: str


class SignalResponse(BaseModel):
    drug_name: str
    reaction_term: str
    prr: float
    case_count: int
    spike_ratio: float
    priority: str


class ReportResponse(BaseModel):
    drug_name: str
    reaction_term: str
    risk_level: str
    report_markdown: str


class HealthResponse(BaseModel):
    status: str
    kibana: dict
    agents_registered: int
    tools_registered: int
    investigations_count: int


# ── App Lifecycle ────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=" * 60)
    logger.info("   PharmaVigil AI — Starting")
    logger.info("   Autonomous Drug Safety Signal Detection")
    logger.info("=" * 60)

    # Check Kibana connectivity
    health = await elastic_agent_client.health_check()
    logger.info(f"Kibana connection: {health.get('status')}")

    if health.get("status") == "connected":
        agents = await elastic_agent_client.list_agents()
        tools = await elastic_agent_client.list_tools()
        logger.info(f"Agents available: {len(agents)}")
        logger.info(f"Tools available: {len(tools)}")

    yield

    logger.info("Shutting down PharmaVigil AI...")
    await elastic_agent_client.close()


# ── FastAPI App ──────────────────────────────────────────

app = FastAPI(
    title="PharmaVigil AI",
    description=(
        "Autonomous drug safety signal detection system. "
        "Multi-agent pharmacovigilance powered by Elastic Agent Builder + LangGraph."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Endpoints ────────────────────────────────────────────

@app.get("/")
async def root():
    return {
        "name": "PharmaVigil AI",
        "version": "1.0.0",
        "description": "Autonomous Drug Safety Signal Detection",
        "docs": "/docs",
    }


@app.get("/api/health", response_model=HealthResponse)
async def health_check():
    """System health check."""
    kibana_health = await elastic_agent_client.health_check()
    agents = await elastic_agent_client.list_agents() if kibana_health.get("status") == "connected" else []
    tools = await elastic_agent_client.list_tools() if kibana_health.get("status") == "connected" else []

    return HealthResponse(
        status="healthy" if kibana_health.get("status") == "connected" else "degraded",
        kibana=kibana_health,
        agents_registered=len(agents),
        tools_registered=len(tools),
        investigations_count=len(investigations_store),
    )


@app.post("/api/investigate", response_model=InvestigateResponse)
async def start_investigation(request: InvestigateRequest):
    """Trigger a full multi-agent drug safety investigation."""
    investigation_id = f"INV-{uuid.uuid4().hex[:8].upper()}"

    # Store initial state
    investigations_store[investigation_id] = {
        "id": investigation_id,
        "status": "routing",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "query": request.query,
        "route": "",
        "direct_response": "",
        "signals": [],
        "investigations": [],
        "reports": [],
        "progress": [],
        "reasoning_trace": [],
    }

    # Run investigation in background
    asyncio.create_task(_run_investigation_background(investigation_id, request.query))

    return InvestigateResponse(
        investigation_id=investigation_id,
        status="routing",
        message="Investigation started. Master Orchestrator is analyzing your query. Connect to /ws/progress/{id} for real-time updates.",
    )


async def _run_investigation_background(investigation_id: str, query: str):
    """Background task to run the multi-agent investigation."""
    try:
        async for event in stream_investigation(query=query, investigation_id=investigation_id):
            # event is a dict with node_name -> state_update
            for node_name, state_update in event.items():
                logger.info(f"[{investigation_id}] Node '{node_name}' completed")

                # Update store
                inv = investigations_store.get(investigation_id, {})
                if "signals" in state_update:
                    inv.setdefault("signals", []).extend(state_update["signals"])
                if "investigations" in state_update:
                    inv.setdefault("investigations", []).extend(state_update["investigations"])
                if "reports" in state_update:
                    inv.setdefault("reports", []).extend(state_update["reports"])
                if "status" in state_update:
                    inv["status"] = state_update["status"]
                if "route" in state_update:
                    inv["route"] = state_update["route"]
                if "direct_response" in state_update and state_update["direct_response"]:
                    inv["direct_response"] = state_update["direct_response"]
                if "progress_messages" in state_update:
                    inv.setdefault("progress", []).extend(state_update["progress_messages"])

                # Capture reasoning traces
                reasoning_steps = state_update.get("reasoning_trace", [])
                if reasoning_steps:
                    inv.setdefault("reasoning_trace", []).extend(reasoning_steps)

                investigations_store[investigation_id] = inv

                # Broadcast progress to WebSocket clients
                await _broadcast_progress(investigation_id, {
                    "node": node_name,
                    "status": state_update.get("status", ""),
                    "route": state_update.get("route", ""),
                    "direct_response": state_update.get("direct_response", ""),
                    "progress": state_update.get("progress_messages", []),
                    "signals_count": len(inv.get("signals", [])),
                    "investigations_count": len(inv.get("investigations", [])),
                    "reports_count": len(inv.get("reports", [])),
                })

                # Broadcast reasoning trace events separately for real-time UI
                if reasoning_steps:
                    await _broadcast_progress(investigation_id, {
                        "type": "reasoning",
                        "node": node_name,
                        "steps": reasoning_steps,
                    })

    except Exception as e:
        logger.error(f"Investigation {investigation_id} failed: {e}")
        inv = investigations_store.get(investigation_id, {})
        inv["status"] = "error"
        inv.setdefault("progress", []).append(f"Error: {str(e)}")
        investigations_store[investigation_id] = inv

        await _broadcast_progress(investigation_id, {
            "node": "error",
            "status": "error",
            "error": str(e),
        })


@app.get("/api/investigations")
async def list_investigations():
    """List all investigations."""
    return [
        {
            "id": inv["id"],
            "status": inv["status"],
            "started_at": inv.get("started_at"),
            "signals_count": len(inv.get("signals", [])),
            "reports_count": len(inv.get("reports", [])),
        }
        for inv in investigations_store.values()
    ]


@app.get("/api/investigations/{investigation_id}")
async def get_investigation(investigation_id: str):
    """Get full investigation details."""
    inv = investigations_store.get(investigation_id)
    if not inv:
        raise HTTPException(status_code=404, detail="Investigation not found")
    return inv


@app.get("/api/signals")
async def list_signals():
    """List all detected safety signals across investigations."""
    all_signals = []
    for inv in investigations_store.values():
        for signal in inv.get("signals", []):
            signal_copy = {**signal}
            signal_copy["investigation_id"] = inv["id"]
            signal_copy.pop("raw_response", None)
            all_signals.append(signal_copy)
    return all_signals


@app.get("/api/reports")
async def list_reports():
    """List all generated safety reports."""
    all_reports = []
    for inv in investigations_store.values():
        for report in inv.get("reports", []):
            all_reports.append({
                "investigation_id": inv["id"],
                "drug_name": report.get("drug_name"),
                "reaction_term": report.get("reaction_term"),
                "risk_level": report.get("risk_level"),
                "has_report": bool(report.get("report_markdown")),
            })
    return all_reports


@app.get("/api/reports/{investigation_id}/{drug_name}")
async def get_report(investigation_id: str, drug_name: str):
    """Get a specific safety report."""
    inv = investigations_store.get(investigation_id)
    if not inv:
        raise HTTPException(status_code=404, detail="Investigation not found")

    for report in inv.get("reports", []):
        if report.get("drug_name", "").lower() == drug_name.lower():
            return report

    raise HTTPException(status_code=404, detail=f"No report found for {drug_name}")


# ── WebSocket for Real-time Progress ─────────────────────

@app.websocket("/ws/progress/{investigation_id}")
async def websocket_progress(websocket: WebSocket, investigation_id: str):
    """WebSocket endpoint for real-time investigation progress."""
    await websocket.accept()

    # Register client
    if investigation_id not in active_websockets:
        active_websockets[investigation_id] = []
    active_websockets[investigation_id].append(websocket)

    logger.info(f"WebSocket client connected for investigation {investigation_id}")

    # Send current state if investigation exists
    inv = investigations_store.get(investigation_id)
    if inv:
        await websocket.send_json({
            "type": "current_state",
            "data": {
                "status": inv["status"],
                "signals_count": len(inv.get("signals", [])),
                "investigations_count": len(inv.get("investigations", [])),
                "reports_count": len(inv.get("reports", [])),
                "progress": inv.get("progress", []),
                "reasoning_trace": inv.get("reasoning_trace", []),
            },
        })

    try:
        while True:
            # Keep connection alive, handle client messages
            data = await websocket.receive_text()
            # Echo or handle commands if needed
    except WebSocketDisconnect:
        active_websockets[investigation_id].remove(websocket)
        logger.info(f"WebSocket client disconnected for {investigation_id}")


async def _broadcast_progress(investigation_id: str, data: dict):
    """Broadcast progress update to all WebSocket clients for an investigation."""
    clients = active_websockets.get(investigation_id, [])
    disconnected = []

    for ws in clients:
        try:
            await ws.send_json({"type": "progress", "data": data})
        except Exception:
            disconnected.append(ws)

    for ws in disconnected:
        clients.remove(ws)
