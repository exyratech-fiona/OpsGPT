#!/usr/bin/env bash
# One-time setup: create .env with strong random secrets. Won't overwrite an
# existing .env.
set -euo pipefail
cd "$(dirname "$0")"

if [ -f .env ]; then
  echo ".env already exists — leaving it untouched. Delete it first to regenerate."
  exit 0
fi

JWT=$(openssl rand -hex 32)
ADMPW=$(openssl rand -base64 18 | tr -d '/+=' | cut -c1-20)

cp .env.example .env
sed -i '' "s|^OPSGPT_JWT_SECRET=.*|OPSGPT_JWT_SECRET=${JWT}|" .env
sed -i '' "s|^OPSGPT_ADMIN_PASSWORD=.*|OPSGPT_ADMIN_PASSWORD=${ADMPW}|" .env

echo "Created .env with generated secrets."
echo
echo "  Admin login:  admin@opsgpt.local  /  ${ADMPW}"
echo
echo "IMPORTANT: edit .env and set DOCKERHUB_USER to the account the images were"
echo "pushed to, and MODEL_FILE to your GGUF filename in ./models."
echo
echo "Then:  docker compose up -d   and open http://localhost:8000/api/docs"
