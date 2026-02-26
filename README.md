# SignalShield AI 💊🔍

**Autonomous Drug Safety & Pharmacovigilance System** — A multi-agent AI system that detects safety signals, investigates adverse events, generates regulatory reports, and answers complex drug-label questions using FDA FAERS data and RAG in **under 30 seconds**.

> Built for the [Elasticsearch Agent Builder Hackathon](https://www.elastic.co/campaigns/agent-builder-hackathon)

[![Docker CI](https://github.com/avinash7055/Hackathon_Elastic_Search/actions/workflows/docker-ci.yml/badge.svg)](https://github.com/avinash7055/Hackathon_Elastic_Search/actions/workflows/docker-ci.yml)

---

## 🎯 The Problem

Pharmacovigilance — monitoring drugs for adverse effects after market approval — is a **$5 billion/year** industry relying heavily on manual review. Dangerous signals can go undetected for **months to years**, putting patients at risk.

- **Data overload:** 800,000+ adverse event reports filed annually.
- **Slow processes:** Manual review cycles take **2–6 weeks** per signal.
- **Siloed knowledge:** Guidelines, methodologies (PRR, EBGM), and drug labels are scattered across complex PDFs and databases.

## 💡 The Solution

SignalShield AI deploys **4 specialized AI Agents** orchestrated by LangGraph, powered by Elastic Agent Builder, ELSER Semantic Search, and Groq LLM (Llama 3.3 70B):

| Agent | Role | Capabilities |
|---|---|---|
| 🧠 **Master Orchestrator** | Intelligent Router | Understands intent, extracts entities, and routes to the correct specialized pipeline (7 distinct routes). |
| 🔍 **Signal Scanner** | Data Anomaly Hunter | Scans FAERS data for statistical anomalies using PRR & temporal spike detection. |
| 🔬 **Case Investigator** | Deep-Dive Analyst | Investigates demographics, co-medications, severity, and geography for specific drugs. |
| 📋 **Safety Reporter** | Regulatory Writer | Generates structured, FDA MedWatch-style safety assessment reports in Markdown. |

**Result: 3 weeks → 30 seconds.** From raw data and complex documents to a prioritized, actionable safety report or grounded answer.

---

## ✨ Key Features

### 🧠 Intelligent Request Routing
The Master Orchestrator classifies every natural language query into 7 distinct routes:
1. `full_scan` — Broad safety sweeps across all drugs.
2. `investigate` — Deep-dives into a specific drug's adverse events.
3. `data_query` — Quick statistical/factual counts from FAERS.
4. `report` — Formal safety report generation.
5. `general` — Knowledge questions routed to the RAG pipeline.
6. `greeting` — Natural conversational greetings handled by LLM.
7. `out_of_scope` — Graceful handling of non-pharma queries.

### 📚 RAG Knowledge Base (ELSER Semantic Search)
Ask complex questions about drug prescribing information and methodology:
- *"What are the contraindications of Cardizol-X?"*
- *"What drug interactions does Arthrex-200 have with statins?"*
- *"How is Proportional Reporting Ratio (PRR) calculated?"*

Answers are grounded in an Elasticsearch vector database using ELSER, eliminating LLM hallucinations and citing specific percentages and guidelines.

### 💬 Conversational AI with Chat History
- **Follow-up Questions**: Full conversational context maintained across user queries — ask follow-ups naturally.
- **ChatGPT-like Streaming**: Word-by-word response streaming via WebSocket for a fluid, natural experience.
- **Agent Reasoning Transparency**: Full step-by-step reasoning trace visible in real-time. See every ES|QL query the agents run.
- **Smart Scrolling**: Auto-scrolls gracefully, pausing if the user scrolls up to read past reasoning steps.

### 🎨 Premium Full-Stack UI
- **Landing Page**: Futuristic hero section with animated stats, feature cards, and agent showcase.
- **Authentication**: Login/Signup flow with client-side auth context (localStorage-backed).
- **Dashboard**: Glassmorphism chat interface with sidebar navigation, query suggestions, and dark-mode aesthetics.
- **PDF Export**: Download safety reports as formatted PDF documents directly from the dashboard.
- **Micro-animations**: Typing indicators, thinking messages, hover effects, and smooth transitions throughout.

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
│  │  (11 Custom ES|QL / Search Tools Registered)              │  │
│  └────────────────────────────┬──────────────────────────────┘  │
└───────────────────────────────┼─────────────────────────────────┘
                                │ HTTPS Converse API
┌───────────────────────────────┼─────────────────────────────────┐
│  Python Backend (FastAPI + LangGraph)                           │
│  ┌────────────────────────────▼──────────────────────────────┐  │
│  │  LangGraph StateGraph Orchestration                       │  │
│  │  master_node ── routing ──┬──> scan_signals_node          │  │
│  │                           ├──> investigate_cases_node     │  │
│  │                           ├──> direct_query_node          │  │
│  │                           ├──> general_knowledge_node     │  │
│  │                           ├──> greeting_node              │  │
│  │                           └──> out_of_scope_node          │  │
│  └────────────────────────────┬──────────────────────────────┘  │
│  ┌────────────────────────────▼──────────────────────────────┐  │
│  │  Groq LLM (Llama 3.3 70B) — Direct responses, RAG,      │  │
│  │  greetings, out-of-scope handling (no tool overhead)      │  │
│  └────────────────────────────┬──────────────────────────────┘  │
│  ┌────────────────────────────▼──────────────────────────────┐  │
│  │  FastAPI REST + WebSocket Progress Streaming              │  │
│  └────────────────────────────┬──────────────────────────────┘  │
└───────────────────────────────┼─────────────────────────────────┘
                                │ HTTP / WS
┌───────────────────────────────▼─────────────────────────────────┐
│  React Frontend (Vite + React Router)                           │
│  • Landing Page              • Authentication (Login/Signup)    │
│  • Dashboard Chat Interface  • Real-Time Streaming Responses    │
│  • Agent Reasoning Trace     • PDF Report Export                │
│  • Dark-Mode Glassmorphism   • Conversational Follow-ups        │
└─────────────────────────────────────────────────────────────────┘
```

---

## 📁 Project Structure

```
Hackathon_Elastic_Search/
├── app/                          # Python backend
│   ├── api.py                    # FastAPI app — REST endpoints + WebSocket
│   ├── config.py                 # Centralized settings from .env
│   ├── elastic_client.py         # Elastic Agent Builder Converse API client
│   └── graph/                    # LangGraph orchestration
│       ├── graph.py              # StateGraph definition & routing logic
│       ├── nodes.py              # All agent node functions (1300+ lines)
│       └── state.py              # Typed state schema (SignalShieldState)
├── frontend/                     # React frontend (Vite)
│   ├── index.html                # Entry point
│   ├── vite.config.js            # Vite configuration
│   ├── package.json              # Dependencies & scripts
│   ├── public/                   # Static assets (hero image, favicon)
│   └── src/
│       ├── App.jsx               # React Router — routes & protected pages
│       ├── main.jsx              # App entry (React DOM render)
│       ├── index.css             # Global design system (15K+ lines CSS)
│       ├── context/
│       │   └── AuthContext.jsx   # Authentication context (localStorage)
│       └── pages/
│           ├── LandingPage.jsx   # Marketing landing page
│           ├── LandingPage.css   # Landing page styles
│           ├── AuthPage.jsx      # Login / Signup page
│           ├── AuthPage.css      # Auth page styles
│           ├── Dashboard.jsx     # Main chat dashboard (860 lines)
│           └── Dashboard.css     # Dashboard styles (33K design system)
├── data/                         # Data generation scripts
│   ├── generate_faers_data.py    # 500K synthetic FAERS reports generator
│   ├── generate_knowledge_base.py# RAG knowledge base (drug labels, guidelines)
│   ├── index_mappings.json       # Elasticsearch index mappings
│   ├── sample_faers.json         # Sample data for reference
│   └── preview_data.py           # Data preview utility
├── agent_config/                 # Elastic Agent Builder definitions
│   ├── agents.json               # 4 agent definitions with instructions
│   └── tools.json                # 11 ES|QL tool definitions
├── setup/
│   └── setup_agents.py           # Registers agents & tools to Kibana
├── tests/
│   └── test_scenarios.py         # Comprehensive scenario test suite
├── .github/workflows/
│   └── docker-ci.yml             # GitHub Actions — Docker build & test
├── Dockerfile                    # Multi-stage Docker build (Node + Python)
├── requirements.txt              # Python dependencies
├── .env                          # Environment variables (git-ignored)
├── .gitignore                    # Git ignore rules
├── .dockerignore                 # Docker build ignore rules
└── LICENSE                       # MIT License
```

---

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+
- [Elastic Cloud Serverless trial](https://cloud.elastic.co/registration?cta=agentbuilderhackathon)
- [Groq API key](https://console.groq.com/) (free tier available)

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

Create a `.env` file in the project root with your credentials:

```env
# ── Elastic Cloud Serverless ──────────────────────────
ELASTICSEARCH_URL=https://<your-project>.es.<region>.elastic.cloud:443
ELASTICSEARCH_API_KEY=<your-es-api-key>

KIBANA_URL=https://<your-project>.kb.<region>.elastic.cloud:443
KIBANA_API_KEY=<your-kibana-api-key>

# ── LLM (Groq — hardware-accelerated inference) ──────
GROQ_API_KEY=<your-groq-api-key>
GROQ_MODEL=llama-3.3-70b-versatile

# ── App Settings ─────────────────────────────────────
LOG_LEVEL=INFO
FAERS_RECORD_COUNT=500000
```

### 3. Generate Data & Knowledge Base

Generate the 500K synthetic FAERS reports (contains hidden safety signals):
```bash
python -m data.generate_faers_data --es-url $ELASTICSEARCH_URL --api-key $ELASTICSEARCH_API_KEY --count 500000
```

Generate the RAG Semantic Knowledge Base:
```bash
python -m data.generate_knowledge_base --es-url $ELASTICSEARCH_URL --api-key $ELASTICSEARCH_API_KEY
```

### 4. Register Agents & Tools

Deploys the 4 agents and 11 ES|QL tools to your Elastic Kibana instance:
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

## 🐳 Docker Deployment

The application ships with a multi-stage `Dockerfile` that builds the React frontend and serves it alongside the FastAPI backend:

```bash
# Build the image
docker build -t signalshield-app .

# Run the container
docker run -p 8000:8000 --env-file .env signalshield-app
```

Open **[http://localhost:8000](http://localhost:8000)** — the compiled frontend is served from the same port.

A **GitHub Actions** CI pipeline (`.github/workflows/docker-ci.yml`) automatically builds and tests the Docker image on every push to `main`.

---

## 🔌 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/health` | System health check (Kibana connectivity, agent count) |
| `POST` | `/api/investigate` | Trigger a multi-agent investigation (accepts `query` and `conversation_history`) |
| `GET` | `/api/investigations` | List all investigations |
| `GET` | `/api/investigations/{id}` | Get full investigation details |
| `GET` | `/api/signals` | List all detected safety signals |
| `GET` | `/api/reports` | List all generated safety reports |
| `GET` | `/api/reports/{id}/{drug}` | Get a specific safety report |
| `WS` | `/ws/progress/{id}` | WebSocket for real-time investigation progress streaming |

---

## 🧪 Running the Test Suite

The comprehensive scenario test validates routing, RAG accuracy, pipelines, and WebSockets.

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

## 🛠 Tech Stack

| Layer | Technology |
|-------|-----------|
| **LLM** | Groq (Llama 3.3 70B Versatile) — hardware-accelerated inference |
| **Search & Storage** | Elasticsearch Cloud Serverless + ELSER v2 Semantic Search |
| **Agent Framework** | Elastic Agent Builder (Kibana Converse API) |
| **Orchestration** | LangGraph StateGraph (deterministic multi-agent routing) |
| **Backend** | FastAPI + Uvicorn + WebSockets |
| **Frontend** | React 19 + Vite 7 + React Router 7 |
| **Styling** | Custom CSS design system (glassmorphism, dark mode, micro-animations) |
| **PDF Generation** | html2canvas + jsPDF |
| **CI/CD** | GitHub Actions + Docker (multi-stage build) |
| **Data Generation** | Faker + custom signal generators |

---

## 🏆 Hackathon Features Delivered

- ✅ **Elastic Agent Builder Integration**: 4 bespoke agents natively deployed to Kibana.
- ✅ **ES\|QL Mastery**: 11 complex parameterized queries computing relative time windows, distributions, and cross-tabulations.
- ✅ **Vector & Semantic Search (ELSER)**: Complete RAG implementation for complex domain knowledge.
- ✅ **Multi-Agent Orchestration**: LangGraph state machine with deterministic LLM routing across 7 distinct routes.
- ✅ **Agent Transparency UI**: Custom React frontend visualizing every API request, ES\|QL query, and tool invocation in real-time.
- ✅ **Conversational AI**: Full chat history support for natural follow-up questions across sessions.
- ✅ **Premium Full-Stack UI**: Landing page, authentication, glassmorphism dashboard with PDF export.
- ✅ **Docker & CI/CD**: Multi-stage Docker build with GitHub Actions automated testing.
- ✅ **Resilience**: Automated Python testing suite & fault-tolerant agent fallback routines.

---

## 📜 License
[MIT License](LICENSE)
