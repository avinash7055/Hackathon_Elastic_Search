"""LangGraph state schema for PharmaVigil AI investigation workflow.

Defines the typed state that flows through the multi-agent graph:
Signal Scanner → Case Investigator → Safety Reporter
"""

from typing import TypedDict, Annotated
from operator import add


class ReasoningStep(TypedDict, total=False):
    """A single reasoning step from an agent — tool call, thought, or result."""
    agent: str          # signal_scanner | case_investigator | safety_reporter
    step_type: str      # thinking | tool_call | tool_result | conclusion
    content: str        # The reasoning text or tool description
    tool_name: str      # e.g. pharma.calculate_reporting_ratio
    tool_input: dict    # e.g. {"drug_name": "Cardizol-X", "reaction_term": "Arrhythmia"}
    tool_query: str     # The ES|QL query that was executed
    tool_result: str    # Summarized result from the tool
    timestamp: str      # ISO timestamp


class SignalRecord(TypedDict):
    """A detected drug safety signal."""
    drug_name: str
    reaction_term: str
    prr: float
    case_count: int
    spike_ratio: float
    priority: str  # HIGH, MEDIUM, LOW
    raw_response: str


class InvestigationRecord(TypedDict):
    """Investigation findings for a single signal."""
    drug_name: str
    reaction_term: str
    demographics_summary: str
    concomitant_drugs: list[str]
    interaction_detected: bool
    fatality_rate: float
    serious_rate: float
    geo_distribution: str
    overall_assessment: str
    raw_response: str


class SafetyReport(TypedDict):
    """Generated safety assessment report."""
    drug_name: str
    reaction_term: str
    risk_level: str  # CRITICAL, HIGH, MODERATE, LOW
    report_markdown: str
    evidence_summary: str
    recommended_actions: list[str]


class PharmaVigilState(TypedDict):
    """Root state for the LangGraph investigation workflow."""

    # Investigation metadata
    investigation_id: str
    status: str  # routing | scanning | investigating | reporting | complete | error
    started_at: str
    query: str  # Original user query / trigger

    # Master Node routing
    route: str            # full_scan | investigate | report | data_query | general
    extracted_drug: str   # Drug name extracted from query (if any)
    extracted_reaction: str  # Reaction term extracted (if any)
    direct_response: str  # For general/data_query — direct answer string

    # Agent outputs (append-only lists)
    signals: Annotated[list[dict], add]
    investigations: Annotated[list[dict], add]
    reports: Annotated[list[dict], add]

    # Conversation tracking
    scanner_conversation_id: str
    investigator_conversation_id: str
    reporter_conversation_id: str

    # Progress tracking
    current_agent: str
    progress_messages: Annotated[list[str], add]
    errors: Annotated[list[str], add]

    # Agent reasoning transparency (append-only)
    reasoning_trace: Annotated[list[dict], add]

    # Metadata
    total_signals_found: int
    total_investigations: int
    total_reports: int
