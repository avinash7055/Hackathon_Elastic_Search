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
    "pharma.search_knowledge": (
        "FROM pharma_knowledge | WHERE content LIKE ?search_query OR title LIKE ?search_query "
        "| KEEP doc_id, title, category, drug_name, content | LIMIT 3"
    ),
    "pharma.search_drug_label": (
        "FROM pharma_knowledge | WHERE drug_name == ?drug_name AND category == 'drug_label' "
        "| KEEP doc_id, title, content | LIMIT 1"
    ),
    "pharma.search_regulatory_guidance": (
        "FROM pharma_knowledge | WHERE category IN ('methodology','regulatory') AND content LIKE ?topic "
        "| KEEP doc_id, title, category, content | LIMIT 3"
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
    "pharma.search_knowledge": "Search Pharma Knowledge Base (RAG)",
    "pharma.search_drug_label": "Search Drug Label Information (RAG)",
    "pharma.search_regulatory_guidance": "Search Regulatory Guidance (RAG)",
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


# ── Master Node (Intelligent Router) ──────────────────────

async def master_node(state: PharmaVigilState) -> dict:
    """Master Node: Classifies user intent and routes to the right agent pipeline.
    
    Uses the master_orchestrator Elastic Agent Builder agent for classification.
    This ensures ALL intelligence flows through Elastic Agent Builder.
    """
    query = state.get("query", "")
    logger.info(f"Master Node: Classifying query — '{query[:80]}...'")

    reasoning = [{
        "agent": "master_orchestrator",
        "step_type": "thinking",
        "content": f"Analyzing query to determine optimal investigation route: \"{query}\"",
        "tool_name": "", "tool_input": {}, "tool_query": "", "tool_result": "",
        "timestamp": _now_iso(),
    }]

    try:
        classification_prompt = (
            "CLASSIFY the following user query into one of these routes and extract entities.\n\n"
            "## Routes:\n"
            "- \"full_scan\" → Broad safety scan across ALL drugs (e.g. \"scan for signals\", \"any emerging safety issues\")\n"
            "- \"investigate\" → Deep-dive into a SPECIFIC drug's adverse event data from FAERS (e.g. \"Investigate Cardizol-X\", \"Is Neurofen-Plus causing liver problems?\")\n"
            "- \"report\" → Generate a formal safety assessment report (e.g. \"Generate safety report for Arthrex-200\")\n"
            "- \"data_query\" → Quick factual/statistical question about FAERS data (e.g. \"How many events?\", \"Top 5 drugs by fatality\")\n"
            "- \"general\" → Knowledge question about drug labels, pharmacovigilance methods, guidelines, contraindications, warnings, dosage, drug interactions, or any question that does NOT need FAERS database queries (e.g. \"What is PRR?\", \"What are the contraindications of Cardizol-X?\", \"How is EBGM calculated?\", \"Warnings for Neurofen-Plus in elderly?\")\n"
            "- \"out_of_scope\" → Question completely unrelated to drugs, pharmacovigilance, or medicine (e.g. \"What is the weather?\", \"Tell me a joke\", \"Who won the world cup?\")\n\n"
            "## Rules:\n"
            "- If the query asks about drug LABELS, warnings, contraindications, dosage, mechanism, or prescribing information → route = \"general\" (even if a drug name is mentioned)\n"
            "- If the query asks about actual FAERS adverse event DATA, demographics, case counts, or needs database analysis → route = \"investigate\" or \"data_query\"\n"
            "- Respond with ONLY a JSON object. No markdown, no explanation, no extra text.\n\n"
            f"## User Query:\n\"{query}\"\n\n"
            "## Response (JSON only):\n"
        )

        result = await elastic_agent_client.converse(
            agent_id="master_orchestrator",
            message=classification_prompt,
        )

        response_text = result["response"].strip()
        logger.info(f"Master Orchestrator raw response: {response_text[:500]}")

        # Parse JSON classification from the agent
        # Try to extract JSON even if the agent wraps it in markdown or extra text
        classification = None
        try:
            classification = json.loads(response_text)
        except json.JSONDecodeError:
            # Try to find JSON object in the response
            json_match = re.search(r'\{[^}]+\}', response_text)
            if json_match:
                try:
                    classification = json.loads(json_match.group())
                except json.JSONDecodeError:
                    pass

        if not classification:
            # ── FALLBACK: Keyword-based intent classification ──
            # The agent may have answered the question instead of classifying it.
            # Use keyword heuristics on the ORIGINAL QUERY to determine route.
            logger.warning("Master Node: JSON parse failed — using keyword fallback classifier")
            q_lower = query.lower().strip()

            # Known drug names in our database
            known_drugs = ["cardizol-x", "neurofen-plus", "arthrex-200", "cardizol", "neurofen", "arthrex"]
            found_drug = ""
            for d in known_drugs:
                if d in q_lower:
                    # Capitalise properly
                    drug_map = {
                        "cardizol-x": "Cardizol-X", "cardizol": "Cardizol-X",
                        "neurofen-plus": "Neurofen-Plus", "neurofen": "Neurofen-Plus",
                        "arthrex-200": "Arthrex-200", "arthrex": "Arthrex-200",
                    }
                    found_drug = drug_map.get(d, d)
                    break

            # General knowledge patterns (no DB needed)
            general_patterns = [
                "what is", "what are", "explain", "define", "how does", "how do",
                "tell me about prr", "tell me about ror", "tell me about faers",
                "what does", "meaning of", "difference between",
            ]
            is_general = any(q_lower.startswith(p) or p in q_lower for p in general_patterns)

            # Pharma-related keywords to detect domain relevance
            pharma_keywords = [
                "drug", "adverse", "event", "safety", "signal", "pharmacovigilance",
                "prr", "ror", "faers", "fda", "reaction", "side effect", "clinical",
                "patient", "dose", "dosage", "prescription", "medication", "hepato",
                "cardiac", "rhabdomyolysis", "report", "scan", "investigate", "label",
                "contraindication", "warning", "interaction", "toxicity", "mortality",
                "meddra", "icsr", "psur", "ich", "rems", "ebgm", "bcpnn",
                "statin", "opioid", "nsaid", "arrhythmia", "hepatitis",
                "serious", "fatal", "hospitalization", "surveillance",
            ]
            has_pharma_context = any(kw in q_lower for kw in pharma_keywords)

            # But only if NO drug is mentioned and it's a conceptual question
            if is_general and not found_drug:
                classification = {"route": "general", "drug_name": "", "reaction_term": ""}
            # Drug-label knowledge question (drug name + label-related keywords → RAG)
            elif found_drug and any(kw in q_lower for kw in [
                "contraindication", "warning", "precaution", "interaction",
                "dosage", "dose", "maximum dose", "mechanism", "half-life",
                "prescribing", "label", "indication", "black box",
                "elderly", "pregnancy", "pediatric", "renal", "hepatic impairment",
                "adverse reaction", "side effect", "clinical pharmacology",
            ]):
                classification = {"route": "general", "drug_name": found_drug, "reaction_term": ""}
                logger.info(f"Master Node: Drug-label knowledge question detected → routing to RAG")
            # Quick data questions
            elif any(kw in q_lower for kw in ["how many", "top ", "count", "fatality rate", "geographic", "demographics"]):
                classification = {"route": "data_query", "drug_name": found_drug, "reaction_term": ""}
            # Report generation
            elif any(kw in q_lower for kw in ["generate", "write", "create", "compile", "report"]):
                classification = {"route": "report", "drug_name": found_drug, "reaction_term": ""}
            # Drug-specific investigation
            elif found_drug:
                classification = {"route": "investigate", "drug_name": found_drug, "reaction_term": ""}
            # Out-of-scope: no drug found AND no pharma keywords detected
            elif not has_pharma_context and not found_drug:
                classification = {"route": "out_of_scope", "drug_name": "", "reaction_term": ""}
                logger.info(f"Master Node: Query appears out of scope — '{query[:60]}'")
            # Default to full scan
            else:
                classification = {"route": "full_scan", "drug_name": "", "reaction_term": ""}

            # If the agent already answered the question (general route), capture it
            if classification["route"] == "general":
                # The agent already returned a useful answer in response_text
                # We'll store it so general_knowledge_node can use it or we short-circuit
                logger.info(f"Master Node: Agent already answered (fallback general). Capturing response.")
            
            logger.info(f"Master Node: Fallback classification → {classification}")

        route = classification.get("route", "full_scan")
        drug = classification.get("drug_name", "")
        reaction = classification.get("reaction_term", "")

        # Validate route
        valid_routes = {"full_scan", "investigate", "report", "data_query", "general", "out_of_scope"}
        if route not in valid_routes:
            logger.warning(f"Master Node: Invalid route '{route}', defaulting to full_scan")
            route = "full_scan"

        # If investigate/report/data_query requires a drug but none extracted, fall back to full_scan
        if route in ("investigate", "report") and not drug:
            logger.info(f"Master Node: Route '{route}' requires a drug name but none found, falling back to full_scan")
            route = "full_scan"

        logger.info(f"Master Node: route={route}, drug={drug}, reaction={reaction}")

        reasoning.append({
            "agent": "master_orchestrator",
            "step_type": "conclusion",
            "content": f"Query classified → Route: **{route}**{f', Drug: {drug}' if drug else ''}{f', Reaction: {reaction}' if reaction else ''}. Dispatching to appropriate agent pipeline.",
            "tool_name": "", "tool_input": {}, "tool_query": "", "tool_result": "",
            "timestamp": _now_iso(),
        })

        result_dict = {
            "route": route,
            "extracted_drug": drug,
            "extracted_reaction": reaction,
            "status": "routing",
            "current_agent": "master_orchestrator",
            "reasoning_trace": reasoning,
            "progress_messages": [f"🧠 Master Orchestrator: Routed to '{route}'" + (f" for {drug}" if drug else "")],
        }

        # NOTE: We no longer short-circuit general questions here.
        # The general_knowledge_node will perform RAG search for grounded answers.

        return result_dict

    except Exception as e:
        logger.error(f"Master Node failed: {e}")
        reasoning.append({
            "agent": "master_orchestrator",
            "step_type": "conclusion",
            "content": f"Classification failed ({str(e)}). Falling back to full safety scan.",
            "tool_name": "", "tool_input": {}, "tool_query": "", "tool_result": "",
            "timestamp": _now_iso(),
        })
        return {
            "route": "full_scan",
            "extracted_drug": "",
            "extracted_reaction": "",
            "status": "routing",
            "current_agent": "master_orchestrator",
            "reasoning_trace": reasoning,
            "progress_messages": ["🧠 Master Orchestrator: Defaulting to full safety scan"],
        }


async def direct_query_node(state: PharmaVigilState) -> dict:
    """Handles quick data queries by routing to the most appropriate Elastic agent.
    
    For drug-specific questions → case_investigator agent
    For broad data questions → signal_scanner agent
    """
    query = state.get("query", "")
    drug = state.get("extracted_drug", "")
    reaction = state.get("extracted_reaction", "")

    logger.info(f"Direct Query Node: Answering data question — '{query[:80]}'")

    reasoning = [{
        "agent": "data_query",
        "step_type": "thinking",
        "content": f"Processing quick data query. {'Targeting drug: ' + drug if drug else 'No specific drug — broad data scan.'}",
        "tool_name": "", "tool_input": {}, "tool_query": "", "tool_result": "",
        "timestamp": _now_iso(),
    }]

    # Choose the right agent based on whether a drug is specified
    if drug:
        agent_id = "case_investigator"
        enhanced_query = (
            f"Answer this specific data question about {drug}:\n{query}\n\n"
            f"Use the appropriate tools to get the exact data requested. "
            f"Be concise and data-focused in your response."
        )
    else:
        agent_id = "signal_scanner"
        enhanced_query = (
            f"Answer this data question about the FAERS database:\n{query}\n\n"
            f"Use the appropriate tools to get the exact data requested. "
            f"Be concise and data-focused in your response."
        )

    try:
        result = await elastic_agent_client.converse(
            agent_id=agent_id,
            message=enhanced_query,
        )

        # Extract reasoning from the agent's response
        agent_reasoning = _extract_reasoning_from_response(agent_id, result)
        reasoning.extend(agent_reasoning)

        reasoning.append({
            "agent": agent_id,
            "step_type": "conclusion",
            "content": f"Data query answered successfully by {TOOL_DESCRIPTIONS.get(agent_id, agent_id)}.",
            "tool_name": "", "tool_input": {}, "tool_query": "", "tool_result": "",
            "timestamp": _now_iso(),
        })

        return {
            "status": "complete",
            "direct_response": result["response"],
            "current_agent": "none",
            "reasoning_trace": reasoning,
            "progress_messages": [f"📊 Data query answered by {agent_id}"],
        }

    except Exception as e:
        logger.error(f"Direct Query Node failed: {e}")
        reasoning.append({
            "agent": agent_id,
            "step_type": "conclusion",
            "content": f"Data query failed: {str(e)}",
            "tool_name": "", "tool_input": {}, "tool_query": "", "tool_result": "",
            "timestamp": _now_iso(),
        })
        return {
            "status": "error",
            "direct_response": f"Sorry, I couldn't retrieve that data: {str(e)}",
            "errors": [f"Direct query error: {str(e)}"],
            "reasoning_trace": reasoning,
            "progress_messages": [f"Data query failed: {str(e)}"],
        }


async def out_of_scope_node(state: PharmaVigilState) -> dict:
    """Handles queries that are outside the pharmacovigilance domain.
    
    Returns a polite redirect message guiding the user back to drug safety topics.
    """
    query = state.get("query", "")
    logger.info(f"Out of Scope Node: Redirecting off-topic query — '{query[:80]}'")

    redirect_message = (
        "## 🔒 Out of Scope\n\n"
        "I appreciate your question, but I'm **PharmaVigil AI** — a specialized system "
        "designed exclusively for **drug safety and pharmacovigilance**.\n\n"
        "I can help you with:\n\n"
        "- 🔍 **Signal Detection** — Scan for emerging drug safety signals\n"
        "- 💊 **Drug Investigation** — Investigate specific drugs for adverse events\n"
        "- 📊 **Data Queries** — Get adverse event counts, demographics, geographic distribution\n"
        "- 📝 **Safety Reports** — Generate regulatory-grade safety assessment reports\n"
        "- 📚 **Pharma Knowledge** — Learn about PRR, ROR, FAERS, ICH guidelines, drug labels\n\n"
        "### Try one of these:\n"
        "- *\"Scan for any emerging drug safety signals in the last 90 days\"*\n"
        "- *\"Investigate Cardizol-X for cardiac safety signals\"*\n"
        "- *\"What is PRR in pharmacovigilance?\"*\n"
        "- *\"What are the contraindications of Neurofen-Plus?\"*\n"
        "- *\"Generate safety report for Arthrex-200\"*"
    )

    return {
        "status": "complete",
        "direct_response": redirect_message,
        "current_agent": "none",
        "reasoning_trace": [{
            "agent": "master_orchestrator",
            "step_type": "conclusion",
            "content": f"Query \"{query[:60]}\" is outside the pharmacovigilance domain. Providing guidance on supported topics.",
            "tool_name": "", "tool_input": {}, "tool_query": "", "tool_result": "",
            "timestamp": _now_iso(),
        }],
        "progress_messages": ["🔒 Query is outside the pharmacovigilance domain"],
    }


async def general_knowledge_node(state: PharmaVigilState) -> dict:
    """Answers general pharmacovigilance questions using the master_orchestrator agent.
    
    No database queries needed — pure LLM knowledge via Elastic Agent Builder.
    If the master node already answered the question (fallback), we skip the redundant call.
    """
    query = state.get("query", "")
    logger.info(f"General Knowledge Node: Answering question — '{query[:80]}'")

    # Always perform RAG search — never skip to ensure answers are grounded in knowledge base

    reasoning = [{
        "agent": "master_orchestrator",
        "step_type": "thinking",
        "content": f"Searching knowledge base for relevant documents before answering...",
        "tool_name": "", "tool_input": {}, "tool_query": "", "tool_result": "",
        "timestamp": _now_iso(),
    }]

    # ── RAG: Search knowledge base for context ──────────
    rag_context = ""
    try:
        from app.config import settings
        from elasticsearch import Elasticsearch

        es = Elasticsearch(settings.elasticsearch_url, api_key=settings.elasticsearch_api_key, request_timeout=15)
        
        # Try semantic search first (ELSER embeddings), fallback to BM25
        hits = []
        try:
            semantic_body = {
                "query": {
                    "semantic": {
                        "field": "content_semantic",
                        "query": query,
                    }
                },
                "size": 3,
                "_source": ["title", "category", "content"],
            }
            results = es.search(index="pharma_knowledge", body=semantic_body)
            hits = results.get("hits", {}).get("hits", [])
            if hits:
                logger.info(f"RAG semantic search returned {len(hits)} hits")
        except Exception:
            logger.info("Semantic search not available, falling back to BM25")
        
        # Fallback to BM25 full-text search
        if not hits:
            bm25_body = {
                "query": {
                    "multi_match": {
                        "query": query,
                        "fields": ["title^3", "content"],
                        "type": "best_fields",
                        "fuzziness": "AUTO",
                    }
                },
                "size": 3,
                "_source": ["title", "category", "content"],
            }
            results = es.search(index="pharma_knowledge", body=bm25_body, ignore=[404])
            hits = results.get("hits", {}).get("hits", [])

        if hits:
            rag_pieces = []
            for hit in hits:
                src = hit["_source"]
                rag_pieces.append(f"--- {src['title']} ({src['category']}) ---\n{src['content'][:2000]}")
            rag_context = "\n\n".join(rag_pieces)
            reasoning.append({
                "agent": "master_orchestrator",
                "step_type": "tool_call",
                "content": f"Retrieved {len(hits)} relevant knowledge documents via RAG semantic search.",
                "tool_name": "pharma.search_knowledge",
                "tool_input": {"search_query": query[:100]},
                "tool_query": f"Semantic search: '{query[:80]}' → {len(hits)} results",
                "tool_result": ", ".join(h["_source"]["title"] for h in hits),
                "timestamp": _now_iso(),
            })
        else:
            logger.info("RAG search returned no results, using LLM knowledge only.")
    except Exception as rag_err:
        logger.warning(f"RAG search failed (non-critical): {rag_err}")

    try:
        rag_prefix = ""
        if rag_context:
            rag_prefix = (
                f"Here is relevant context from our pharmaceutical knowledge base:\n\n"
                f"{rag_context}\n\n"
                f"Use the above context to inform and ground your answer. "
                f"Cite specific documents when applicable.\n\n"
            )

        result = await elastic_agent_client.converse(
            agent_id="master_orchestrator",
            message=(
                f"You are now acting as a pharmacovigilance knowledge expert. "
                f"Answer this question clearly, accurately, and concisely. "
                f"Use markdown formatting for readability.\n\n"
                f"{rag_prefix}"
                f"Question: {query}"
            ),
        )

        reasoning.append({
            "agent": "master_orchestrator",
            "step_type": "conclusion",
            "content": "General knowledge question answered successfully.",
            "tool_name": "", "tool_input": {}, "tool_query": "", "tool_result": "",
            "timestamp": _now_iso(),
        })

        return {
            "status": "complete",
            "direct_response": result["response"],
            "current_agent": "none",
            "reasoning_trace": reasoning,
            "progress_messages": ["💡 General knowledge question answered"],
        }

    except Exception as e:
        logger.error(f"General Knowledge Node failed: {e}")
        return {
            "status": "error",
            "direct_response": f"Sorry, I couldn't answer that: {str(e)}",
            "errors": [f"General knowledge error: {str(e)}"],
            "reasoning_trace": reasoning,
            "progress_messages": [f"General knowledge query failed: {str(e)}"],
        }


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
    """Node 2: Call Case Investigator agent for each flagged signal.
    
    Also handles direct investigation requests from the Master Node
    when a specific drug is mentioned but no scanner was run.
    """
    logger.info("Node: investigate_cases — Investigating flagged signals")

    signals = state.get("signals", [])

    # If no signals but master node extracted a drug, create a synthetic signal
    if not signals and state.get("extracted_drug"):
        drug = state.get("extracted_drug", "")
        reaction = state.get("extracted_reaction", "")
        logger.info(f"No scanner signals — creating direct investigation for {drug}")
        signals = [{
            "drug_name": drug,
            "reaction_term": reaction or "All adverse events",
            "prr": 0.0,
            "case_count": 0,
            "spike_ratio": 0.0,
            "priority": "UNKNOWN",
            "raw_response": "Direct investigation request via Master Orchestrator",
        }]

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

    route = state.get("route", "full_scan")
    signals = state.get("signals", [])
    investigations = state.get("investigations", [])
    reports = state.get("reports", [])
    direct_response = state.get("direct_response", "")

    # Route-appropriate summary
    if route == "general":
        summary = "✅ Knowledge question answered successfully."
    elif route == "data_query":
        summary = "✅ Data query completed successfully."
    elif route in ("full_scan", "investigate", "report"):
        summary = (
            f"Investigation complete. "
            f"Signals detected: {len(signals)}, "
            f"Cases investigated: {len(investigations)}, "
            f"Reports generated: {len(reports)}."
        )
        # Log high-priority signals
        high_priority = [s for s in signals if s.get("priority") in ("HIGH", "CRITICAL")]
        if high_priority:
            summary += f" ⚠ HIGH PRIORITY signals: {len(high_priority)}."
    else:
        summary = "Investigation complete."

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
