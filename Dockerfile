# --- Build stage: install dependencies into an isolated virtualenv ---
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install -r requirements.txt

# --- Final stage: minimal runtime, non-root ---
FROM python:3.12-slim

# Create an unprivileged user — containers must never run as root.
RUN groupadd --system app && useradd --system --gid app --no-create-home app

# Copy only the prebuilt venv from the builder (no build tooling in final image).
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app
COPY app/ ./app/

USER app
EXPOSE 8000

# Liveness/readiness are wired to K8s probes; this HEALTHCHECK helps local runs.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
