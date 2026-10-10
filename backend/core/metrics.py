from prometheus_client import Counter, Gauge, Histogram

REQUEST_COUNT = Counter("http_requests_total", "Total HTTP requests", ["method", "endpoint", "status"])
REQUEST_DURATION = Histogram("http_request_duration_seconds", "HTTP request duration", ["method", "endpoint"])
ACTIVE_CALLS = Gauge("active_calls_total", "Currently active AI calls")
CALL_DURATION = Histogram("call_duration_seconds", "Call duration in seconds")
STT_LATENCY = Histogram("stt_latency_seconds", "STT processing latency")
LLM_LATENCY = Histogram("llm_first_token_seconds", "LLM first token latency")
TTS_LATENCY = Histogram("tts_latency_seconds", "TTS generation latency")
DNC_BLOCKS = Counter("dnc_blocks_total", "Total DNC-blocked call attempts", ["reason"])
OPT_OUTS = Counter("opt_outs_total", "Total opt-out events")
