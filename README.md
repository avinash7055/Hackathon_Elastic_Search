# PharmaVigil AI 💊🔍

**Autonomous Drug Safety & Pharmacovigilance System** — A multi-agent AI system that detects safety signals, investigates adverse events, generates regulatory reports, and answers complex drug-label questions using FDA FAERS data and RAG in **under 30 seconds**.

> Built for the [Elasticsearch Agent Builder Hackathon](https://www.elastic.co/campaigns/agent-builder-hackathon)

---

## 🎯 The Problem

Pharmacovigilance — monitoring drugs for adverse effects after market approval — is a **$5 billion/year** industry relying heavily on manual review. Dangerous signals can go undetected for **months to years**, putting patients at risk. 

- **Data overload:** 800,000+ adverse event reports filed annually.
- **Slow processes:** Manual review cycles take **2–6 weeks** per signal.
- **Siloed knowledge:** Guidelines, methodologies (PRR, EBGM), and drug labels are scattered across complex PDFs and databases.

## 💡 The Solution

PharmaVigil AI deploys **5 specialized AI Agents** orchestrated by LangGraph, powered by Elastic Agent Builder and ELSER Semantic Search:

| Agent | Role | Capabilities |
|---|---|---|
| 🧠 **Master Orchestrator** | Intelligent Router | Understands intent, extracts entities, and routes to the correct specialized pipeline (6 distinct routes). |
| 📚 **Knowledge Expert (RAG)** | Pharmacovigilance Guru | Uses ELSER semantic search to answer questions about drug labels, contraindications, and ICH guidelines. |
| 🔍 **Signal Scanner** | Data Anomaly Hunter | Scans FAERS data for statistical anomalies using PRR & temporal spike detection. |
| 🔬 **Case Investigator** | Deep-Dive Analyst | Investigates demographics, co-medications, severity, and geography for specific drugs. |
| 📋 **Safety Reporter** | Regulatory Writer | Generates structured, FDA MedWatch-style safety assessment reports in Markdown. |

**Result: 3 weeks → 30 seconds.** From raw data and complex documents to a prioritized, actionable safety report or grounded answer.

---

## ✨ Key Features

### 🧠 Intelligent Request Routing
The Master Orchestrator classifies every natural language query into 6 distinct routes:
1. `full_scan`: Broad safety sweeps across all drugs.
2. `investigate`: Deep-dives into a specific drug's adverse events.
3. `data_query`: Quick statistical/factual counts.
4. `report`: Formal safety report generation.
5. `general`: Knowledge questions routed to the RAG pipeline.
6. `out_of_scope`: Graceful handling of non-pharma queries.

### 📚 RAG Knowledge Base (ELSER Semantic Search)
Ask complex questions about drug prescribing information and methodology:
- *"What are the contraindications of Cardizol-X?"*
- *"What drug interactions does Arthrex-200 have with statins?"*
- *"How is Proportional Reporting Ratio (PRR) calculated?"*
Answers are grounded in an Elasticsearch vector database using ELSER, eliminating LLM hallucinations and citing specific percentages and guidelines.

### 💬 Premium Streaming User Interface
- **ChatGPT-like Streaming**: Word-by-word response streaming for a fluid, natural conversational experience.
- **Agent Reasoning Transparency**: Full step-by-step reasoning trace visible in real-time. See every ES|QL query the agents run.
- **Smart Scrolling**: Auto-scrolls gracefully, pausing if the user scrolls up to read past reasoning steps.
- **Glassmorphism Design**: High-end futuristic aesthetic with micro-animations.

### 📊 Autonomous ES|QL Signal Detection
- Scans all drugs in synthetic FAERS for adverse event volume anomalies.
- Computes **Proportional Reporting Ratio (PRR)** for disproportionate reactions.
- Detects **temporal spikes** by comparing 90-day recent rates vs 365-day baselines.

### 🧪 Comprehensive Scenario Testing Suite
A robust automated test script (`tests/test_scenarios.py`) validates the entire application:
- API Health & Connectivity
- Master Orchestrator Routing Accuracy
- RAG Knowledge Retrieval Accuracy
- Full Investigation & Report Generation Pipelines
- WebSocket Real-time Progress Streaming

---

## 🏗 Architecture

```text
┌─────────────────────────────────────────────────────────────────┐
│  Elastic Cloud Serverless                                       │
│  ┌────────────────────────┐  ┌───────────────────────────────┐  │
│  │ FDA FAERS Data (ES|QL) │  │ Knowledge Base (Vector/ELSER) │  │
│  │ Index: faers_reports   │  │ Index: pharma_knowledge       │  │
│  └────────────────────────┘  └───────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  Elastic Agent Builder (Kibana)                           │  │
│  │  • master_orchestrator   • safety_reporter                │  │
│  │  • signal_scanner        • case_investigator              │  │
│  │  (19 Custom ES|QL / Search Tools Registered)              │  │
│  └────────────────────────────┬──────────────────────────────┘  │
└───────────────────────────────┼─────────────────────────────────┘
                                │ HTTPS Converse API
┌───────────────────────────────┼─────────────────────────────────┐
│  Python Backend (FastAPI + LangGraph)                           │
│  ┌────────────────────────────▼──────────────────────────────┐  │
│  │  LangGraph StateGraph Orchestration                       │  │
│  │  master_node ── routing ──┬──> general_knowledge_node     │  │
│  │                           ├──> scan_signals_node          │  │
│  │                           └──> out_of_scope_node          │  │
│  └────────────────────────────┬──────────────────────────────┘  │
│  ┌────────────────────────────▼──────────────────────────────┐  │
│  │  FastAPI REST + WebSocket Progress Streaming              │  │
│  └────────────────────────────┬──────────────────────────────┘  │
└───────────────────────────────┼─────────────────────────────────┘
                                │ HTTP / WS
┌───────────────────────────────▼─────────────────────────────────┐
│  React Frontend (Vite)                                          │
│  • Natural Language Input   • Real-Time Streaming Responses     │
│  • Agent Reasoning Trace    • Dark-Mode Glassmorphism UI        │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+
- [Elastic Cloud Serverless trial](https://cloud.elastic.co/registration?cta=agentbuilderhackathon)

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
cd frontend
npm install
cd ..
```

### 2. Configure Environment

Copy `.env.example` to `.env` and fill in your Elastic Cloud credentials:

```env
ELASTICSEARCH_URL=https://<your-project>.es.<region>.elastic.cloud:443
ELASTICSEARCH_API_KEY=<your-es-api-key>

KIBANA_URL=https://<your-project>.kb.<region>.elastic.cloud:443
KIBANA_API_KEY=<your-kibana-api-key>

LOG_LEVEL=INFO
```

### 3. Generate Data & Knowledge Base

Generate the 500k synthetic FAERS reports (contains hidden safety signals):
```bash
python -m data.generate_faers_data --es-url $ELASTICSEARCH_URL --api-key $ELASTICSEARCH_API_KEY --count 500000
```

Generate the RAG Semantic Knowledge Base:
```bash
python -m data.generate_knowledge_base --es-url $ELASTICSEARCH_URL --api-key $ELASTICSEARCH_API_KEY
```

### 4. Register Agents & Tools

Deploys the 5 agents and 19 ES|QL tools to your Elastic Kibana instance:
```bash
python -m setup.setup_agents --kibana-url $KIBANA_URL --api-key $KIBANA_API_KEY
```

### 5. Run the Application

```bash
# Terminal 1 — Backend
uvicorn app.api:app --reload --port 8000

# Terminal 2 — Frontend
cd frontend
npm run dev
```

Open **[http://localhost:5173](http://localhost:5173)** and start investigating!

---

## 🧪 Running the Test Suite

The comprehensive scenario test validates routing, RAG accuracy, pipelines, and web-sockets. 

```bash
# Run all tests (takes ~10 mins)
python tests/test_scenarios.py

# Run a quick smoke test
python tests/test_scenarios.py --category quick

# Test specific functionality
python tests/test_scenarios.py --category routing
python tests/test_scenarios.py --category rag
```

---

## 📊 Embedded Safety Signals (For Testing)

If you run a `full_scan` or `investigate` specific drugs, the system will identify these seeded signals automatically:

| Target Drug | Priority | Identifying Pattern in Data | RAG Knowledge Base Concept |
|---|---|---|---|
| **Cardizol-X** | 🔴 HIGH | Massive 3.4x temporal spike in fatal cardiac arrhythmias. | Has strict cardiac contraindications. |
| **Neurofen-Plus** | 🟡 MED | Elevated PRR for hepatotoxicity in elderly patients. | Prescribing info warns of liver risks in >65 age group. |
| **Arthrex-200** | 🟢 LOW | Rhabdomyolysis events ONLY when co-prescribed with statins. | CYP2C9 inhibition mechanism explicitly outlined in label. |

---

## 🏆 Hackathon Features Delivered

- ✅ **Elastic Agent Builder Integration**: 5 bespoke agents natively deployed to Kibana.
- ✅ **ES\|QL Mastery**: 19 complex parameterized queries computing relative time windows, distributions, and cross-tabulations.
- ✅ **Vector & Semantic Search (ELSER)**: Complete RAG implementation for complex domain knowledge.
- ✅ **Multi-Agent Orchestration**: LangGraph state machine with deterministic LLM routing.
- ✅ **Agent Transparency UI**: Custom React frontend visualizing every API request, ES\|QL query, and tool invocation in real-time.
- ✅ **Resilience**: Automated Python testing suite & fault-tolerant agent fallback routines.

---

## 📜 License
[MIT License](LICENSE)
