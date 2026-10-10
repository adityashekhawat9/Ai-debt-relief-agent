from datetime import date
from pydantic import BaseModel

class DailyCallStats(BaseModel):
    date: date
    total_calls: int
    answered_calls: int
    qualified_leads: int
    transfers: int
    opt_outs: int
    avg_duration_seconds: float
    call_abandonment_rate: float

class OutcomeBreakdown(BaseModel):
    outcome: str
    count: int
    percentage: float

class LatencyMetrics(BaseModel):
    vad_p50_ms: float
    vad_p95_ms: float
    stt_p50_ms: float
    stt_p95_ms: float
    llm_first_token_p50_ms: float
    llm_first_token_p95_ms: float
    tts_p50_ms: float
    tts_p95_ms: float
    end_to_end_p50_ms: float
    end_to_end_p95_ms: float

class DashboardSummary(BaseModel):
    active_calls: int
    calls_today: int
    qualified_today: int
    transfers_today: int
    dnc_blocks_today: int
    compliance_rate: float
    latency: LatencyMetrics
