#!/bin/bash
set -euo pipefail
for port in 3000 8001; do
  pids="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
  if [ -n "$pids" ]; then echo "$pids" | xargs kill 2>/dev/null || true; fi
done
echo "CLEAR NASDAQ local frontend/backend stopped. Ollama was left untouched."
