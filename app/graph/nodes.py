"""LangGraph node functions for the SignalShield investigation pipeline.

Routing strategy:
  - Queries needing NO tools (general knowledge, classification, greetings,
    out-of-scope) → answered directly by Groq LLM (fast, no Agent Builder overhead).
  - Queries needing FAERS database tools (full_scan, investigate, report,
    data_query) → routed to Elastic Agent Builder agents that have tool access.
"""

import asyncio
import logging
import json
import re
from datetime import datetime, timezone

from langchain_groq import ChatGroq
from langchain_core.messages import SystemMessage, HumanMessage

from app.elastic_client import elastic_agent_client
from app.graph.state import SignalShieldState

logger = logging.getLogger(__name__)


# ── Direct LLM helper (no tools, no Agent Builder) ────────────────────────────

def _get_groq_llm():
    """Return a configured ChatGroq instance (tool-free direct LLM calls)."""
    from app.config import settings
    return ChatGroq(
        model=settings.groq_model,
        api_key=settings.groq_api_key,
        temperature=0.3,
        max_tokens=4096,
    )


async def _call_llm_direct(system_prompt: str, user_message: str) -> str:
    """Call Groq LLM directly without any tool involvement.

    Use this for: classification, general knowledge, greetings, out-of-scope.
    Do NOT use for queries requiring FAERS database access — route those to
    Elastic Agent Builder instead.

    Returns the response text string.
    """
    llm = _get_groq_llm()
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_message),
    ]
    response = await llm.ainvoke(messages)
    return response.content.strip()

# ── Tool metadata lookup ──────────────────────────────────

TOOL_FRIENDLY_MESSAGES = {
    "pharma.scan_adverse_event_trends": "Scanning for drugs with the most reported side effects recently...",
    "pharma.calculate_reporting_ratio": "Calculating how often this drug causes this side effect compared to other drugs...",
    "pharma.detect_temporal_spike": "Checking if side effect reports have spiked recently...",
    "pharma.analyze_patient_demographics": "Looking at which patients are most affected (age, gender)...",
    "pharma.find_concomitant_drugs": "Checking which other drugs patients were taking alongside this one...",
    "pharma.check_outcome_severity": "Reviewing how serious the reported outcomes were...",
    "pharma.geo_distribution": "Checking where in the world these reports are coming from...",
    "pharma.compile_signal_summary": "Pulling together all the key data for this drug...",
    "pharma.search_knowledge": "Searching our pharma knowledge base...",
    "pharma.search_drug_label": "Looking up the official drug label information...",
    "pharma.search_regulatory_guidance": "Checking regulatory guidelines...",
}


# ── Embedded Safety Signals context (demo dataset knowledge) ──────────────────
# This context is injected into AI prompts so the LLM can give informed responses
# about the 3 drugs with known safety signals in our synthetic FAERS dataset.

