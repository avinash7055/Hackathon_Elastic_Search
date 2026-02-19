"""LangGraph node functions for the PharmaVigil investigation pipeline.

Each node communicates with an Agent Builder agent via the Converse API
and updates the shared state with results — including agent reasoning traces
for the transparency panel.
"""

import logging
import json
import re
from datetime import datetime, timezone

from app.elastic_client import elastic_agent_client
from app.graph.state import PharmaVigilState

logger = logging.getLogger(__name__)

# ── Tool metadata lookup ──────────────────────────────────

TOOL_QUERIES = {
    "pharma.scan_adverse_event_trends": (
        "FROM faers_reports | WHERE report_date >= NOW() - ?time_range::INT * 1 DAY "
        "| STATS event_count = COUNT(*), serious_count = COUNT(CASE(serious == true, 1, null)), "
        "fatal_count = COUNT(CASE(reaction_outcome == \"Fatal\", 1, null)) BY drug_name "
        "| SORT event_count DESC | LIMIT 20"
    ),
    "pharma.calculate_reporting_ratio": (
        "FROM faers_reports | STATS drug_reaction = COUNT(CASE(drug_name == ?drug_name AND "
        "reaction_term == ?reaction_term, 1, null)), drug_total = COUNT(CASE(drug_name == ?drug_name, 1, null)), "
        "other_reaction = COUNT(CASE(drug_name != ?drug_name AND reaction_term == ?reaction_term, 1, null)), "
        "other_total = COUNT(CASE(drug_name != ?drug_name, 1, null)) "
        "| EVAL prr = (drug_reaction * 1.0 / drug_total) / (other_reaction * 1.0 / other_total) | KEEP prr, case_count"
    ),
    "pharma.detect_temporal_spike": (
        "FROM faers_reports | WHERE drug_name == ?drug_name "
        "| STATS recent_count, baseline_count | EVAL spike_ratio = recent_daily_rate / baseline_daily_rate"
    ),
    "pharma.analyze_patient_demographics": (
        "FROM faers_reports | WHERE drug_name == ?drug_name "
        "| STATS count = COUNT(*), avg_age = AVG(patient_age) BY patient_sex, patient_age_group"
    ),
    "pharma.find_concomitant_drugs": (
        "FROM faers_reports | WHERE drug_name == ?drug_name "
        "| STATS co_report_count = COUNT(*), serious_pct BY concomitant_drugs | SORT co_report_count DESC"
    ),
    "pharma.check_outcome_severity": (
        "FROM faers_reports | WHERE drug_name == ?drug_name "
        "| STATS total, fatal, hospitalized, life_threatening | EVAL fatality_rate, serious_rate"
    ),
    "pharma.geo_distribution": (
        "FROM faers_reports | WHERE drug_name == ?drug_name "
        "| STATS event_count, serious_count BY reporter_country | SORT event_count DESC"
    ),
    "pharma.compile_signal_summary": (
        "FROM faers_reports | WHERE drug_name == ?drug_name "
        "| STATS total_reports, serious_count, fatal_count, last_90d, avg_patient_age BY reaction_term"
    ),
}

