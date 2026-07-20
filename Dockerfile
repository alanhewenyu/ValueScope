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
    PYTHONUNBUFFERED=1 \
    MALLOC_ARENA_MAX=2

WORKDIR /app

# Copy application code
COPY modeling/ ./modeling/
COPY backend/  ./backend/

EXPOSE 8000

# gunicorn master + 1 uvicorn worker, recycled every ~2000 requests.
# Cache eviction bounds Python-object memory, but glibc heap fragmentation
# still grows RSS ~linearly under sustained crawler churn (2026-07-20 OOM:
# ~140MB/h to the 8GB kill). Recycling resets RSS; the master holds the
# listen socket so requests queue (not fail) during the ~5s worker swap.
# Single worker: in-memory caches stay unified and snapshot_scheduler
# runs once. Jitter avoids recycling at a predictable request count.
CMD ["gunicorn", "backend.main:app", \
     "-k", "uvicorn_worker.UvicornWorker", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "1", \
     "--max-requests", "2000", \
     "--max-requests-jitter", "200", \
     "--timeout", "180", \
     "--graceful-timeout", "45", \
     "--keep-alive", "5"]
