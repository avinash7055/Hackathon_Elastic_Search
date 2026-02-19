# PharmaVigil AI 💊🔍

**Autonomous Drug Safety Signal Detection** — A multi-agent pharmacovigilance system that detects, investigates, and reports on emerging drug safety signals using FDA FAERS data in **under 30 seconds**.

> Built for the [Elasticsearch Agent Builder Hackathon 2026](https://www.elastic.co/campaigns/agent-builder-hackathon)

---

## 🎯 The Problem

Pharmacovigilance — monitoring drugs for adverse effects after market approval — is a **$5 billion/year** industry that still relies heavily on manual review. Dangerous signals can go undetected for **months to years**, putting patients at risk.

- 800,000+ adverse event reports filed annually in the US alone
- Manual review cycles take **2–6 weeks** per signal
- Critical drug interactions buried in millions of records

## 💡 The Solution

PharmaVigil AI deploys **3 specialized Elastic Agent Builder agents** orchestrated by LangGraph to autonomously scan, investigate, and report on drug safety signals:

| Agent | Role | Tools Used |
|---|---|---|
| 🔍 **Signal Scanner** | Scans FAERS data for statistical anomalies using PRR & temporal spike detection | `scan_adverse_event_trends`, `detect_temporal_spike`, `calculate_reporting_ratio` |
| 🔬 **Case Investigator** | Deep-dives into demographics, co-medications, severity, geography | `analyze_patient_demographics`, `find_concomitant_drugs`, `check_outcome_severity`, `geo_distribution` |
| 📋 **Safety Reporter** | Generates structured FDA MedWatch-style safety assessment reports | `compile_signal_summary`, `geo_distribution`, `check_outcome_severity` |

**Result: 3 weeks → 30 seconds.** From raw adverse event data to a prioritized, actionable safety report.

---

## 🏗 Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  Elastic Cloud Serverless                                         │
│  ┌────────────────────────────────────────────┐                  │
│  │  Elasticsearch: 500K+ Synthetic FAERS      │                  │
│  │  Index: faers_reports                      │                  │
│  └────────────────────────────────────────────┘                  │
│  ┌────────────────────────────────────────────┐                  │
│  │  Elastic Agent Builder (Kibana)            │                  │
│  │  • signal_scanner    — 3 ES|QL tools       │                  │
│  │  • case_investigator — 4 ES|QL tools       │                  │
│  │  • safety_reporter   — 3 ES|QL tools       │                  │
│  │  19 registered tools total                 │                  │
│  └──────────────┬─────────────────────────────┘                  │
│                 │ Converse API (HTTPS)                            │
└─────────────────┼────────────────────────────────────────────────┘
                  │
┌─────────────────┼────────────────────────────────────────────────┐
│  Python Backend (FastAPI + LangGraph)                             │
│  ┌──────────────▼──────────────────────┐                         │
│  │  LangGraph StateGraph               │                         │
│  │  scan_signals → investigate_cases   │                         │
│  │       → generate_reports            │                         │
│  │       → compile_results             │                         │
│  │  (conditional routing on signals)   │                         │
│  └──────────────┬──────────────────────┘                         │
│  ┌──────────────▼──────────────────────┐                         │
│  │  FastAPI REST + WebSocket           │                         │
│  │  POST /api/investigate              │                         │
│  │  GET  /api/investigations/:id       │                         │
│  │  WS   /ws/progress/:id  (real-time) │                         │
│  └──────────────┬──────────────────────┘                         │
└─────────────────┼────────────────────────────────────────────────┘
                  │
┌─────────────────┼────────────────────────────────────────────────┐
│  React Frontend (Vite)                                            │
│  ┌──────────────▼──────────────────────┐                         │
│  │  Dashboard                          │                         │
│  │  • Natural language query input     │                         │
│  │  • 6 quick-query chips              │                         │
│  │  • Live pipeline steps indicator    │                         │
│  │  • 🧠 Agent Reasoning Trace panel   │                         │
│  │  • Signal table (PRR, spike, badge) │                         │
│  │  • Signal Strength bar chart        │                         │
│  │  • Safety report viewer (Markdown)  │                         │
│  └─────────────────────────────────────┘                         │
└──────────────────────────────────────────────────────────────────┘
```

### Key Technologies

| Component | Technology |
|---|---|
| Agent Logic | Elastic Agent Builder (custom agents + ES|QL tools) |
| Data Store | Elasticsearch Serverless |
| Query Language | ES|QL (19 parameterized queries, `DATE_DIFF` based) |
| Orchestration | LangGraph `StateGraph` with conditional routing |
| LLM Backbone | Groq `llama-3.3-70b-versatile` (auto-retry on rate limits) |
| Backend API | FastAPI + WebSocket (real-time progress streaming) |
| Frontend | React 18 + Recharts + ReactMarkdown |
| Data Source | Synthetic FDA FAERS data (500K+ records) |

---

## ✨ Features

### 🔍 Autonomous Signal Detection
- Scans all drugs in FAERS for adverse event volume anomalies
- Computes **Proportional Reporting Ratio (PRR)** for disproportionate reactions
- Detects **temporal spikes** by comparing 90-day recent rate vs 365-day baseline

### 🧠 Agent Reasoning Transparency
- Full step-by-step reasoning trace from all 3 agents displayed in real-time
- See every **ES|QL query** the agents run, with results
- Expandable tool call cards show `tool name → parameters → ES|QL → results`
- Step count and tool call count displayed in the reasoning panel header

### 💬 Natural Language Investigation Queries
- Free-text input: ask anything (e.g., *"Are there cardiac signals for Cardizol-X?"*)
- 6 **quick-query chips** for common investigation types:
  - Full Safety Scan · Cardiac Signals · Hepatotoxicity · Drug Interactions · Pediatric Safety · Rhabdomyolysis

### 📡 Real-Time Progress Streaming
- WebSocket connection streams pipeline progress live
- Pipeline step indicator shows Scanner → Investigator → Reporter status
- Investigation log panel shows timestamped progress messages

### 📋 Structured Safety Reports
- Markdown reports rendered in-browser from the Safety Reporter agent
- Risk level badge (`HIGH` / `MEDIUM` / `LOW` / `CRITICAL`) derived from signal priority
- Tabbed viewer to switch between reports for multiple signals

### 🔄 Robust Error Handling
- Auto-retry with exponential backoff on Groq API 429 rate limit errors (max 3 retries, reads `retry-after` header)
- Signal parser has two-layer fallback: text parsing → raw API step mining
- ES|QL tools use `COALESCE` to handle optional parameters gracefully

---

## 📊 Confirmed Detected Signals

The synthetic dataset embeds 3 drug safety signals. The pipeline **correctly identifies** these on every run:

| Priority | Drug | Spike Ratio | Key Reactions | Pattern |
|---|---|---|---|---|
| 🔴 **HIGH** | **Cardizol-X** | **3.41×** | Cardiac arrest, Tachycardia, QT prolongation, Ventricular tachycardia | 18,323 events in 90d; 91% serious, 18% fatal |
| 🟡 **MEDIUM** | **Neurofen-Plus** | **2.29×** | Hepatic failure, Jaundice, Liver injury, Transaminases increased | Predominantly elderly females (avg age 74.8) |
| 🟢 **LOW** | **Arthrex-200** | ~1.2× | Rhabdomyolysis with statin co-prescription | Drug-drug interaction signal |

---

## 📃 ES|QL Tools (19 Total)

| Tool ID | What It Does |
|---|---|
| `pharma.scan_adverse_event_trends` | Time-bucketed adverse event counts, serious/fatal breakdown per drug |
| `pharma.calculate_reporting_ratio` | Proportional Reporting Ratio (PRR ≥ 2.0 = signal) |
| `pharma.detect_temporal_spike` | Recent 90-day daily rate vs 365-day baseline spike ratio |
| `pharma.analyze_patient_demographics` | Age group, sex, weight distribution per drug/reaction |
| `pharma.find_concomitant_drugs` | Top 15 co-reported drugs with seriousness % |
| `pharma.check_outcome_severity` | Fatal/hospitalization/disability/life-threatening counts |
| `pharma.geo_distribution` | Country-level event counts and seriousness rates |
| `pharma.compile_signal_summary` | Comprehensive reaction-level report profile |

All queries use `DATE_DIFF("day", report_date, NOW())` for time filtering and `COALESCE` for optional parameter handling.

---

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- [Elastic Cloud Serverless trial](https://cloud.elastic.co/registration?cta=agentbuilderhackathon)
- [Groq API key](https://console.groq.com/) (free tier)

### 1. Clone & Install

```bash
git clone https://github.com/avinash7055/Hackathon_Elastic_Search.git
cd Hackathon_Elastic_Search

# Python dependencies
python -m venv venv
venv\Scripts\activate       # Windows
# source venv/bin/activate  # Mac/Linux
pip install -r requirements.txt

# Frontend dependencies
cd frontend && npm install && cd ..
```

### 2. Configure Environment

```bash
copy .env.example .env   # Windows
# cp .env.example .env   # Mac/Linux
```

Edit `.env`:

```env
ELASTICSEARCH_URL=https://<your-project>.es.<region>.elastic.cloud:443
ELASTICSEARCH_API_KEY=<your-es-api-key>

KIBANA_URL=https://<your-project>.kb.<region>.elastic.cloud:443
KIBANA_API_KEY=<your-kibana-api-key>

GROQ_API_KEY=<your-groq-api-key>
GROQ_MODEL=llama-3.3-70b-versatile

LOG_LEVEL=INFO
FAERS_RECORD_COUNT=500000
```

### 3. Generate Synthetic FAERS Data

```bash
python -m data.generate_faers_data \
  --es-url $ELASTICSEARCH_URL \
  --api-key $ELASTICSEARCH_API_KEY \
  --count 500000
```

> This creates the `faers_reports` index with 500K records including embedded safety signals for Cardizol-X, Neurofen-Plus, and Arthrex-200.

### 4. Register Agents & Tools in Kibana

```bash
python -m setup.setup_agents \
  --kibana-url $KIBANA_URL \
  --api-key $KIBANA_API_KEY
```

> **Re-run this any time you modify `agent_config/tools.json` or `agent_config/agents.json`.**

### 5. Run

```bash
# Terminal 1 — Backend
uvicorn app.api:app --reload --port 8000

# Terminal 2 — Frontend
cd frontend && npm run dev
```

Open **[http://localhost:5173](http://localhost:5173)** and click **🔍 Investigate** or select a quick-query chip.

---

## 📁 Project Structure

```
pharmavigil-ai/
├── agent_config/
│   ├── agents.json          # Agent definitions (system prompts, model config)
│   └── tools.json           # 19 ES|QL tool definitions with parameterized queries
├── app/
│   ├── api.py               # FastAPI endpoints + WebSocket progress streaming
│   ├── config.py            # Pydantic settings from .env
│   ├── elastic_client.py    # Kibana Converse API client (with retry logic)
│   └── graph/
│       ├── graph.py         # LangGraph StateGraph definition + routing
│       ├── nodes.py         # Agent node functions + signal parsing logic
│       └── state.py         # PharmaVigilState TypedDict
├── data/
│   └── generate_faers_data.py   # Synthetic FAERS data generator
├── frontend/
│   └── src/
│       ├── App.jsx           # Full React dashboard
│       └── index.css         # Design system (dark theme, glassmorphism)
├── setup/
│   └── setup_agents.py      # Kibana agent/tool registration script
├── test_groq.py             # Quick Groq API connectivity test
├── requirements.txt
└── .env.example
```

---

## 🏆 Hackathon Submission

Built for the **Elasticsearch Agent Builder Hackathon 2026** demonstrating:

- ✅ **Elastic Agent Builder** — 3 custom agents with 19 ES|QL tools
- ✅ **Multi-agent orchestration** — LangGraph StateGraph with conditional routing
- ✅ **Agent transparency** — Full reasoning trace visible in real-time UI
- ✅ **Natural language interface** — Free-text + quick-query chip input
- ✅ **Real-world use case** — Drug safety signal detection (pharmacovigilance)
- ✅ **Production-quality** — Error handling, retry logic, WebSocket streaming

---

## 📜 License

[MIT License](LICENSE)
