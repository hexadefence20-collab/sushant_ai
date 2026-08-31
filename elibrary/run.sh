#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"

if ! python3.12 -c "import fastapi,uvicorn" 2>/dev/null; then
  echo "installing deps..."
  python3.12 -m pip install -r requirements.txt
fi

exec python3.12 -m uvicorn app.main:app --host "$HOST" --port "$PORT" --proxy-headers