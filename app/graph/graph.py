"""LangGraph StateGraph definition for PharmaVigil AI.

Defines the investigation workflow with intelligent routing via Master Node:
  START → Master Node → (route classification)
    → "full_scan"   → Scanner → Investigator → Reporter → Compile → END
    → "investigate"  → Investigator → Reporter → Compile → END
    → "report"       → Reporter → Compile → END
    → "data_query"   → Direct Query → Compile → END
    → "general"      → General Knowledge → Compile → END
"""

import logging
import uuid
from datetime import datetime, timezone

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from app.graph.state import PharmaVigilState
from app.graph.nodes import (
    master_node,
    scan_signals_node,
    investigate_cases_node,
    generate_reports_node,
    compile_results_node,
    direct_query_node,
    general_knowledge_node,
)

logger = logging.getLogger(__name__)


def route_after_master(state: PharmaVigilState) -> str:
    """Conditional edge: Master Node routes to the appropriate pipeline."""
    route = state.get("route", "full_scan")
    logger.info(f"Master routing decision: {route}")

    if route == "full_scan":
        return "scan_signals"
    elif route == "investigate":
        return "investigate_cases"
    elif route == "report":
        return "generate_reports"
    elif route == "data_query":
        return "direct_query"
    elif route == "general":
        return "general_knowledge"
    else:
        logger.warning(f"Unknown route '{route}', defaulting to full scan")
        return "scan_signals"


def should_investigate(state: PharmaVigilState) -> str:
    """Conditional edge: continue to investigation only if signals found."""
    signals = state.get("signals", [])
    if signals and len(signals) > 0:
        logger.info(f"Routing to investigation: {len(signals)} signal(s) found")
        return "investigate"
    else:
        logger.info("No signals found — ending investigation")
        return "complete"


def build_graph() -> StateGraph:
    """Build the PharmaVigil investigation StateGraph with Master Node routing."""

    graph = StateGraph(PharmaVigilState)

    # Add nodes
    graph.add_node("master", master_node)
    graph.add_node("scan_signals", scan_signals_node)
    graph.add_node("investigate_cases", investigate_cases_node)
    graph.add_node("generate_reports", generate_reports_node)
    graph.add_node("compile_results", compile_results_node)
    graph.add_node("direct_query", direct_query_node)
    graph.add_node("general_knowledge", general_knowledge_node)

    # ── Entry point: always start with Master Node ──
    graph.set_entry_point("master")

    # ── Master Node → conditional routing ──
    graph.add_conditional_edges(
        "master",
        route_after_master,
        {
            "scan_signals": "scan_signals",
            "investigate_cases": "investigate_cases",
            "generate_reports": "generate_reports",
            "direct_query": "direct_query",
            "general_knowledge": "general_knowledge",
        },
    )

    # ── Full Scan pipeline: Scanner → (conditional) → Investigator → Reporter ──
    graph.add_conditional_edges(
        "scan_signals",
        should_investigate,
        {
            "investigate": "investigate_cases",
            "complete": "compile_results",
        },
    )

    # ── Linear flow after investigation ──
    graph.add_edge("investigate_cases", "generate_reports")
    graph.add_edge("generate_reports", "compile_results")

    # ── Quick paths → compile directly ──
    graph.add_edge("direct_query", "compile_results")
    graph.add_edge("general_knowledge", "compile_results")

    # ── Terminal ──
    graph.add_edge("compile_results", END)

    return graph


async def create_runnable():
    """Create a compiled graph with in-memory checkpointing."""
    graph = build_graph()
    checkpointer = MemorySaver()
    return graph.compile(checkpointer=checkpointer)


async def run_investigation(
    query: str = "Scan for any emerging drug safety signals in the FAERS database from the last 90 days. Look for drugs with unusual spikes in adverse event reporting, particularly for serious reactions like cardiac events, hepatotoxicity, and rhabdomyolysis.",
    investigation_id: str = None,
) -> PharmaVigilState:
    """Run a full multi-agent investigation.
    
    Args:
        query: The investigation prompt / question
        investigation_id: Optional ID (generated if not provided)
        
    Returns:
        Final investigation state with all signals, investigations, and reports
    """
    if investigation_id is None:
        investigation_id = f"INV-{uuid.uuid4().hex[:8].upper()}"

    initial_state: PharmaVigilState = {
        "investigation_id": investigation_id,
        "status": "routing",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "query": query,
        "route": "",
        "extracted_drug": "",
        "extracted_reaction": "",
        "direct_response": "",
        "signals": [],
        "investigations": [],
        "reports": [],
        "scanner_conversation_id": "",
        "investigator_conversation_id": "",
        "reporter_conversation_id": "",
        "current_agent": "master_orchestrator",
        "progress_messages": [f"Investigation {investigation_id} started"],
        "errors": [],
        "reasoning_trace": [],
        "total_signals_found": 0,
        "total_investigations": 0,
        "total_reports": 0,
    }

    logger.info(f"Starting investigation {investigation_id}")

    runnable = await create_runnable()

    config = {"configurable": {"thread_id": investigation_id}}

    final_state = await runnable.ainvoke(initial_state, config=config)

    logger.info(
        f"Investigation {investigation_id} complete: "
        f"route={final_state.get('route', 'N/A')}, "
        f"{final_state.get('total_signals_found', 0)} signals, "
        f"{final_state.get('total_investigations', 0)} investigations, "
        f"{final_state.get('total_reports', 0)} reports"
    )

    return final_state


async def stream_investigation(
    query: str = "Scan for any emerging drug safety signals in the FAERS database from the last 90 days.",
    investigation_id: str = None,
):
    """Stream investigation progress for real-time UI updates.
    
    Yields state updates as each node completes.
    """
    if investigation_id is None:
        investigation_id = f"INV-{uuid.uuid4().hex[:8].upper()}"

    initial_state: PharmaVigilState = {
        "investigation_id": investigation_id,
        "status": "routing",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "query": query,
        "route": "",
        "extracted_drug": "",
        "extracted_reaction": "",
        "direct_response": "",
        "signals": [],
        "investigations": [],
        "reports": [],
        "scanner_conversation_id": "",
        "investigator_conversation_id": "",
        "reporter_conversation_id": "",
        "current_agent": "master_orchestrator",
        "progress_messages": [f"Investigation {investigation_id} started"],
        "errors": [],
        "reasoning_trace": [],
        "total_signals_found": 0,
        "total_investigations": 0,
        "total_reports": 0,
    }

    runnable = await create_runnable()
    config = {"configurable": {"thread_id": investigation_id}}

    async for event in runnable.astream(initial_state, config=config):
        yield event
