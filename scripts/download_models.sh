#!/usr/bin/env bash
# ============================================================
#  OpsGPT — download the GGUF models into ./models
#  Models are ~13 GB total and are NOT stored in git.
#  Run from the repo root:  bash scripts/download_models.sh
#
#  Each model has an overridable source URL. If any URL 404s
#  (upstream repos move), set it via env or edit below, e.g.:
#     QWEN3_8B_URL="https://.../file.gguf" bash scripts/download_models.sh
# ============================================================
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
mkdir -p models
cd models

HF="https://huggingface.co"

# filename                                   |  default source URL
QWEN3_8B_URL="${QWEN3_8B_URL:-$HF/bartowski/Qwen_Qwen3-8B-GGUF/resolve/main/Qwen_Qwen3-8B-Q4_K_M.gguf}"
PHI4_URL="${PHI4_URL:-$HF/bartowski/microsoft_Phi-4-mini-instruct-GGUF/resolve/main/microsoft_Phi-4-mini-instruct-Q4_K_M.gguf}"
XCODER_URL="${XCODER_URL:-$HF/mradermacher/X-Coder-RL-Qwen3-8B-i1-GGUF/resolve/main/X-Coder-RL-Qwen3-8B.i1-Q4_K_M.gguf}"
EMBED_URL="${EMBED_URL:-$HF/nomic-ai/nomic-embed-text-v1.5-GGUF/resolve/main/nomic-embed-text-v1.5.f16.gguf}"
BGE_URL="${BGE_URL:-$HF/CompendiumLabs/bge-large-en-v1.5-gguf/resolve/main/bge-large-en-v1.5-f16.gguf}"
RERANKER_URL="${RERANKER_URL:-$HF/gpustack/bge-reranker-v2-m3-GGUF/resolve/main/bge-reranker-v2-m3-Q8_0.gguf}"
# Optional draft model for speculative decoding experiments (safe to skip):
DRAFT_URL="${DRAFT_URL:-$HF/bartowski/Qwen_Qwen3-0.6B-GGUF/resolve/main/Qwen_Qwen3-0.6B-Q8_0.gguf}"

# desired local filename  ->  url   (name must match .env MODEL_FILE etc.)
declare -A MODELS=(
  ["Qwen_Qwen3-8B-Q4_K_M.gguf"]="$QWEN3_8B_URL"
  ["Phi-4-mini-instruct-Q4_K_M.gguf"]="$PHI4_URL"
  ["X-Coder-RL-Qwen3-8B.i1-Q4_K_M.gguf"]="$XCODER_URL"
  ["nomic-embed-text-v1.5.f16.gguf"]="$EMBED_URL"
  ["bge-large-en-v1.5-f16.gguf"]="$BGE_URL"
  ["bge-reranker-v2-m3-Q8_0.gguf"]="$RERANKER_URL"
)
# add the optional draft model only when DOWNLOAD_DRAFT=1
[ "${DOWNLOAD_DRAFT:-0}" = "1" ] && MODELS["Qwen_Qwen3-0.6B-Q8_0.gguf"]="$DRAFT_URL"

fail=0
for name in "${!MODELS[@]}"; do
  url="${MODELS[$name]}"
  if [ -s "$name" ]; then
    echo "✓ already present: $name"
    continue
  fi
  echo "↓ downloading $name"
  echo "    from $url"
  if curl -fL --retry 3 -o "$name.part" "$url"; then
    mv "$name.part" "$name"
    echo "✓ done: $name ($(du -h "$name" | cut -f1))"
  else
    rm -f "$name.part"
    echo "✗ FAILED: $name — check/override its URL (see top of this script)"
    fail=1
  fi
done

echo
if [ "$fail" = 0 ]; then
  echo "All models present in ./models:"
else
  echo "Some downloads failed. Fix the URL(s) and re-run (existing files are skipped)."
fi
ls -lh . 2>/dev/null | grep -E '\.gguf$' || true