TOOL_DESCRIPTIONS = {
    "pharma.scan_adverse_event_trends": "Scan Adverse Event Trends",
    "pharma.calculate_reporting_ratio": "Calculate Proportional Reporting Ratio (PRR)",
    "pharma.detect_temporal_spike": "Detect Temporal Spike",
    "pharma.analyze_patient_demographics": "Analyze Patient Demographics",
    "pharma.find_concomitant_drugs": "Find Concomitant Drugs",
    "pharma.check_outcome_severity": "Check Outcome Severity",
    "pharma.geo_distribution": "Geographic Distribution",
    "pharma.compile_signal_summary": "Compile Signal Summary",
}


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _extract_reasoning_from_response(agent_name: str, result: dict) -> list[dict]:
    """Extract structured reasoning steps from an Agent Builder Converse API response.
    
    Parses tool calls and the agent's text response to build a reasoning trace.
    """
    steps = []
    tool_calls = result.get("tool_calls", [])
    response_text = result.get("response", "")

    # Extract reasoning from the agent's textual thinking
    # Look for patterns that indicate the agent is reasoning
    thinking_patterns = [
        r"(?:I (?:will|need to|should|am going to|can see|notice|observe).*?[.!])",
        r"(?:Let me.*?[.!])",
        r"(?:Based on.*?[.!])",
        r"(?:The (?:data|results|analysis) (?:shows?|indicates?|suggests?|reveals?).*?[.!])",
        r"(?:This (?:indicates?|suggests?|shows?|means?).*?[.!])",
        r"(?:Looking at.*?[.!])",
    ]

    # Parse tool calls into reasoning steps  
    for tc in tool_calls:
        tool_id = tc.get("toolId", tc.get("tool_id", tc.get("name", "unknown_tool")))
        tool_input = tc.get("parameters", tc.get("input", tc.get("args", {})))
        tool_result_data = tc.get("result", tc.get("output", ""))

        # Emit tool_call step
        steps.append({
            "agent": agent_name,
            "step_type": "tool_call",
            "content": TOOL_DESCRIPTIONS.get(tool_id, tool_id),
            "tool_name": tool_id,
            "tool_input": tool_input if isinstance(tool_input, dict) else {},
            "tool_query": TOOL_QUERIES.get(tool_id, ""),
            "tool_result": "",
            "timestamp": _now_iso(),
        })

        # Emit tool_result step if we have one
        if tool_result_data:
            result_summary = str(tool_result_data)[:300]
            steps.append({
                "agent": agent_name,
                "step_type": "tool_result",
                "content": f"Results from {TOOL_DESCRIPTIONS.get(tool_id, tool_id)}",
                "tool_name": tool_id,
                "tool_input": {},
                "tool_query": "",
                "tool_result": result_summary,
                "timestamp": _now_iso(),
            })

    # Extract key thinking sentences from the response
    sentences = re.split(r'(?<=[.!?])\s+', response_text)
    thinking_sentences = []
    for sentence in sentences[:15]:  # Check first 15 sentences
        sentence = sentence.strip()
        if len(sentence) > 20 and any(re.search(p, sentence, re.IGNORECASE) for p in thinking_patterns):
            thinking_sentences.append(sentence)
            if len(thinking_sentences) >= 4:  # Cap at 4 thinking steps per agent call
                break

    # Interleave thinking steps before tool calls
    for i, thought in enumerate(thinking_sentences):
        steps.insert(min(i, len(steps)), {
            "agent": agent_name,
            "step_type": "thinking",
            "content": thought,
            "tool_name": "",
            "tool_input": {},
            "tool_query": "",
            "tool_result": "",
            "timestamp": _now_iso(),
        })

    return steps


