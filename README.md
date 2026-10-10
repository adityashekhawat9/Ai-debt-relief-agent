# AI Voice Platform — Debt Relief AI

![Phase](https://img.shields.io/badge/Phase-3-blue) ![Status](https://img.shields.io/badge/Status-Active-brightgreen) ![License](https://img.shields.io/badge/License-Proprietary-red)

A production-grade AI outbound calling platform tailored specifically for debt relief services. The system operates as a headless AI agent that dynamically navigates phone conversations, handles objections, gathers intelligence, and integrates seamlessly into **Olivia LMS** via an Event-Driven architecture.

## 🏗️ Architecture

The platform is built on an incredibly fast, highly scalable microservices architecture:

- **AI Orchestrator**: The "Brain" of the platform, utilizing LangGraph for dynamic state machine management (handling objections, script flow, and conversational logic).
- **LiveKit WebRTC / SIP**: Direct LiveKit integration. The AI manages high-fidelity, ultra-low latency audio streaming natively over WebRTC and SIP.
- **LLM Engine**: Inference engine powered by Qwen.
- **STT & TTS Pipelines**: Lightning-fast streaming Speech-to-Text and Text-to-Speech handling natural human interruptions (barge-in) and semantic chunking.
- **Event-Driven Webhook Sync**: The AI operates entirely headless. When a call drops or finishes, it packages the conversation intelligence into a single JSON payload and `POST`s it directly to the Olivia LMS Webhook (`/api/webhooks/ai-voice`).

## 🚀 Quick Start
```bash
# 1. Copy the environment template
cp .env.example .env  

# 2. Add your secret keys and Olivia LMS Webhook URL in .env
# DATA_WEBHOOK_URL="https://olivialms.cloud/api/webhooks/ai-voice"

# 3. Start the backend services
make dev              

# 4. Run the frontend UI
npm run dev
```

## 🔗 Single Webhook Integration
To integrate this AI with Olivia LMS (or any CRM), you only need to expose a single `POST` route on your backend. The AI will send the following payload when a call completes:

```json
{
  "vicidial_lead_id": "12345",
  "phone": "5551234567",
  "ai_disposition": "SALE",
  "collected_data": {
    "total_debt": 15000,
    "employment_status": "employed"
  }
}
```

## 🗺️ Phase Roadmap

| Phase | Description | Status |
|---|---|---|
| Phase 1 | Core Infrastructure & LiveKit Integration | ✅ Complete |
| Phase 2 | Advanced Conversation Handling (LangGraph, Interruptions) | ✅ Complete |
| Phase 3 | Event-Driven CRM Integration (Single Webhook) | ✅ Complete |
| Phase 4 | RAG Knowledge Base Integration | ⏳ Pending |
| Phase 5 | Frontend Analytics Dashboard | ⏳ Pending |
| Phase 6 | Redis Distributed State Management & Scalability | ⏳ Pending |
| Phase 7 | Meta/Instagram HRMS Workflow | ⏳ Pending |

## ⚖️ Compliance Notice
This system must be operated in accordance with TCPA, TSR, and all applicable federal and state laws regarding outbound calling. Always check against the Federal DNC and State DND lists before initiating calls.

## 🛠️ Tech Stack

| Category | Technology |
|---|---|
| **Backend** | Python, FastAPI, Node.js (Frontend) |
| **AI / ML** | LangGraph, Qwen (LLM), Whisper (STT), Piper (TTS) |
| **Telephony** | LiveKit WebRTC / SIP |
| **Integration** | Event-Driven JSON Webhooks |
| **Infrastructure** | Docker, Docker Compose |
