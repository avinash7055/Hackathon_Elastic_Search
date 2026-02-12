# PharmaVigil AI 💊🔍

**Autonomous Drug Safety Signal Detection** — Multi-agent pharmacovigilance system that detects, investigates, and reports on emerging drug safety signals using FDA FAERS data.

> Built for the [Elasticsearch Agent Builder Hackathon](https://www.elastic.co/campaigns/agent-builder-hackathon)

---

## 🎯 The Problem

Pharmacovigilance — monitoring drugs for adverse effects after market approval — is a **$5 billion/year** industry that still relies on manual review. Dangerous signals can go undetected for **months to years**, putting patients at risk.

- 800,000+ adverse event reports filed annually in the US alone
- Manual review cycles take **2-6 weeks** per signal
- Critical drug interactions are buried in millions of records

## 💡 The Solution

PharmaVigil AI deploys **3 specialized agents** that autonomously:

1. **🔍 Signal Scanner** — Scans FAERS data for statistical anomalies (PRR, temporal spikes)
2. **🔬 Case Investigator** — Deep-dives into demographics, drug interactions, severity, geography
3. **📋 Safety Reporter** — Generates FDA MedWatch-style safety assessment reports

**Result: 3 weeks → 30 seconds.** From raw adverse event data to actionable safety report.

---

## 🏗 Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Elastic Cloud Serverless                                │
│  ┌──────────────────────────────────────────────┐       │
│  │  Elasticsearch: 500K+ FAERS Records         │       │
│  └──────────────────────────────────────────────┘       │
│  ┌──────────────────────────────────────────────┐       │
│  │  Agent Builder                                │       │
│  │  • signal_scanner (3 ES|QL tools)            │       │
│  │  • case_investigator (4 ES|QL tools)         │       │
│  │  • safety_reporter (3 ES|QL tools)           │       │
│  └──────────┬───────────────────────────────────┘       │
│             │ Converse API                               │
└─────────────┼───────────────────────────────────────────┘
              │
┌─────────────┼───────────────────────────────────────────┐
│  External Application                                    │
│  ┌──────────▼───────────────────────┐                   │
│  │  LangGraph StateGraph            │                   │
│  │  scan → investigate → report     │                   │
│  │  (conditional routing)           │                   │
│  └──────────┬───────────────────────┘                   │
│  ┌──────────▼───────────────────────┐                   │
│  │  FastAPI Backend                  │                   │
│  │  REST + WebSocket                 │                   │
│  └──────────┬───────────────────────┘                   │
│  ┌──────────▼───────────────────────┐                   │
│  │  React Dashboard                  │                   │
│  │  Signal Timeline · Reports · KPIs │                   │
│  └──────────────────────────────────┘                   │
└─────────────────────────────────────────────────────────┘
```

### Key Technologies

| Component | Technology |
|---|---|
| Agent Logic | Elastic Agent Builder (custom agents + ES|QL tools) |
| Data Store | Elasticsearch Serverless |
| Query Language | ES|QL (8 custom parameterized queries) |
| Orchestration | LangGraph StateGraph |
| Backend API | FastAPI + WebSocket |
| Frontend | React 18 + Recharts |
| Data Source | Synthetic FDA FAERS data (500K+ records) |

---

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- [Elastic Cloud Serverless trial](https://cloud.elastic.co/registration?cta=agentbuilderhackathon)

### 1. Clone & Install

```bash
git clone https://github.com/yourusername/pharmavigil-ai.git
cd pharmavigil-ai

# Python dependencies
python -m venv venv
venv\Scripts\activate  # Windows
pip install -r requirements.txt

# Frontend dependencies
cd frontend && npm install && cd ..
```

### 2. Configure

```bash
copy .env.example .env
# Edit .env with your Elastic Cloud credentials:
# ELASTICSEARCH_URL, ELASTICSEARCH_API_KEY
# KIBANA_URL, KIBANA_API_KEY
```

### 3. Generate FAERS Data

```bash
python -m data.generate_faers_data --es-url %ELASTICSEARCH_URL% --api-key %ELASTICSEARCH_API_KEY% --count 500000
```

### 4. Register Agents & Tools

```bash
python -m setup.setup_agents --kibana-url %KIBANA_URL% --api-key %KIBANA_API_KEY%
```

### 5. Run

```bash
# Backend (terminal 1)
uvicorn app.api:app --reload --port 8000

# Frontend (terminal 2)
cd frontend && npm run dev
```

Open [http://localhost:3000](http://localhost:3000) and click **Start Investigation**.

---

## 📊 What It Detects

The synthetic dataset includes 3 embedded safety signals:

| Signal | Drug | Reaction | Pattern |
|---|---|---|---|
| 1 | **Cardizol-X** | Cardiac arrhythmia | 4x spike in last 90 days |
| 2 | **Neurofen-Plus** | Hepatotoxicity | Rising trend in 65+ females |
| 3 | **Arthrex-200** | Rhabdomyolysis | Drug interaction with statins |

---

## 📃 Custom ES|QL Tools

| Tool | What It Does |
|---|---|
| `pharma.scan_adverse_event_trends` | Time-bucketed event counts per drug |
| `pharma.calculate_reporting_ratio` | PRR disproportionality score |
| `pharma.detect_temporal_spike` | Recent vs baseline rate comparison |
| `pharma.analyze_patient_demographics` | Age/sex/weight breakdown |
| `pharma.find_concomitant_drugs` | Co-reported drug frequency |
| `pharma.check_outcome_severity` | Death/hospitalization/disability counts |
| `pharma.geo_distribution` | Country-level event distribution |
| `pharma.compile_signal_summary` | Comprehensive signal profile |

---

## 📜 License

[MIT License](LICENSE)

---

## 🏆 Hackathon

Built for the [Elasticsearch Agent Builder Hackathon](https://www.elastic.co/campaigns/agent-builder-hackathon) — demonstrating how multi-agent AI can transform drug safety monitoring from weeks to seconds.
