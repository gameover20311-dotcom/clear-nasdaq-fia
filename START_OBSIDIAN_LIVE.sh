#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
LOGS="$ROOT/logs"
mkdir -p "$LOGS"

PY="$BACKEND/.venv/bin/python"
if [ ! -x "$PY" ]; then PY="$(command -v python3 || true)"; fi
if [ -z "${PY:-}" ]; then echo "ERROR: Python 3 not found"; exit 1; fi

stop_port() {
  local port="$1"
  local pids
  pids="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
  if [ -n "$pids" ]; then
    echo "$pids" | xargs kill 2>/dev/null || true
    sleep 2
  fi
}

wait_http() {
  local url="$1"; local want="$2"; local seconds="$3"; local i code
  for ((i=0;i<seconds;i++)); do
    code="$(curl -s -o /dev/null -w '%{http_code}' "$url" 2>/dev/null || true)"
    if [ "$code" = "$want" ]; then return 0; fi
    sleep 1
  done
  return 1
}

# Ollama is part of the actual Brain contract. Do not fake it.
if ! curl -fsS --max-time 3 http://127.0.0.1:11434/api/tags >/tmp/clear_nasdaq_ollama_tags.json 2>/dev/null; then
  if command -v ollama >/dev/null 2>&1; then
    nohup ollama serve >"$LOGS/ollama.log" 2>&1 &
    for _ in $(seq 1 20); do
      curl -fsS --max-time 2 http://127.0.0.1:11434/api/tags >/tmp/clear_nasdaq_ollama_tags.json 2>/dev/null && break
      sleep 1
    done
  fi
fi
if ! test -s /tmp/clear_nasdaq_ollama_tags.json; then
  echo "ERROR: Ollama is not reachable on 127.0.0.1:11434"
  exit 1
fi
if ! "$PY" - <<'PY'
import json
p='/tmp/clear_nasdaq_ollama_tags.json'
d=json.load(open(p))
models=[str(x.get('name') or x.get('model') or '') for x in d.get('models',[]) if isinstance(x,dict)]
raise SystemExit(0 if 'gpt-oss:20b' in models else 1)
PY
then
  echo "ERROR: exact model gpt-oss:20b is not installed. No fallback will be called LIVE."
  exit 1
fi

stop_port 8001
stop_port 3000

cd "$BACKEND"
nohup "$PY" -m uvicorn main:app --host 127.0.0.1 --port 8001 >"$LOGS/backend.log" 2>&1 &
echo $! > "$LOGS/backend.pid"
if ! wait_http "http://127.0.0.1:8001/api/health" "200" 60; then
  echo "ERROR: backend did not become healthy. See $LOGS/backend.log"
  tail -80 "$LOGS/backend.log" 2>/dev/null || true
  exit 1
fi
if ! wait_http "http://127.0.0.1:8001/api/auth/health" "200" 20; then
  echo "ERROR: auth service did not become READY. See $LOGS/backend.log"
  tail -80 "$LOGS/backend.log" 2>/dev/null || true
  exit 1
fi

if [ ! -d "$FRONTEND/.next" ]; then
  echo "ERROR: frontend production build missing. Run the Obsidian installer first."
  exit 1
fi
cd "$FRONTEND"
FIA_BACKEND_URL="${FIA_BACKEND_URL:-http://127.0.0.1:8001}" FIA_COOKIE_SECURE="${FIA_COOKIE_SECURE:-0}" \
  nohup npm run start -- --hostname 127.0.0.1 --port 3000 >"$LOGS/frontend.log" 2>&1 &
echo $! > "$LOGS/frontend.pid"
if ! wait_http "http://127.0.0.1:3000/login" "200" 60; then
  echo "ERROR: frontend did not become healthy. See $LOGS/frontend.log"
  tail -80 "$LOGS/frontend.log" 2>/dev/null || true
  exit 1
fi

ROOT_CODE="$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:3000/ || true)"
echo ""
echo "✅ CLEAR NASDAQ OBSIDIAN LIVE is running"
echo "Backend health : HTTP $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8001/api/health)"
echo "Auth health    : HTTP $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8001/api/auth/health)"
echo "Frontend login : HTTP $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:3000/login)"
echo "Protected /    : HTTP $ROOT_CODE (redirect/auth gate expected without session)"
echo "Model          : gpt-oss:20b FOUND"
echo ""
echo "Open: http://127.0.0.1:3000/login"
if command -v open >/dev/null 2>&1; then open "http://127.0.0.1:3000/login" >/dev/null 2>&1 || true; fi
