#!/bin/bash
# Start both backend (FastAPI) and frontend (Next.js) for local development.
# Usage: ./dev.sh

set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

echo "🎯 Starting ValueScope 2.0 development servers..."
echo ""

# Backend: FastAPI on port 8000
echo "📡 Starting FastAPI backend on http://localhost:8000"
# Use project venv if available, otherwise system python
if [ -f "$PROJECT_DIR/.venv/bin/python" ]; then
    PYTHON="$PROJECT_DIR/.venv/bin/python"
else
    PYTHON="python"
fi
# NOTE: --reload disabled because mini_racer (akshare dep) V8 engine crashes
# on fork. Use manual restart when backend code changes.
$PYTHON -m uvicorn backend.main:app --port 8000 &
BACKEND_PID=$!

# Frontend: Next.js on port 3000
# BACKEND_URL points the rewrite proxy at the local FastAPI; otherwise
# /api/* gets forwarded to the Railway production backend (per next.config.ts default).
echo "🌐 Starting Next.js frontend on http://localhost:3000"
cd frontend && BACKEND_URL=http://localhost:8000 npm run dev &
FRONTEND_PID=$!

cd "$PROJECT_DIR"

echo ""
echo "✅ Both servers starting..."
echo "   Backend:  http://localhost:8000/api/health"
echo "   Frontend: http://localhost:3000"
echo "   API docs: http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop both servers."

# Cleanup on exit
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; echo ''; echo 'Servers stopped.'" EXIT

wait
