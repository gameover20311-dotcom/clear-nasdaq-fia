#!/bin/bash

ROOT="$HOME/ClearNasdaq/clear_nasdaq_fia-2"
LOGS="$ROOT/runtime_logs"
SCHEME="http"
BACKEND="$SCHEME://127.0.0.1:8001"

while true; do

  TMP="$LOGS/.forecast.tmp"

  if curl -fsS --max-time 60 \
      "$BACKEND/api/forecast" \
      > "$TMP"; then
      mv "$TMP" "$LOGS/public_forecast.json"
  else
      rm -f "$TMP"
  fi

  TMP="$LOGS/.liquidity.tmp"

  if curl -fsS --max-time 60 \
      "$BACKEND/api/liquidity" \
      > "$TMP"; then
      mv "$TMP" "$LOGS/public_liquidity.json"
  else
      rm -f "$TMP"
  fi

  sleep 30
done
