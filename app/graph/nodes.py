"""LangGraph node functions for the PharmaVigil investigation pipeline.

Each node communicates with an Agent Builder agent via the Converse API
and updates the shared state with results.
"""

import logging
import json
import re
from datetime import datetime, timezone

from app.elastic_client import elastic_agent_client
from app.graph.state import PharmaVigilState

logger = logging.getLogger(__name__)


def _extract_signals_from_response(response_text: str) -> list[dict]:
    """Parse Signal Scanner agent response into structured signal records.
    
    Looks for patterns like:
    FLAGGED SIGNAL: DrugName → ReactionTerm
    - PRR: X.X
    - Recent cases: N
    - Spike ratio: X.Xx
    - Priority: HIGH/MEDIUM/LOW
    """
    signals = []
    current_signal = None

    for line in response_text.split("\n"):
        line = line.strip()

        # Match signal header
        if "FLAGGED SIGNAL" in line.upper() or ("→" in line and ("signal" in line.lower() or ":" in line)):
            if current_signal and current_signal.get("drug_name"):
                signals.append(current_signal)

            # Parse "Drug → Reaction" pattern
            parts = line.split("→")
            if len(parts) >= 2:
                drug = parts[0].replace("**", "").replace("FLAGGED SIGNAL:", "").replace("FLAGGED SIGNAL", "").strip()
                drug = drug.lstrip("*#- ").strip()
                reaction = parts[1].replace("**", "").strip()
                current_signal = {
                    "drug_name": drug,
                    "reaction_term": reaction,
                    "prr": 0.0,
                    "case_count": 0,
                    "spike_ratio": 0.0,
                    "priority": "MEDIUM",
                    "raw_response": "",
                }

        # Parse PRR
        if current_signal and "prr" in line.lower():
            match = re.search(r"[\d.]+", line.split(":")[-1])
            if match:
                try:
                    current_signal["prr"] = float(match.group())
                except ValueError:
                    pass

        # Parse case count
        if current_signal and ("recent cases" in line.lower() or "case count" in line.lower() or "cases" in line.lower()):
            match = re.search(r"(\d+)", line.split(":")[-1])
            if match:
                current_signal["case_count"] = int(match.group(1))

        # Parse spike ratio
        if current_signal and "spike" in line.lower():
            match = re.search(r"([\d.]+)", line.split(":")[-1])
            if match:
                try:
                    current_signal["spike_ratio"] = float(match.group(1))
                except ValueError:
                    pass

        # Parse priority
        if current_signal and "priority" in line.lower():
            for level in ["HIGH", "MEDIUM", "LOW", "CRITICAL"]:
                if level in line.upper():
                    current_signal["priority"] = level
                    break

    # Append last signal
    if current_signal and current_signal.get("drug_name"):
        signals.append(current_signal)

    return signals


async def scan_signals_node(state: PharmaVigilState) -> dict:
    """Node 1: Call Signal Scanner agent to detect emerging safety signals."""
    logger.info("Node: scan_signals — Starting signal surveillance")

    query = state.get("query", "Scan for any emerging drug safety signals in FAERS data from the last 90 days")

    try:
        result = await elastic_agent_client.converse(
            agent_id="signal_scanner",
            message=query,
            conversation_id=state.get("scanner_conversation_id"),
        )

        response_text = result["response"]
        conversation_id = result["conversation_id"]

        # Parse structured signals from response
        signals = _extract_signals_from_response(response_text)

        logger.info(f"Signal Scanner found {len(signals)} potential signals")

        # Store raw response in each signal
        for s in signals:
            s["raw_response"] = response_text

        return {
            "status": "investigating" if signals else "complete",
            "signals": signals,
            "scanner_conversation_id": conversation_id,
            "current_agent": "case_investigator" if signals else "none",
            "total_signals_found": len(signals),
            "progress_messages": [
                f"Signal Scanner completed: {len(signals)} signal(s) detected"
            ],
        }

    except Exception as e:
        logger.error(f"Signal Scanner failed: {e}")
        return {
            "status": "error",
            "errors": [f"Signal Scanner error: {str(e)}"],
            "progress_messages": [f"Signal Scanner failed: {str(e)}"],
        }


