# Stage 1: builder
FROM python:3.12-slim AS builder
WORKDIR /build
# Install build deps
RUN apt-get update && apt-get install -y --no-install-recommends build-essential
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: runtime
FROM python:3.12-slim AS runtime

# Create non-root user
RUN groupadd -r appgroup && useradd -r -g appgroup -u 1000 appuser

WORKDIR /app

# Copy installed packages
COPY --from=builder /root/.local /home/appuser/.local
COPY --chown=appuser:appgroup . .

# Create logs and pulse directories with correct ownership before switching to non-root user
RUN mkdir -p /app/logs /home/appuser/.config/pulse && chown -R appuser:appgroup /app/logs /home/appuser/.config

# Runtime deps (audio libs for piper/whisper in Phase 4)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsndfile1 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

USER appuser
ENV PYTHONPATH=/app
ENV PATH=/home/appuser/.local/bin:$PATH
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD python -c "import httpx; httpx.get('http://localhost:8000/health').raise_for_status()"

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
