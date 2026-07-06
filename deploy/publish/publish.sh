#!/usr/bin/env bash
# Build the OpsGPT arm64 images (for Apple Silicon Macs) and push them to Docker
# Hub. Run this ONCE. The client then just pulls + runs (no build).
#
# Prereqs:
#   - docker login            (to the Docker Hub account you'll push to)
#   - DOCKERHUB_USER set       (your Docker Hub username / namespace)
#
# Run it on an Apple Silicon Mac for a fast native build, OR on any Docker host
# (Windows/Linux) where it will use QEMU emulation (slower, one-time).
#
# Usage:
#   DOCKERHUB_USER=youruser ./publish.sh
set -euo pipefail
cd "$(dirname "$0")"

: "${DOCKERHUB_USER:?set DOCKERHUB_USER=your-dockerhub-username}"
TAG="${IMAGE_TAG:-mac}"
ROOT="../.."   # repo root relative to deploy/publish

echo "==> Publishing to  ${DOCKERHUB_USER}/opsgpt-llamacpp:${TAG}  and  ${DOCKERHUB_USER}/opsgpt-backend:${TAG}"

# Register arm64 emulation (no-op / harmless if already arm64 or already set up).
docker run --privileged --rm tonistiigi/binfmt --install arm64 >/dev/null 2>&1 || true

# A buildx builder that can target linux/arm64.
docker buildx create --name opsgpt-builder --use >/dev/null 2>&1 || docker buildx use opsgpt-builder

echo "==> Building + pushing llama.cpp (chat + embeddings share this image)…"
docker buildx build --platform linux/arm64 \
  -t "${DOCKERHUB_USER}/opsgpt-llamacpp:${TAG}" \
  --push "${ROOT}/docker/llamacpp"

echo "==> Building + pushing backend (Swagger + /v1 API)…"
docker buildx build --platform linux/arm64 \
  -t "${DOCKERHUB_USER}/opsgpt-backend:${TAG}" \
  --push "${ROOT}/backend"

echo
echo "Done. Images on Docker Hub:"
echo "  ${DOCKERHUB_USER}/opsgpt-llamacpp:${TAG}"
echo "  ${DOCKERHUB_USER}/opsgpt-backend:${TAG}"
echo
echo "Send the client the folder  deploy/client-mac/  and tell them to set"
echo "DOCKERHUB_USER=${DOCKERHUB_USER} in their .env, then: docker compose up"