async def investigate_cases_node(state: PharmaVigilState) -> dict:
    """Node 2: Call Case Investigator agent for each flagged signal."""
    logger.info("Node: investigate_cases — Investigating flagged signals")

    signals = state.get("signals", [])
    if not signals:
        return {
            "status": "complete",
            "progress_messages": ["No signals to investigate"],
        }

    investigations = []
    conversation_id = state.get("investigator_conversation_id")

    for i, signal in enumerate(signals):
        drug = signal.get("drug_name", "Unknown")
        reaction = signal.get("reaction_term", "Unknown")

        logger.info(f"Investigating signal {i+1}/{len(signals)}: {drug} → {reaction}")

        message = (
            f"Investigate this flagged drug safety signal:\n"
            f"Drug: {drug}\n"
            f"Reaction: {reaction}\n"
            f"PRR: {signal.get('prr', 'N/A')}\n"
            f"Recent cases (90d): {signal.get('case_count', 'N/A')}\n"
            f"Spike ratio: {signal.get('spike_ratio', 'N/A')}x\n\n"
            f"Please perform a full investigation covering demographics, "
            f"concomitant drugs, outcome severity, and geographic distribution."
        )

        try:
            result = await elastic_agent_client.converse(
                agent_id="case_investigator",
                message=message,
                conversation_id=conversation_id,
            )

            conversation_id = result["conversation_id"]

            investigation = {
                "drug_name": drug,
                "reaction_term": reaction,
                "raw_response": result["response"],
                "demographics_summary": "",
                "concomitant_drugs": [],
                "interaction_detected": False,
                "fatality_rate": 0.0,
                "serious_rate": 0.0,
                "geo_distribution": "",
                "overall_assessment": result["response"][-500:] if result["response"] else "",
            }

            # Check for drug interaction mentions
            resp_lower = result["response"].lower()
            if "interaction" in resp_lower and ("yes" in resp_lower or "detected" in resp_lower or "potential" in resp_lower):
                investigation["interaction_detected"] = True

            investigations.append(investigation)

        except Exception as e:
            logger.error(f"Investigation failed for {drug}: {e}")
            investigations.append({
                "drug_name": drug,
                "reaction_term": reaction,
                "raw_response": f"Error: {str(e)}",
                "overall_assessment": f"Investigation failed: {str(e)}",
            })

    return {
        "status": "reporting",
        "investigations": investigations,
        "investigator_conversation_id": conversation_id,
        "current_agent": "safety_reporter",
        "total_investigations": len(investigations),
        "progress_messages": [
            f"Case Investigator completed: {len(investigations)} signal(s) investigated"
        ],
    }


async def generate_reports_node(state: PharmaVigilState) -> dict:
    """Node 3: Call Safety Reporter agent to generate formal reports."""
    logger.info("Node: generate_reports — Generating safety assessment reports")

    investigations = state.get("investigations", [])
    signals = state.get("signals", [])

    if not investigations:
        return {
            "status": "complete",
            "progress_messages": ["No investigations to report on"],
        }

    reports = []
    conversation_id = state.get("reporter_conversation_id")

    for i, investigation in enumerate(investigations):
        drug = investigation.get("drug_name", "Unknown")
        reaction = investigation.get("reaction_term", "Unknown")

        logger.info(f"Generating report {i+1}/{len(investigations)}: {drug} → {reaction}")

        # Find matching signal data
        matching_signal = next(
            (s for s in signals if s.get("drug_name") == drug),
            {},
        )

        message = (
            f"Generate a Drug Safety Signal Assessment Report for:\n\n"
            f"Drug: {drug}\n"
            f"Reaction: {reaction}\n"
            f"PRR: {matching_signal.get('prr', 'N/A')}\n"
            f"Spike ratio: {matching_signal.get('spike_ratio', 'N/A')}x\n"
            f"Priority: {matching_signal.get('priority', 'N/A')}\n\n"
            f"Investigation findings:\n{investigation.get('raw_response', 'No findings available')}\n\n"
            f"Please compile the full data using pharma.compile_signal_summary for {drug} "
            f"and generate the complete structured safety report."
        )

        try:
            result = await elastic_agent_client.converse(
                agent_id="safety_reporter",
                message=message,
                conversation_id=conversation_id,
            )

            conversation_id = result["conversation_id"]

            # Determine risk level from response
            risk_level = "MODERATE"
            resp_upper = result["response"].upper()
            if "CRITICAL" in resp_upper:
                risk_level = "CRITICAL"
            elif "HIGH" in resp_upper and "RISK" in resp_upper:
                risk_level = "HIGH"
            elif "LOW" in resp_upper and "RISK" in resp_upper:
                risk_level = "LOW"

            report = {
                "drug_name": drug,
                "reaction_term": reaction,
                "risk_level": risk_level,
                "report_markdown": result["response"],
                "evidence_summary": "",
                "recommended_actions": [],
            }

            reports.append(report)

        except Exception as e:
            logger.error(f"Report generation failed for {drug}: {e}")
            reports.append({
                "drug_name": drug,
                "reaction_term": reaction,
                "risk_level": "UNKNOWN",
                "report_markdown": f"Report generation failed: {str(e)}",
            })

    return {
        "status": "complete",
        "reports": reports,
        "reporter_conversation_id": conversation_id,
        "current_agent": "none",
        "total_reports": len(reports),
        "progress_messages": [
            f"Safety Reporter completed: {len(reports)} report(s) generated"
        ],
    }


async def compile_results_node(state: PharmaVigilState) -> dict:
    """Final node: Compile all results into the investigation summary."""
    logger.info("Node: compile_results — Finalizing investigation")

    signals = state.get("signals", [])
    investigations = state.get("investigations", [])
    reports = state.get("reports", [])

    summary = (
        f"Investigation complete. "
        f"Signals detected: {len(signals)}, "
        f"Cases investigated: {len(investigations)}, "
        f"Reports generated: {len(reports)}."
    )

    # Log high-priority signals
    high_priority = [s for s in signals if s.get("priority") in ("HIGH", "CRITICAL")]
    if high_priority:
        summary += f" HIGH PRIORITY signals: {len(high_priority)}."

    logger.info(summary)

    return {
        "status": "complete",
        "current_agent": "none",
        "progress_messages": [summary],
    }
