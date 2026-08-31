#!/usr/bin/env bash
set -euo pipefail

# Resolve to an absolute path so startup is independent of the caller's CWD
# (Render may launch from the repo root rather than /elibrary).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"

# Guarantee the `app` package resolves as a regular package regardless of CWD.
export PYTHONPATH="$SCRIPT_DIR${PYTHONPATH:+:$PYTHONPATH}"

if ! python3.12 -c "import fastapi,uvicorn" 2>/dev/null; then
  echo "installing deps..."
  python3.12 -m pip install -r requirements.txt
fi

exec python3.12 -m uvicorn app.main:app --host "$HOST" --port "$PORT" --proxy-headers