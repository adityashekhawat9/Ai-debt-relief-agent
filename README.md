# AI Voice Platform — Debt Relief AI

<div align="center">

![Phase](https://img.shields.io/badge/Phase-3%20Complete-blue?style=for-the-badge)
![Status](https://img.shields.io/badge/Status-Production--Ready-brightgreen?style=for-the-badge)
![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-19-61DAFB?style=for-the-badge&logo=react&logoColor=black)
![LiveKit](https://img.shields.io/badge/LiveKit-WebRTC%20%2F%20SIP-002B36?style=for-the-badge)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=for-the-badge&logo=docker&logoColor=white)
![Compliance](https://img.shields.io/badge/TCPA%20%2F%20TSR-Compliant-success?style=for-the-badge)

<p align="center">
  <strong>An ultra-low latency, full-duplex conversational AI voice agent engineered for autonomous outbound and inbound debt relief qualification.</strong>
</p>

</div>

---

## 📖 Overview

The **AI Voice Platform** is a production-grade, headless conversational voice agent designed specifically for financial services and debt relief programs. The platform dynamically navigates phone conversations, handles complex objections with contextual memory, detects customer opt-outs, qualifies lead financial thresholds, and delivers structured qualification data directly into **Olivia LMS** or any modern CRM via an event-driven webhook architecture.

Equipped with **sub-500ms voice-to-voice response times**, real-time barge-in interruption handling, conversational backchanneling, and multi-provider fallback, this system provides human-parity phone engagement while strictly enforcing compliance regulations.

---

## ✨ Key Features

- **⚡ Sub-500ms Voice Pipeline**: Streaming pipeline spanning Silero VAD, streaming STT, semantic chunking, and streaming TTS for immediate conversational response.
- **🗣️ Natural Human Interruption (Barge-In)**: Instant cancellation of AI speech playback when the customer speaks, accompanied by low-latency backchannels (*"uh-huh"*, *"gotcha"*, *"makes sense"*).
- **🧠 LangGraph State Machine Orchestrator**: Deterministic conversation flow control guaranteeing step-by-step qualification while allowing dynamic branching for objection handling and FAQs.
- **🛡️ TCPA / TSR Regulatory Compliance Gate**: Built-in Federal DNC / State DND list checking, calling hour validation (8:00 AM - 9:00 PM local recipient time), and immediate conversational opt-out detection.
- **🔄 Multi-Provider AI Fallback**:
  - **LLM**: Cloud orchestration (Groq, OpenRouter, Anthropic Claude, Google Gemini) with local fallback support (Qwen 2.5 / 3 via GGUF).
  - **STT**: Deepgram Nova-2 streaming WebSocket & Whisper.
  - **TTS**: Deepgram Aura, Cartesia Sonic, ElevenLabs, and offline Piper ONNX fallback.
- **📞 Dual Telephony Stack**:
  - **LiveKit WebRTC & SIP**: Native WebRTC cloud worker for browser testing and SIP trunking.
  - **Asterisk AMI/ARI & AudioSocket**: Native Asterisk PBX bridging with Vicidial campaign disposition syncing.
- **📊 Event-Driven CRM Synchronization**: Single-webhook payload dispatching qualification answers, call sentiment, dispositions, and complete transcripts upon call completion.
- **🧪 Browser Audio Sandbox**: Built-in React + Vite frontend with real-time mic streaming, audio waveform visualizer, FSM state indicators, and live transcripts.
- **📈 Comprehensive Observability**: Pre-configured Prometheus metrics exporter, Grafana dashboards, and Loki structured log collection.

---

## 🏗️ Architecture & Data Flow

```mermaid
flowchart TD
    subgraph Telephony["📞 Telephony & Ingestion"]
        PSTN["PSTN / SIP Trunk"] --> Asterisk["Asterisk / Vicidial (AudioSocket / AMI)"]
        Browser["Web Client (Browser Test)"] --> LiveKit["LiveKit WebRTC / SIP"]
    end

    subgraph AudioEngine["⚡ Streaming Audio Pipeline"]
        VAD["Silero VAD & Barge-in Detector"]
        STT["Streaming STT (Deepgram Nova-2 / Whisper)"]
        TTS["Streaming TTS (Deepgram Aura / Cartesia / ElevenLabs / Piper)"]
    end

    subgraph Core["🧠 AI Brain & Orchestration"]
        Orchestrator["Call Orchestrator & Session Manager"]
        FSM["LangGraph Dialogue FSM"]
        RAG["Qdrant Vector DB (Knowledge Base)"]
        LLM["LLM Engine (Groq / OpenRouter / Claude / Qwen)"]
        Compliance["Compliance Gate (DNC & Calling Hours)"]
    end

    subgraph Persistence["💾 Storage & State"]
        PG[("PostgreSQL\nCalls, Leads, Transcripts")]
        Redis[("Redis\nState & Sessions")]
    end

    subgraph Integration["🔗 Downstream Systems"]
        Webhook["Olivia LMS / CRM Webhook\n(/api/webhooks/ai-voice)"]
        Grafana["Prometheus + Grafana + Loki"]
    end

    PSTN --> Asterisk
    Asterisk --> VAD
    Browser --> LiveKit
    LiveKit --> VAD

    VAD --> STT
    STT --> Orchestrator
    Orchestrator --> Compliance
    Compliance --> FSM
    FSM <--> RAG
    FSM <--> LLM
    FSM --> TTS
    TTS --> LiveKit
    TTS --> Asterisk

    Orchestrator --> PG
    Orchestrator --> Redis
    Orchestrator -. Call Ended .-> Webhook
    Orchestrator -. Metrics & Logs .-> Grafana
```

---

## 📁 Repository Structure

```text
├── backend/
│   ├── api/                     # FastAPI endpoints (calls, leads, analytics, knowledge)
│   │   ├── routers/             # Modular API route definitions
│   │   ├── dependencies.py      # Dependency injection (Auth, DB, Redis)
│   │   └── main.py              # Application entrypoint & lifespan lifecycle
│   ├── assets/backchannels/     # Pre-rendered raw PCM audio backchannel clips
│   ├── browser_test/            # WebSocket bridge for browser audio playground
│   ├── conversation_engine/     # LangGraph dialogue FSM, prompts & checkpointers
│   ├── core/                    # Security, logging, metrics, config settings
│   ├── database/                # SQLAlchemy async sessions & Alembic migrations
│   ├── models/                  # Database models (PostgreSQL) and Pydantic schemas
│   ├── services/
│   │   ├── ai/                  # LLM, STT, TTS, VAD, and RAG service abstractions
│   │   ├── compliance/          # DNC check, TCPA calling hours, compliance gate
│   │   ├── rag/                 # Qdrant client, chunking and embedding pipelines
│   │   └── telephony/           # Asterisk AMI/ARI, AudioSocket, Vicidial sync
│   ├── telephony/               # LiveKit worker agent implementation
│   ├── tests/                   # Pytest unit, integration, and flow tests
│   └── Dockerfile               # Backend container definition
├── frontend/                    # React 19 + TypeScript + Vite audio testing client
│   ├── src/pages/BrowserTest.tsx # Interactive mic testing studio with real-time waveform
│   └── Dockerfile               # Frontend container definition
├── infrastructure/
│   ├── docker/                  # Docker Compose setups (core, dev, monitoring)
│   ├── monitoring/              # Grafana dashboards, Prometheus and Loki configs
│   └── nginx/                   # Nginx reverse proxy configuration
├── docs/                        # Architecture guides, Asterisk setup guides
├── scripts/                     # Shell & PowerShell model download utilities
├── Makefile                     # Developer productivity automation commands
├── .env.example                 # Environment configuration template
└── README.md                    # Platform documentation
```

---

## 🚀 Quick Start

### 1. Prerequisites
- [Docker](https://www.docker.com/) & Docker Compose (v2.20+)
- Python 3.11+ (for local development)
- Node.js 18+ (for frontend development)

### 2. Configure Environment Variables
Copy the template configuration file:
```bash
cp .env.example .env
```
Edit `.env` with your API credentials and endpoints (see [Configuration Guide](#-configuration--environment-variables)).

### 3. Start via Docker Compose (Recommended)
Launch the complete stack (API, PostgreSQL, Redis, Qdrant, Nginx, and Frontend):
```bash
make dev
```
To also launch the monitoring stack (Prometheus, Grafana, Loki, Promtail):
```bash
make monitoring
```

Once running:
- **FastAPI Documentation**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Browser Audio Test Studio**: [http://localhost:3005](http://localhost:3005)
- **Grafana Dashboard**: [http://localhost:3001](http://localhost:3001) (`admin` / `admin`)
- **API Health Check**: [http://localhost:8000/health](http://localhost:8000/health)

---

## 🛠️ Local Development Setup

If running directly without Docker:

### Backend
```bash
cd backend

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: .\venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run database migrations
alembic -c database/migrations/alembic.ini upgrade head

# Start FastAPI dev server
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
```

### Frontend
```bash
cd frontend

# Install dependencies
npm install

# Start Vite dev server
npm run dev
```

---

## ⚙️ Configuration & Environment Variables

| Variable | Description | Default / Example |
|---|---|---|
| **Application** | | |
| `APP_ENV` | Application environment (`development`, `production`) | `development` |
| `LOG_LEVEL` | Log verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`) | `INFO` |
| `PUBLIC_APP_URL` | Public tunnel / domain for webhook callbacks | `example.trycloudflare.com` |
| **Databases** | | |
| `DATABASE_URL` | Async PostgreSQL connection string | `postgresql+asyncpg://aicalls:changeme@postgres:5432/aicalls` |
| `REDIS_URL` | Redis connection URL | `redis://redis:6379/0` |
| `QDRANT_URL` | Qdrant vector database URL | `http://qdrant:6333` |
| **AI Providers** | | |
| `USE_CLOUD_LLM` | Enable cloud LLM routing | `true` |
| `GROQ_API_KEY` | Groq API Key (high-speed inference) | `gsk_...` |
| `OPENROUTER_API_KEY`| OpenRouter API Key (fallback models) | `sk-or-v1-...` |
| `ANTHROPIC_API_KEY` | Anthropic Claude API Key | `sk-ant-...` |
| `DEEPGRAM_API_KEY`  | Deepgram Speech-to-Text & Aura TTS | `...` |
| `CARTESIA_API_KEY`  | Cartesia Sonic low-latency TTS | `sk_car_...` |
| `ELEVENLABS_API_KEY`| ElevenLabs conversational voice synthesis | `sk_...` |
| **Telephony** | | |
| `LIVEKIT_URL` | LiveKit Cloud or self-hosted WebSocket URL | `wss://project.livekit.cloud` |
| `LIVEKIT_API_KEY` | LiveKit API Key | `...` |
| `LIVEKIT_API_SECRET`| LiveKit API Secret | `...` |
| `TRANSFER_EXTENSION`| PBX extension for qualified agent handoff | `90009` |
| **Integrations** | | |
| `DATA_WEBHOOK_URL` | Target CRM/LMS webhook endpoint | `https://crm.cloud/api/webhooks/ai-voice` |
| `VICIDIAL_URL` | Vicidial PBX host URL | `http://vicidial` |

---

## 🔗 CRM & LMS Webhook Integration

When a call completes, the AI packaging worker dispatches an event-driven JSON payload to the URL configured in `DATA_WEBHOOK_URL`:

```json
{
  "vicidial_lead_id": "981245",
  "phone": "+15552345678",
  "ai_disposition": "SALE",
  "call_duration_seconds": 184,
  "sentiment": "positive",
  "collected_data": {
    "total_debt": 24500,
    "debt_type": "credit_card",
    "employment_status": "employed",
    "monthly_income": 4200,
    "hardship_reason": "medical_bills"
  },
  "metrics": {
    "total_turns": 8,
    "objections_handled": 1,
    "interruptions_detected": 2,
    "average_latency_ms": 420
  },
  "full_transcript": [
    {"speaker": "ai", "text": "Hi, this is Alex with the Consumer Debt Relief program. Am I speaking with Jordan?"},
    {"speaker": "user", "text": "Yes, who is this?"},
    {"speaker": "ai", "text": "I'm following up on an inquiry regarding options to consolidate and reduce unsecured debts..."}
  ]
}
```

---

## 🤖 Conversation State Machine (LangGraph)

The dialogue flow is managed via a state graph that guarantees deterministic business compliance:

```mermaid
stateDiagram-v2
    [*] --> Greeting
    Greeting --> DiscloseIdentity: Customer Responds
    DiscloseIdentity --> QualificationCheck: Acknowledged
    
    state QualificationCheck {
        [*] --> CheckDebtAmount
        CheckDebtAmount --> CheckEmployment: Debt >= $10,000
        CheckEmployment --> Qualified: Meets Thresholds
        CheckDebtAmount --> Unqualified: Debt < $10,000
    }

    QualificationCheck --> ObjectionHandling: Customer Hesitates / Objects
    ObjectionHandling --> QualificationCheck: Objection Resolved
    ObjectionHandling --> PoliteExit: Max Objections Exceeded (> 2)

    QualificationCheck --> WarmTransfer: Lead Qualified
    QualificationCheck --> OptOut: Customer Requests DNC / Stop

    WarmTransfer --> FinalDisposition
    Unqualified --> FinalDisposition
    PoliteExit --> FinalDisposition
    OptOut --> FinalDisposition

    FinalDisposition --> WebhookSync
    WebhookSync --> [*]
```

---

## 📜 Makefile Command Reference

| Command | Action |
|---|---|
| `make dev` | Start all core services in background with hot reloading |
| `make dev-down` | Stop and tear down development containers |
| `make prod` | Run production compose bundle with optimized flags |
| `make monitoring` | Launch Prometheus, Grafana, Loki, and Promtail |
| `make migrate` | Execute pending Alembic database migrations |
| `make migrate-down` | Roll back the latest database migration |
| `make test` | Run complete Pytest test suite with code coverage |
| `make lint` | Run Ruff linter and MyPy type checker |
| `make logs` | Stream live tail logs from all Docker containers |
| `make health` | Query backend health status JSON endpoint |
| `make clean` | Stop containers and prune all volumes & local images |

---

## ⚖️ Regulatory Compliance & TCPA Notice

This platform includes technical safeguards for TCPA (Telephone Consumer Protection Act) and TSR (Telemarketing Sales Rule):

1. **Calling Hours Validation**: Outbound calls are automatically blocked outside 8:00 AM – 9:00 PM local recipient timezone.
2. **Immediate Opt-Out Detection**: Natural language triggers (*"stop calling me"*, *"remove my number"*, *"put me on the do not call list"*) trigger an immediate hangup, mark the record in the local DNC database, and dispatch DNC dispositions to the CRM.
3. **Disclosure Statements**: Initial turn includes caller identity and purpose disclosure.

> **Disclaimer**: Operators are solely responsible for ensuring adherence to federal, state, and local regulations, including maintaining active Federal DNC Registry subscriptions.

---

## 📄 License

Proprietary & Confidential. All rights reserved. Built for enterprise debt relief operations.
