#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Running backend tests..."
cd "$SCRIPT_DIR/../apps/api"
PYTHONPATH=. python -m pytest tests/ -v

echo "Running frontend tests..."
cd "$SCRIPT_DIR/../apps/web"
npx vitest run

echo "All tests passed."
