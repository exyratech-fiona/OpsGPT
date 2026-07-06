#!/usr/bin/env bash
# Create an OpenAI-style API key (opsk_...) for calling /v1. Shown once — save it.
set -euo pipefail
cd "$(dirname "$0")"
[ -f .env ] && set -a && . ./.env && set +a

BASE="http://localhost:${API_PORT:-8000}"
JAR="$(mktemp)"
trap 'rm -f "$JAR"' EXIT

# log in as admin (sets an auth cookie), then create a key
curl -fsS -c "$JAR" -X POST "$BASE/api/auth/login" \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"${OPSGPT_ADMIN_EMAIL:-admin@opsgpt.local}\",\"password\":\"${OPSGPT_ADMIN_PASSWORD}\"}" >/dev/null

KEY=$(curl -fsS -b "$JAR" -X POST "$BASE/api/keys" \
  -H 'Content-Type: application/json' \
  -d '{"name":"client-key"}' \
  | python3 -c 'import sys,json;print(json.load(sys.stdin).get("key",""))')

if [ -z "$KEY" ]; then
  echo "Failed to create key. Is the stack up? (docker compose ps)"; exit 1
fi

echo "API key (save it now — it is shown only once):"
echo
echo "  $KEY"
echo
echo "Use it as a Bearer token, e.g.:"
echo "  curl $BASE/v1/models -H \"Authorization: Bearer $KEY\""
