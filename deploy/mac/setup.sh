#!/usr/bin/env bash
# One-time setup: create .env with strong random secrets. Safe to re-run
# (it won't overwrite an existing .env).
set -euo pipefail
cd "$(dirname "$0")"

if [ -f .env ]; then
  echo ".env already exists — leaving it untouched. Delete it first to regenerate."
  exit 0
fi

JWT=$(openssl rand -hex 32)
ADMPW=$(openssl rand -base64 18 | tr -d '/+=' | cut -c1-20)

cp .env.example .env
# macOS sed needs the '' after -i
sed -i '' "s|^OPSGPT_JWT_SECRET=.*|OPSGPT_JWT_SECRET=${JWT}|" .env
sed -i '' "s|^OPSGPT_ADMIN_PASSWORD=.*|OPSGPT_ADMIN_PASSWORD=${ADMPW}|" .env

echo "Created .env with generated secrets."
echo
echo "  Admin login (for the make-key.sh helper / any UI):"
echo "    email:    admin@opsgpt.local"
echo "    password: ${ADMPW}"
echo
echo "Next:"
echo "  1) make sure your GGUF files are in ./models  (see models/README.md)"
echo "  2) docker compose up --build"
echo "  3) open http://localhost:8000/api/docs   and run ./make-key.sh for an API key"
