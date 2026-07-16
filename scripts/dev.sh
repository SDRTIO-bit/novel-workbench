#!/usr/bin/env bash
set -e

echo "Starting Novel Workbench..."

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
API_DIR="$SCRIPT_DIR/../apps/api"
WEB_DIR="$SCRIPT_DIR/../apps/web"

PYTHONPATH="$API_DIR" python -m uvicorn app.main:app --host 127.0.0.1 --port 8766 --reload &
API_PID=$!

echo "Backend starting on http://localhost:8766 ..."
echo "Frontend starting on http://localhost:8765 ..."

cd "$WEB_DIR"
npx vite --port 8765 &
WEB_PID=$!

trap "kill $API_PID $WEB_PID 2>/dev/null" EXIT
wait
