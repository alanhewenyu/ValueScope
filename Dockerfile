# ---- Build stage: install Python deps ----
FROM python:3.10-slim AS builder

WORKDIR /build

# Install build tools needed by some wheels (e.g. py_mini_racer, numpy)
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc g++ && \
    rm -rf /var/lib/apt/lists/*

COPY requirements-api.txt .

# Install all dependencies into a virtual-env so we can copy it cleanly
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements-api.txt

# ---- Runtime stage ----
FROM python:3.10-slim AS runtime

# Minimal runtime libs that py_mini_racer / pandas may need
RUN apt-get update && \
    apt-get install -y --no-install-recommends libstdc++6 && \
    rm -rf /var/lib/apt/lists/*

# Copy virtualenv from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Copy application code
COPY modeling/ ./modeling/
COPY backend/  ./backend/

EXPOSE 8000

# Run with 2 uvicorn workers (sufficient for current traffic).
# --max-requests 500: restart each worker after 500 requests to reclaim leaked memory.
# --max-requests-jitter 50: stagger restarts so not all workers restart simultaneously.
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--max-requests", "500", "--max-requests-jitter", "50"]