DEMO_DRUG_SIGNALS_CONTEXT = """
## SignalShield Demo Dataset — Known Embedded Safety Signals

Our FAERS (FDA Adverse Event Reporting System) database contains synthetic data
for 20 drugs. Three of these drugs have intentionally embedded safety signals
that you should be aware of:

### 1. Cardizol-X (cardizolam) — Cardiac Arrhythmia Spike
- **Signal**: Dramatic increase in cardiac events (4× baseline) in the last 90 days
- **Reactions**: Cardiac arrhythmia, Ventricular tachycardia, QT prolongation,
  Atrial fibrillation, Cardiac arrest, Tachycardia
- **Indication**: Hypertension
- **Pattern**: Low baseline cardiac event rate for the first 21 months, then a
  sharp 4× spike in the most recent 90 days
- **Seriousness**: All cardiac events marked as serious (life-threatening,
  hospitalization, or death)
- **Patient profile**: Ages 45–85, both sexes, reported by healthcare professionals

### 2. Neurofen-Plus (ibuprofen-codeine) — Hepatotoxicity in Elderly Females
- **Signal**: Rising trend of liver injury reports, especially in females aged 65+
- **Reactions**: Hepatotoxicity, Liver injury, Hepatic failure, Jaundice,
  Hepatitis, Transaminases increased
- **Indication**: Pain Management
- **Pattern**: Gradual increase over the last 6 months (Gaussian distribution
  weighted toward recent dates)
- **Demographics**: ~78% female, ages 60–88, mostly classified as "Elderly"
- **Seriousness**: All events marked as serious (hospitalization or life-threatening)

### 3. Arthrex-200 (celecoxib-200) — Rhabdomyolysis with Statin Co-prescription
- **Signal**: Rhabdomyolysis cases specifically when co-prescribed with statins
- **Reactions**: Rhabdomyolysis, Myopathy, Creatine kinase increased
- **Indication**: Osteoarthritis
- **Co-prescribed statins**: Lipitorex (atorvastatin) or Simvalex (simvastatin)
  — ALWAYS present as concomitant medication in signal cases
- **Pattern**: Consistent over the past year, suggesting a drug-drug interaction
- **Patient profile**: Ages 50–80, both sexes
- **Seriousness**: All events marked as serious (hospitalization or life-threatening)

### Other Drugs in the Database (no embedded signals)
Lipitorex, Metforin-XR, Amlodex, Omeprazol-20, Sertralex, Levothyra,
Gabapentex, Lisinox, Simvalex, Warfatrex, Prednizol, Tramadex, Clopidex,
Azithrex, Fluoxetex, Ramiprilex, Diclofex

When answering questions about these drugs, use this knowledge to provide
accurate, specific, and data-informed responses. Reference specific signal
patterns, demographics, and co-prescribing risks as appropriate.
"""


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _extract_reasoning_from_response(agent_name: str, result: dict) -> list[dict]:
    """Extract structured reasoning steps from an Agent Builder Converse API response.
    
    Parses tool calls and the agent's text response to build a reasoning trace.
    Shows only user-friendly messages — no raw queries or technical details.
    """
    steps = []
    tool_calls = result.get("tool_calls", [])

    # Parse tool calls into friendly reasoning steps (no raw queries)
    for tc in tool_calls:
        tool_id = tc.get("toolId", tc.get("tool_id", tc.get("name", "unknown_tool")))

        # Show a user-friendly message for this tool call
        friendly_msg = TOOL_FRIENDLY_MESSAGES.get(tool_id, "Running analysis...")
        steps.append({
            "agent": agent_name,
            "step_type": "tool_call",
            "content": friendly_msg,
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

async def master_node(state: SignalShieldState) -> dict:
    """Master Node: Classifies user intent and routes to the right agent pipeline.
    
    Uses the master_orchestrator Elastic Agent Builder agent for classification.
    This ensures ALL intelligence flows through Elastic Agent Builder.
    """
    query = state.get("query", "")
    logger.info(f"Master Node: Classifying query — '{query[:80]}...'")

    reasoning = [{
        "agent": "master_orchestrator",
        "step_type": "thinking",
        "content": "Understanding your question...",
        "tool_name": "", "tool_input": {}, "tool_query": "", "tool_result": "",
        "timestamp": _now_iso(),
    }]

    try:
        # ── Classification via direct Groq call (no tools needed, faster) ──
        # The LLM decides EVERYTHING: greetings, out-of-scope, general, tools, etc.
        classification_system = (
            "You are a query classifier for SignalShield AI, a pharmacovigilance system. "
            "Classify the user query into exactly one route and extract any drug/reaction entities. "
            "Respond with ONLY a valid JSON object — no markdown fences, no explanation.\n\n"
            "Our database has these key drugs with known safety signals:\n"
            "  - Cardizol-X (cardiac arrhythmia spike in last 90 days)\n"
            "  - Neurofen-Plus (hepatotoxicity in elderly females, rising trend)\n"
            "  - Arthrex-200 (rhabdomyolysis when co-prescribed with statins)\n"
            "Other drugs: Lipitorex, Metforin-XR, Amlodex, Omeprazol-20, Sertralex, "
            "Levothyra, Gabapentex, Lisinox, Simvalex, Warfatrex, Prednizol, Tramadex, "
            "Clopidex, Azithrex, Fluoxetex, Ramiprilex, Diclofex\n\n"
            "Routes:\n"
            "  greeting    — Casual greetings or conversational openers "
                            "(e.g. 'hi', 'hello', 'how are you?', 'what can you do?', 'who are you?')\n"
            "  full_scan   — Broad scan across ALL drugs for safety signals "
                            "(e.g. 'scan for signals', 'any emerging safety issues')\n"
            "  investigate — Deep-dive into ONE SPECIFIC drug using FAERS adverse event data "
                            "(e.g. 'Investigate Cardizol-X', 'Is Neurofen-Plus safe?')\n"
            "  report      — Generate a formal safety report for a specific drug "
                            "(e.g. 'Generate safety report for Arthrex-200')\n"
            "  data_query  — Quick factual FAERS database question "
                            "(e.g. 'How many events?', 'Top 5 drugs by fatality')\n"
            "  general     — Conceptual / knowledge question that does NOT need FAERS data: "
                            "drug labels, warnings, contraindications, dosage, mechanism, "
                            "pharmacovigilance methods, PRR, EBGM, ICH guidelines, etc.\n"
            "  out_of_scope — Completely unrelated to drugs or pharmacovigilance "
                            "(e.g. 'weather', 'jokes', 'sports', 'coding help')\n\n"
            "Rules:\n"
            "  - Greetings, small talk, 'how are you', 'what can you do' → greeting\n"
            "  - Drug label/warnings/contraindications/dosage questions → general "
                "(even if a drug name is mentioned)\n"
            "  - Questions needing actual FAERS counts/demographics → investigate or data_query\n"
            "  - Respond with exactly: "
                '{"route": "<route>", "drug_name": "<drug or empty>", "reaction_term": "<reaction or empty>"}'
        )

        # ── Build conversation history context for follow-ups ──
        history = state.get("conversation_history", [])
        history_context = ""
        if history:
            # Keep last 6 turns to avoid token bloat
            recent = history[-6:]
            history_lines = []
            for turn in recent:
                role = turn.get("role", "user")
                content = turn.get("content", "")[:300]  # truncate long responses
                prefix = "User" if role == "user" else "Assistant"
                history_lines.append(f"{prefix}: {content}")
            history_context = (
                "\n\nConversation history (most recent messages):\n"
                + "\n".join(history_lines)
                + "\n\nUse the conversation history to understand follow-up references "
                "(e.g. 'that drug', 'tell me more', 'investigate it', etc.).\n"
            )

        classification_user = f'{history_context}User query: "{query}"'

        response_text = await _call_llm_direct(classification_system, classification_user)
        logger.info(f"Master Orchestrator (Groq direct) raw response: {response_text[:500]}")

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
            known_drugs = [
                "cardizol-x", "neurofen-plus", "arthrex-200",
                "cardizol", "neurofen", "arthrex",
                "lipitorex", "metforin-xr", "metforin", "amlodex",
                "omeprazol-20", "omeprazol", "sertralex", "levothyra",
                "gabapentex", "lisinox", "simvalex", "warfatrex",
                "prednizol", "tramadex", "clopidex", "azithrex",
                "fluoxetex", "ramiprilex", "diclofex",
            ]
            found_drug = ""
            for d in known_drugs:
                if d in q_lower:
                    # Capitalise properly
                    drug_map = {
                        "cardizol-x": "Cardizol-X", "cardizol": "Cardizol-X",
                        "neurofen-plus": "Neurofen-Plus", "neurofen": "Neurofen-Plus",
                        "arthrex-200": "Arthrex-200", "arthrex": "Arthrex-200",
                        "lipitorex": "Lipitorex", "metforin-xr": "Metforin-XR",
                        "metforin": "Metforin-XR", "amlodex": "Amlodex",
                        "omeprazol-20": "Omeprazol-20", "omeprazol": "Omeprazol-20",
                        "sertralex": "Sertralex", "levothyra": "Levothyra",
                        "gabapentex": "Gabapentex", "lisinox": "Lisinox",
                        "simvalex": "Simvalex", "warfatrex": "Warfatrex",
                        "prednizol": "Prednizol", "tramadex": "Tramadex",
                        "clopidex": "Clopidex", "azithrex": "Azithrex",
                        "fluoxetex": "Fluoxetex", "ramiprilex": "Ramiprilex",
                        "diclofex": "Diclofex",
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
        valid_routes = {"full_scan", "investigate", "report", "data_query", "general", "out_of_scope", "greeting"}
        if route not in valid_routes:
            logger.warning(f"Master Node: Invalid route '{route}', defaulting to full_scan")
            route = "full_scan"

        # If investigate/report/data_query requires a drug but none extracted, fall back to full_scan
        if route in ("investigate", "report") and not drug:
            logger.info(f"Master Node: Route '{route}' requires a drug name but none found, falling back to full_scan")
            route = "full_scan"

        logger.info(f"Master Node: route={route}, drug={drug}, reaction={reaction}")

        # For greeting / out_of_scope: suppress reasoning trace.
        # These routes involve no tools or meaningful agent work,
        # so showing internal routing steps is noisy and unhelpful.
        if route in ("greeting", "out_of_scope"):
            reasoning = []   # clear the "thinking" step added earlier
        else:
            # User-friendly conclusion messages by route
            friendly_conclusions = {
                "full_scan": "Scanning the safety database for any concerning patterns...",
                "investigate": f"Starting a deep-dive safety review{f' for {drug}' if drug else ''}...",
                "report": f"Preparing a safety report{f' for {drug}' if drug else ''}...",
                "data_query": f"Looking up the data{f' for {drug}' if drug else ''} to answer your question...",
                "general": "Searching our knowledge base for the best answer...",
            }
            conclusion_msg = friendly_conclusions.get(route, "Working on your request...")
            reasoning.append({
                "agent": "master_orchestrator",
                "step_type": "conclusion",
                "content": conclusion_msg,
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
            "content": "Running a full safety scan to cover all angles...",
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


async def direct_query_node(state: SignalShieldState) -> dict:
    """Handles quick data queries by routing to the most appropriate Elastic agent.
    
    For drug-specific questions → case_investigator agent
    For broad data questions → signal_scanner agent
    """
    query = state.get("query", "")
    drug = state.get("extracted_drug", "")
    reaction = state.get("extracted_reaction", "")

    logger.info(f"Direct Query Node: Answering data question — '{query[:80]}'")

    # Build conversation context for follow-ups
    history = state.get("conversation_history", [])
    history_context = ""
    if history:
        recent = history[-4:]
        history_lines = [f"{'User' if t.get('role')=='user' else 'Assistant'}: {t.get('content','')[:200]}" for t in recent]
        history_context = "\n\nRecent conversation for context:\n" + "\n".join(history_lines) + "\n"

    reasoning = [{
        "agent": "data_query",
        "step_type": "thinking",
        "content": f"{'Looking up data for ' + drug + '...' if drug else 'Searching the database for your answer...'}",
        "tool_name": "", "tool_input": {}, "tool_query": "", "tool_result": "",
        "timestamp": _now_iso(),
    }]

    # Choose the right agent based on whether a drug is specified
    if drug:
        agent_id = "case_investigator"
        enhanced_query = (
            f"Answer this specific data question about {drug}:\n{query}\n\n"
            f"{history_context}"
            f"Context: Our FAERS database has embedded safety signals for 3 drugs: "
            f"Cardizol-X (cardiac arrhythmia spike in last 90 days), "
            f"Neurofen-Plus (hepatotoxicity in 65+ females, rising trend), "
            f"Arthrex-200 (rhabdomyolysis with statin co-prescription like Lipitorex/Simvalex).\n\n"
            f"Use the appropriate tools to get the exact data requested. "
            f"Be concise and data-focused in your response."
        )
    else:
        agent_id = "signal_scanner"
        enhanced_query = (
            f"Answer this data question about the FAERS database:\n{query}\n\n"
            f"{history_context}"
            f"Context: Our FAERS database has embedded safety signals for 3 drugs: "
            f"Cardizol-X (cardiac arrhythmia spike in last 90 days), "
            f"Neurofen-Plus (hepatotoxicity in 65+ females, rising trend), "
            f"Arthrex-200 (rhabdomyolysis with statin co-prescription like Lipitorex/Simvalex).\n\n"
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
            "content": "Found the data — here's your answer.",
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
            "content": "Couldn't retrieve the data right now. Please try again.",
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


async def out_of_scope_node(state: SignalShieldState) -> dict:
    """Handles queries outside the pharmacovigilance domain.

    Uses Groq LLM to generate a natural, polite redirect — not a static wall.
    The LLM acknowledges the user's question and gently guides them to
    drug-safety topics SignalShield can actually help with.
    """
    query = state.get("query", "")
    logger.info(f"Out of Scope Node: Politely redirecting — '{query[:80]}'")

    # Build conversation context for follow-ups
    history = state.get("conversation_history", [])
    history_context = ""
    if history:
        recent = history[-4:]
        history_lines = [f"{'User' if t.get('role')=='user' else 'Assistant'}: {t.get('content','')[:200]}" for t in recent]
        history_context = "\nRecent conversation:\n" + "\n".join(history_lines) + "\n"

    try:
        redirect_response = await _call_llm_direct(
            system_prompt=(
                "You are SignalShield AI — a specialist drug safety and pharmacovigilance assistant. "
                "The user has asked a question that is outside your domain. "
                "Respond in 2-3 short sentences MAX. Be warm, polite, and professional. "
                "Briefly acknowledge their question, then explain you specialize in drug safety. "
                "Suggest ONE relevant example query they could try — for example: "
                "'Investigate Cardizol-X for cardiac safety signals', "
                "'Is Neurofen-Plus safe for elderly patients?', or "
                "'Check Arthrex-200 interactions with statins'. "
                "Do NOT use headers, bullet lists, or emoji. Keep it conversational and concise."
            ),
            user_message=f'{history_context}The user asked: "{query}"',
        )
    except Exception as e:
        logger.warning(f"Out-of-scope LLM call failed, using fallback: {e}")
        redirect_response = (
            f"That's an interesting question, but I'm SignalShield AI — I specialize in "
            f"drug safety and pharmacovigilance. Try asking me something like "
            f"\"Investigate Cardizol-X for cardiac safety signals\" and I can help!"
        )

    return {
        "status": "complete",
        "direct_response": redirect_response,
        "current_agent": "none",
        "reasoning_trace": [],
        "progress_messages": ["Redirecting to drug safety topics"],
    }


async def greeting_node(state: SignalShieldState) -> dict:
    """Handles greetings and conversational openers with a natural LLM response."""
    query = state.get("query", "")
    logger.info(f"Greeting Node: Responding naturally — '{query[:80]}'")

    # Build conversation context for follow-ups
    history = state.get("conversation_history", [])
    history_context = ""
    if history:
        recent = history[-4:]
        history_lines = [f"{'User' if t.get('role')=='user' else 'Assistant'}: {t.get('content','')[:200]}" for t in recent]
        history_context = "\n\nRecent conversation:\n" + "\n".join(history_lines) + "\n"

    try:
        greeting_response = await _call_llm_direct(
            system_prompt=(
                "You are SignalShield AI — a friendly, professional drug safety and "
                "pharmacovigilance assistant. The user is greeting you or asking a "
                "conversational question. Respond warmly and naturally in 2-4 sentences. "
                "Briefly introduce what you can do (drug safety signals, investigations, "
                "safety reports, pharma knowledge). "
                "You monitor a FAERS database with 20 drugs. Three drugs have active safety "
                "signals you can investigate: Cardizol-X (cardiac arrhythmia spike), "
                "Neurofen-Plus (hepatotoxicity in elderly females), and Arthrex-200 "
                "(rhabdomyolysis with statin co-prescription). "
                "You can suggest the user try asking about one of these drugs. "
                "End by asking how you can help them today. "
                "Be conversational — NOT robotic. Do NOT use bullet lists or headers. "
                "Keep it short and welcoming. "
                "If there is conversation history provided, acknowledge the ongoing conversation naturally."
            ),
            user_message=f"{history_context}{query}",
        )
    except Exception as e:
        logger.warning(f"Greeting LLM call failed, using fallback: {e}")
        greeting_response = (
            "Hey there! I'm SignalShield AI, your drug safety assistant. "
            "I can help you scan for safety signals, investigate specific drugs, "
            "and generate regulatory reports. How can I help you today?"
        )

    return {
        "status": "complete",
        "direct_response": greeting_response,
        "current_agent": "none",
        "progress_messages": ["👋 Ready to assist with drug safety"],
    }


async def general_knowledge_node(state: SignalShieldState) -> dict:
    """Answers general pharmacovigilance / drug-label questions.

    Uses Groq LLM DIRECTLY — no Elastic Agent Builder, no tool calls.
    This is the correct path for questions that purely need LLM reasoning:
      - What is PRR / EBGM / ROR?
      - Drug label: contraindications, warnings, dosage, interactions
      - ICH guidelines, FAERS methodology, pharmacovigilance concepts

    RAG context from the knowledge base is still retrieved via Elasticsearch
    and injected into the prompt, but NO tools are invoked on the LLM side.
    """
    query = state.get("query", "")
    drug = state.get("extracted_drug", "")
    logger.info(f"General Knowledge Node (Groq direct): '{query[:80]}'")

    # Build conversation context for follow-ups
    history = state.get("conversation_history", [])
    history_context = ""
    if history:
        recent = history[-6:]
        history_lines = [f"{'User' if t.get('role')=='user' else 'Assistant'}: {t.get('content','')[:300]}" for t in recent]
        history_context = "\n\nConversation history (for context):\n" + "\n".join(history_lines) + "\n"

    reasoning = [{
        "agent": "master_orchestrator",
        "step_type": "thinking",
        "content": "Looking through our pharma knowledge base...",
        "tool_name": "", "tool_input": {}, "tool_query": "", "tool_result": "",
        "timestamp": _now_iso(),
    }]

    # ── RAG: Pull relevant docs from Elasticsearch ────────────────────────
    rag_context = ""
    try:
        from app.config import settings
        from elasticsearch import Elasticsearch

        es = Elasticsearch(
            settings.elasticsearch_url,
            api_key=settings.elasticsearch_api_key,
            request_timeout=15,
        )

        hits = []

        # 1. Try semantic search (ELSER)
        try:
            sem_results = es.search(
                index="pharma_knowledge",
                body={
                    "query": {"semantic": {"field": "content_semantic", "query": query}},
                    "size": 3,
                    "_source": ["title", "category", "content"],
                },
            )
            hits = sem_results.get("hits", {}).get("hits", [])
            if hits:
                logger.info(f"RAG semantic search returned {len(hits)} hits")
        except Exception:
            logger.info("Semantic search unavailable, falling back to BM25")

        # 2. Fallback to BM25 full-text
        if not hits:
            bm25_results = es.search(
                index="pharma_knowledge",
                body={
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
                },
                ignore=[404],
            )
            hits = bm25_results.get("hits", {}).get("hits", [])

        if hits:
            pieces = []
            for hit in hits:
                src = hit["_source"]
                pieces.append(
                    f"--- {src['title']} [{src['category']}] ---\n{src['content'][:2000]}"
                )
            rag_context = "\n\n".join(pieces)
            doc_titles = ", ".join(h["_source"]["title"] for h in hits)
            reasoning.append({
                "agent": "master_orchestrator",
                "step_type": "tool_call",
                "content": f"Found {len(hits)} relevant reference(s): {doc_titles}",
                "tool_name": "pharma.search_knowledge",
                "tool_input": {"search_query": query[:100]},
                "tool_query": f"Knowledge base search: '{query[:80]}' → {len(hits)} results",
                "tool_result": doc_titles,
                "timestamp": _now_iso(),
            })
        else:
            logger.info("RAG returned no hits — answering from LLM knowledge only.")

    except Exception as rag_err:
        logger.warning(f"RAG search failed (non-critical): {rag_err}")

    # ── Answer via Groq directly (no tools) ──────────────────────────────
    try:
        system_prompt = (
            "You are SignalShield AI — a specialist pharmacovigilance and drug safety assistant. "
            "Answer questions clearly, accurately, and concisely using markdown formatting. "
            "When context from the knowledge base is provided, use it to ground your answer "
            "and cite document titles where relevant. "
            "Focus only on pharmacovigilance, drug safety, drug labels, and related medical topics. "
            "Do NOT make up data or statistics — if you are uncertain, say so.\n\n"
            f"{DEMO_DRUG_SIGNALS_CONTEXT}"
        )

        user_message_parts = []
        if rag_context:
            user_message_parts.append(
                f"## Relevant Knowledge Base Context\n\n{rag_context}\n\n"
                f"---\nUse the above context to ground your answer. "
                f"Cite document titles when applicable.\n"
            )
        if drug:
            user_message_parts.append(f"(Drug in question: **{drug}**)\n")
        if history_context:
            user_message_parts.append(f"{history_context}\n")
        user_message_parts.append(f"## Question\n\n{query}")

        user_message = "\n".join(user_message_parts)

        response_text = await _call_llm_direct(system_prompt, user_message)
        logger.info(f"General Knowledge Node answered ({len(response_text)} chars)")

        reasoning.append({
            "agent": "master_orchestrator",
            "step_type": "conclusion",
            "content": "Here's what I found for you.",
            "tool_name": "", "tool_input": {}, "tool_query": "", "tool_result": "",
            "timestamp": _now_iso(),
        })

        return {
            "status": "complete",
            "direct_response": response_text,
            "current_agent": "none",
            "reasoning_trace": reasoning,
            "progress_messages": ["💡 Knowledge question answered directly by LLM"],
        }

    except Exception as e:
        logger.error(f"General Knowledge Node (Groq direct) failed: {e}")
        return {
            "status": "error",
            "direct_response": f"Sorry, I couldn't answer that question: {str(e)}",
            "errors": [f"General knowledge error: {str(e)}"],
            "reasoning_trace": reasoning,
            "progress_messages": [f"General knowledge query failed: {str(e)}"],
        }


async def scan_signals_node(state: SignalShieldState) -> dict:
    """Node 1: Call Signal Scanner agent to detect emerging safety signals."""
    logger.info("Node: scan_signals — Starting signal surveillance")

    query = state.get("query", "Scan for any emerging drug safety signals in FAERS data from the last 90 days")

    reasoning = []
    reasoning.append({
        "agent": "signal_scanner",
        "step_type": "thinking",
        "content": "Scanning the safety database for unusual patterns...",
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
            drug_list = ", ".join(s['drug_name'] for s in signals)
            reasoning.append({
                "agent": "signal_scanner",
                "step_type": "conclusion",
                "content": f"Found {len(signals)} potential safety concern(s) involving: {drug_list}. Investigating further...",
                "tool_name": "", "tool_input": {}, "tool_query": "", "tool_result": "",
                "timestamp": _now_iso(),
            })
        else:
            reasoning.append({
                "agent": "signal_scanner",
                "step_type": "conclusion",
                "content": "Scan complete — no safety concerns found in the recent data.",
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
            "content": "Something went wrong during the safety scan. Please try again.",
            "tool_name": "", "tool_input": {}, "tool_query": "", "tool_result": "",
            "timestamp": _now_iso(),
        })
        return {
            "status": "error",
            "errors": [f"Signal Scanner error: {str(e)}"],
            "reasoning_trace": reasoning,
            "progress_messages": [f"Signal Scanner failed: {str(e)}"],
        }


async def investigate_cases_node(state: SignalShieldState) -> dict:
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
    reasoning = []

    reasoning.append({
        "agent": "case_investigator",
        "step_type": "thinking",
        "content": f"Digging deeper into {len(signals)} flagged drug(s) — checking patient details, interactions, and outcomes...",
        "tool_name": "", "tool_input": {}, "tool_query": "", "tool_result": "",
        "timestamp": _now_iso(),
    })

    # ── Investigate all signals in PARALLEL for speed ──────────────────
    async def _investigate_one(i: int, signal: dict) -> tuple[dict, list[dict]]:
        """Investigate a single signal. Returns (investigation, reasoning_steps)."""
        drug = signal.get("drug_name", "Unknown")
        reaction = signal.get("reaction_term", "Unknown")
        steps = []

        logger.info(f"Investigating signal {i+1}/{len(signals)}: {drug} → {reaction}")

        steps.append({
            "agent": "case_investigator",
            "step_type": "thinking",
            "content": f"Reviewing {drug} ({i+1} of {len(signals)}) — looking at who was affected and how...",
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
                # Each parallel call gets its own conversation (no shared ID)
            )

            agent_reasoning = _extract_reasoning_from_response("case_investigator", result)
            steps.extend(agent_reasoning)

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

            resp_lower = result["response"].lower()
            if "interaction" in resp_lower and ("yes" in resp_lower or "detected" in resp_lower or "potential" in resp_lower):
                investigation["interaction_detected"] = True

            interaction_note = "Found a possible drug interaction." if investigation['interaction_detected'] else "No major drug interactions found."
            steps.append({
                "agent": "case_investigator",
                "step_type": "conclusion",
                "content": f"Finished reviewing {drug}. {interaction_note}",
                "tool_name": "", "tool_input": {}, "tool_query": "", "tool_result": "",
                "timestamp": _now_iso(),
            })

            return investigation, steps

        except Exception as e:
            logger.error(f"Investigation failed for {drug}: {type(e).__name__}: {e}")
            steps.append({
                "agent": "case_investigator",
                "step_type": "conclusion",
                "content": f"Couldn't complete the review for {drug}. Please try again.",
                "tool_name": "", "tool_input": {}, "tool_query": "", "tool_result": "",
                "timestamp": _now_iso(),
            })
            return {
                "drug_name": drug,
                "reaction_term": reaction,
                "raw_response": f"Error: {str(e)}",
                "overall_assessment": f"Investigation failed: {str(e)}",
            }, steps

    # Run all investigations concurrently
    results = await asyncio.gather(
        *[_investigate_one(i, sig) for i, sig in enumerate(signals)]
    )

    for inv, steps in results:
        investigations.append(inv)
        reasoning.extend(steps)

    return {
        "status": "reporting",
        "investigations": investigations,
        "current_agent": "safety_reporter",
        "total_investigations": len(investigations),
        "reasoning_trace": reasoning,
        "progress_messages": [
            f"Case Investigator completed: {len(investigations)} signal(s) investigated"
        ],
    }


async def generate_reports_node(state: SignalShieldState) -> dict:
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
    reasoning = []

    reasoning.append({
        "agent": "safety_reporter",
        "step_type": "thinking",
        "content": f"Writing safety report(s) for {len(investigations)} drug(s)...",
        "tool_name": "", "tool_input": {}, "tool_query": "", "tool_result": "",
        "timestamp": _now_iso(),
    })

    # ── Generate all reports in PARALLEL for speed ─────────────────────
    async def _generate_one(i: int, investigation: dict) -> tuple[dict, list[dict]]:
        """Generate a single safety report. Returns (report, reasoning_steps)."""
        drug = investigation.get("drug_name", "Unknown")
        reaction = investigation.get("reaction_term", "Unknown")
        steps = []

        logger.info(f"Generating report {i+1}/{len(investigations)}: {drug} → {reaction}")

        matching_signal = next(
            (s for s in signals if s.get("drug_name") == drug),
            {},
        )

        steps.append({
            "agent": "safety_reporter",
            "step_type": "thinking",
            "content": f"Gathering all findings for {drug} to prepare the report...",
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
                # Each parallel call gets its own conversation (no shared ID)
            )

            agent_reasoning = _extract_reasoning_from_response("safety_reporter", result)
            steps.extend(agent_reasoning)

            signal_priority = matching_signal.get("priority", "MEDIUM").upper()
            risk_level = signal_priority

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

            steps.append({
                "agent": "safety_reporter",
                "step_type": "conclusion",
                "content": f"Safety report for {drug} is ready. Risk level: {risk_level}.",
                "tool_name": "", "tool_input": {}, "tool_query": "", "tool_result": "",
                "timestamp": _now_iso(),
            })

            return report, steps

        except Exception as e:
            logger.error(f"Report generation failed for {drug}: {type(e).__name__}: {e}")
            steps.append({
                "agent": "safety_reporter",
                "step_type": "conclusion",
                "content": f"Couldn't generate the report for {drug}. Please try again.",
                "tool_name": "", "tool_input": {}, "tool_query": "", "tool_result": "",
                "timestamp": _now_iso(),
            })
            return {
                "drug_name": drug,
                "reaction_term": reaction,
                "risk_level": "UNKNOWN",
                "report_markdown": f"Report generation failed: {str(e)}",
            }, steps

    # Run all report generations concurrently
    results = await asyncio.gather(
        *[_generate_one(i, inv) for i, inv in enumerate(investigations)]
    )

    for rpt, steps in results:
        reports.append(rpt)
        reasoning.extend(steps)

    return {
        "status": "complete",
        "reports": reports,
        "current_agent": "none",
        "total_reports": len(reports),
        "reasoning_trace": reasoning,
        "progress_messages": [
            f"Safety Reporter completed: {len(reports)} report(s) generated"
        ],
    }


async def compile_results_node(state: SignalShieldState) -> dict:
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
        "progress_messages": [summary],
    }
