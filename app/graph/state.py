"""LangGraph state schema for PharmaVigil AI investigation workflow.

Defines the typed state that flows through the multi-agent graph:
Signal Scanner → Case Investigator → Safety Reporter
"""

from typing import TypedDict, Annotated
from operator import add


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
    status: str  # scanning | investigating | reporting | complete | error
    started_at: str
    query: str  # Original user query / trigger

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

    # Metadata
    total_signals_found: int
    total_investigations: int
    total_reports: int
