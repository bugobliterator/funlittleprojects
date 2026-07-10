#!/bin/bash
# Misuse response: redirect every connected client away (rickroll by default),
# give the pages a moment to navigate, then kill the relay server.
#
# Env: RELAY_PORT (default 8420), RICKROLL_URL (default: the classic)
set -u
PORT="${RELAY_PORT:-8420}"
URL="${RICKROLL_URL:-https://www.youtube.com/watch?v=dQw4w9WgXcQ}"

curl -s -X POST "http://127.0.0.1:${PORT}/redirect" \
  -H 'Content-Type: application/json' -d "{\"url\":\"${URL}\"}" >/dev/null \
  && echo "redirect armed -> ${URL}"

sleep 4   # let connected pages poll (1.5s cadence) and navigate away before kill
lsof -ti:"${PORT}" 2>/dev/null | xargs kill 2>/dev/null || true
echo "relay on :${PORT} shut down"