def _extract_signals_from_response(response_text: str, raw_result: dict = None) -> list[dict]:
    """Parse Signal Scanner agent response into structured signal records.

    Looks for patterns like:
      FLAGGED SIGNAL: DrugName → ReactionTerm
      - PRR: X.X
      - Recent cases: N
      - Spike ratio: X.Xx
      - Priority: HIGH/MEDIUM/LOW

    Falls back to mining the raw API steps for tool call evidence.
    """
    signals = []
    current_signal = None

    for line in response_text.split("\n"):
        line = line.strip()

        # Match signal header: "FLAGGED SIGNAL: Cardizol-X → Cardiac Arrest"
        if "FLAGGED SIGNAL" in line.upper() or ("→" in line and ("signal" in line.lower() or "🔴" in line or "flag" in line.lower())):
            if current_signal and current_signal.get("drug_name"):
                signals.append(current_signal)

            parts = line.split("→")
            if len(parts) >= 2:
                drug = parts[0].replace("**", "").replace("🔴", "").replace("FLAGGED SIGNAL:", "").replace("FLAGGED SIGNAL", "").strip()
                drug = re.sub(r'^[*#\-:\s]+', '', drug).strip()
                reaction = parts[1].replace("**", "").strip().split("\n")[0].strip()
                # Clean trailing punctuation
                reaction = re.sub(r'[*#\-:]+$', '', reaction).strip()
                if drug:
                    current_signal = {
                        "drug_name": drug,
                        "reaction_term": reaction,
                        "prr": 0.0,
                        "case_count": 0,
                        "spike_ratio": 0.0,
                        "priority": "HIGH",
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
            # Handle "∞" PRR
            if "∞" in line or "infinite" in line.lower() or "exclusive" in line.lower():
                current_signal["prr"] = 999.0

        # Parse case count
        if current_signal and ("recent cases" in line.lower() or "case count" in line.lower() or "cases" in line.lower()):
            match = re.search(r"([\d,]+)", line.split(":")[-1])
            if match:
                current_signal["case_count"] = int(match.group(1).replace(",", ""))

        # Parse spike ratio
        if current_signal and "spike" in line.lower():
            match = re.search(r"[\d.]+", line.split(":")[-1])
            if match:
                try:
                    current_signal["spike_ratio"] = float(match.group())
                except ValueError:
                    pass

        # Parse priority
        if current_signal and "priority" in line.lower():
            for level in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
                if level in line.upper():
                    current_signal["priority"] = level
                    break

    # Append last signal
    if current_signal and current_signal.get("drug_name"):
        signals.append(current_signal)

    # ── Fallback: mine signals from raw API step data ──────────────────────
    # If text parsing found nothing but the raw result has tool call evidence,
    # reconstruct signals from the tool call parameters (drug_name + reaction).
    if not signals and raw_result:
        raw_steps = raw_result.get("raw", {}).get("steps", [])
        spike_drugs = {}       # drug_name → spike_ratio
        prr_signals = {}       # (drug, reaction) → prr

        for step in raw_steps:
            if step.get("type") != "tool_call":
                continue
            tool_id = step.get("tool_id", "")
            params = step.get("params", {})
            results_list = step.get("results", [])

            # Collect spike ratios from detect_temporal_spike
            if tool_id == "pharma.detect_temporal_spike":
                drug = params.get("drug_name", "")
                for res in results_list:
                    if res.get("type") == "esql_results":
                        vals = res.get("data", {}).get("values", [])
                        cols = [c["name"] for c in res.get("data", {}).get("columns", [])]
                        for row in vals:
                            row_dict = dict(zip(cols, row))
                            spike = row_dict.get("spike_ratio")
                            if spike and spike > 2.0:
                                spike_drugs[drug] = float(spike)

            # Collect PRR evidence from calculate_reporting_ratio
            if tool_id == "pharma.calculate_reporting_ratio":
                drug = params.get("drug_name", "")
                reaction = params.get("reaction_term", "")
                for res in results_list:
                    if res.get("type") == "esql_results":
                        vals = res.get("data", {}).get("values", [])
                        cols = [c["name"] for c in res.get("data", {}).get("columns", [])]
                        for row in vals:
                            row_dict = dict(zip(cols, row))
                            prr = row_dict.get("prr")
                            drug_total = row_dict.get("drug_total", 0)
                            if prr and prr > 2.0 and drug_total > 0:
                                prr_signals[(drug, reaction)] = float(prr)

        # Build signals from evidence
        for (drug, reaction), prr in prr_signals.items():
            signals.append({
                "drug_name": drug,
                "reaction_term": reaction,
                "prr": prr,
                "case_count": 0,
                "spike_ratio": spike_drugs.get(drug, 0.0),
                "priority": "HIGH" if prr > 5.0 else "MEDIUM",
                "raw_response": "",
            })

        # If we have spike drugs but no PRR matches, add spike-only signals
        if not signals:
            for drug, spike in spike_drugs.items():
                signals.append({
                    "drug_name": drug,
                    "reaction_term": "Adverse Event",
                    "prr": 0.0,
                    "case_count": 0,
                    "spike_ratio": spike,
                    "priority": "HIGH" if spike > 3.0 else "MEDIUM",
                    "raw_response": "",
                })

    return signals


async def scan_signals_node(state: PharmaVigilState) -> dict:
    """Node 1: Call Signal Scanner agent to detect emerging safety signals."""
    logger.info("Node: scan_signals — Starting signal surveillance")

    query = state.get("query", "Scan for any emerging drug safety signals in FAERS data from the last 90 days")

    reasoning = []
    reasoning.append({
        "agent": "signal_scanner",
        "step_type": "thinking",
        "content": f"Starting signal surveillance scan. Analyzing FAERS database for anomalies in adverse event reporting patterns.",
        "tool_name": "", "tool_input": {}, "tool_query": "", "tool_result": "",
        "timestamp": _now_iso(),
    })

    try:
        result = await elastic_agent_client.converse(
            agent_id="signal_scanner",
            message=query,
            conversation_id=state.get("scanner_conversation_id"),
        )

        response_text = result["response"]
        conversation_id = result["conversation_id"]

        # Extract reasoning trace from agent response
        agent_reasoning = _extract_reasoning_from_response("signal_scanner", result)
        reasoning.extend(agent_reasoning)

        # Parse structured signals from response — try text first, fallback to raw steps
        signals = _extract_signals_from_response(response_text, raw_result=result)

        logger.info(f"Signal Scanner found {len(signals)} potential signals")

        # Store raw response in each signal
        for s in signals:
            s["raw_response"] = response_text

        # Add conclusion step
        if signals:
            signal_summary = ", ".join(f"{s['drug_name']}→{s['reaction_term']} (PRR: {s['prr']})" for s in signals)
            reasoning.append({
                "agent": "signal_scanner",
                "step_type": "conclusion",
                "content": f"Signal scan complete. Detected {len(signals)} potential safety signal(s): {signal_summary}. Routing to Case Investigator for deep analysis.",
                "tool_name": "", "tool_input": {}, "tool_query": "", "tool_result": "",
                "timestamp": _now_iso(),
            })
        else:
            reasoning.append({
                "agent": "signal_scanner",
                "step_type": "conclusion",
                "content": "Signal scan complete. No statistically significant safety signals detected in the current time window.",
                "tool_name": "", "tool_input": {}, "tool_query": "", "tool_result": "",
                "timestamp": _now_iso(),
            })

        return {
            "status": "investigating" if signals else "complete",
            "signals": signals,
            "scanner_conversation_id": conversation_id,
            "current_agent": "case_investigator" if signals else "none",
            "total_signals_found": len(signals),
            "reasoning_trace": reasoning,
            "progress_messages": [
                f"Signal Scanner completed: {len(signals)} signal(s) detected"
            ],
        }

    except Exception as e:
        logger.error(f"Signal Scanner failed: {e}")
        reasoning.append({
            "agent": "signal_scanner",
            "step_type": "conclusion",
            "content": f"Signal Scanner encountered an error: {str(e)}",
            "tool_name": "", "tool_input": {}, "tool_query": "", "tool_result": "",
            "timestamp": _now_iso(),
        })
        return {
            "status": "error",
            "errors": [f"Signal Scanner error: {str(e)}"],
            "reasoning_trace": reasoning,
            "progress_messages": [f"Signal Scanner failed: {str(e)}"],
        }


async def investigate_cases_node(state: PharmaVigilState) -> dict:
    """Node 2: Call Case Investigator agent for each flagged signal."""
    logger.info("Node: investigate_cases — Investigating flagged signals")

    signals = state.get("signals", [])
    if not signals:
        return {
            "status": "complete",
            "reasoning_trace": [],
            "progress_messages": ["No signals to investigate"],
        }

    investigations = []
    conversation_id = state.get("investigator_conversation_id")
    reasoning = []

    reasoning.append({
        "agent": "case_investigator",
        "step_type": "thinking",
        "content": f"Beginning deep investigation of {len(signals)} flagged signal(s). Will analyze demographics, drug interactions, outcome severity, and geographic patterns for each.",
        "tool_name": "", "tool_input": {}, "tool_query": "", "tool_result": "",
        "timestamp": _now_iso(),
    })

    for i, signal in enumerate(signals):
        drug = signal.get("drug_name", "Unknown")
        reaction = signal.get("reaction_term", "Unknown")

        logger.info(f"Investigating signal {i+1}/{len(signals)}: {drug} → {reaction}")

        reasoning.append({
            "agent": "case_investigator",
            "step_type": "thinking",
            "content": f"Investigating signal {i+1}/{len(signals)}: {drug} → {reaction} (PRR: {signal.get('prr', 'N/A')}, Spike: {signal.get('spike_ratio', 'N/A')}x). Querying patient demographics, concomitant medications, and outcome severity.",
            "tool_name": "", "tool_input": {}, "tool_query": "", "tool_result": "",
            "timestamp": _now_iso(),
        })

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

            # Extract reasoning from the investigator's response
            agent_reasoning = _extract_reasoning_from_response("case_investigator", result)
            reasoning.extend(agent_reasoning)

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

            reasoning.append({
                "agent": "case_investigator",
                "step_type": "conclusion",
                "content": f"Investigation of {drug}→{reaction} complete. {'Drug interaction detected.' if investigation['interaction_detected'] else 'No significant drug interactions found.'} Full case analysis recorded.",
                "tool_name": "", "tool_input": {}, "tool_query": "", "tool_result": "",
                "timestamp": _now_iso(),
            })

        except Exception as e:
            logger.error(f"Investigation failed for {drug}: {e}")
            investigations.append({
                "drug_name": drug,
                "reaction_term": reaction,
                "raw_response": f"Error: {str(e)}",
                "overall_assessment": f"Investigation failed: {str(e)}",
            })
            reasoning.append({
                "agent": "case_investigator",
                "step_type": "conclusion",
                "content": f"Investigation of {drug} failed: {str(e)}",
                "tool_name": "", "tool_input": {}, "tool_query": "", "tool_result": "",
                "timestamp": _now_iso(),
            })

    return {
        "status": "reporting",
        "investigations": investigations,
        "investigator_conversation_id": conversation_id,
        "current_agent": "safety_reporter",
        "total_investigations": len(investigations),
        "reasoning_trace": reasoning,
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
            "reasoning_trace": [],
            "progress_messages": ["No investigations to report on"],
        }

    reports = []
    conversation_id = state.get("reporter_conversation_id")
    reasoning = []

    reasoning.append({
        "agent": "safety_reporter",
        "step_type": "thinking",
        "content": f"Generating Drug Safety Signal Assessment Reports for {len(investigations)} investigated signal(s). Compiling statistical evidence, clinical context, and regulatory recommendations.",
        "tool_name": "", "tool_input": {}, "tool_query": "", "tool_result": "",
        "timestamp": _now_iso(),
    })

    for i, investigation in enumerate(investigations):
        drug = investigation.get("drug_name", "Unknown")
        reaction = investigation.get("reaction_term", "Unknown")

        logger.info(f"Generating report {i+1}/{len(investigations)}: {drug} → {reaction}")

        # Find matching signal data
        matching_signal = next(
            (s for s in signals if s.get("drug_name") == drug),
            {},
        )

        reasoning.append({
            "agent": "safety_reporter",
            "step_type": "thinking",
            "content": f"Compiling safety report for {drug}→{reaction}. Using pharma.compile_signal_summary to gather comprehensive data profile before report generation.",
            "tool_name": "", "tool_input": {}, "tool_query": "", "tool_result": "",
            "timestamp": _now_iso(),
        })

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

            # Extract reasoning from the reporter's response
            agent_reasoning = _extract_reasoning_from_response("safety_reporter", result)
            reasoning.extend(agent_reasoning)

            # Determine risk level — prefer signal priority, confirm from agent response text
            signal_priority = matching_signal.get("priority", "MEDIUM").upper()
            risk_level = signal_priority  # HIGH, MEDIUM, LOW, CRITICAL from signal data

            # Allow agent response to upgrade risk level but not downgrade it
            resp_upper = result["response"].upper()
            if "CRITICAL" in resp_upper and risk_level not in ("CRITICAL",):
                risk_level = "CRITICAL"
            elif "HIGH RISK" in resp_upper and risk_level == "LOW":
                risk_level = "HIGH"
            elif "LOW RISK" in resp_upper and risk_level in ("MEDIUM",):
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

            reasoning.append({
                "agent": "safety_reporter",
                "step_type": "conclusion",
                "content": f"Safety report for {drug}→{reaction} generated. Risk level: {risk_level}. Report includes statistical evidence, clinical assessment, and recommended regulatory actions.",
                "tool_name": "", "tool_input": {}, "tool_query": "", "tool_result": "",
                "timestamp": _now_iso(),
            })

        except Exception as e:
            logger.error(f"Report generation failed for {drug}: {e}")
            reports.append({
                "drug_name": drug,
                "reaction_term": reaction,
                "risk_level": "UNKNOWN",
                "report_markdown": f"Report generation failed: {str(e)}",
            })
            reasoning.append({
                "agent": "safety_reporter",
                "step_type": "conclusion",
                "content": f"Report generation for {drug} failed: {str(e)}",
                "tool_name": "", "tool_input": {}, "tool_query": "", "tool_result": "",
                "timestamp": _now_iso(),
            })

    return {
        "status": "complete",
        "reports": reports,
        "reporter_conversation_id": conversation_id,
        "current_agent": "none",
        "total_reports": len(reports),
        "reasoning_trace": reasoning,
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
        "reasoning_trace": [{
            "agent": "system",
            "step_type": "conclusion",
            "content": summary,
            "tool_name": "", "tool_input": {}, "tool_query": "", "tool_result": "",
            "timestamp": _now_iso(),
        }],
        "progress_messages": [summary],
    }
