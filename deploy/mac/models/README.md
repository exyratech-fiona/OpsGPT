# Put your GGUF model files here

The compose bind-mounts this folder read-only into the model servers.

## Required
- **Chat model — Qwen3-8B (you already have this):**
  e.g. `Qwen3-8B-Q4_K_M.gguf`
  Then set `MODEL_FILE=` in `.env` to the **exact filename** you place here.

## Optional (only if you want the embeddings API, `/v1/embeddings`)
- **nomic-embed-text-v1.5** (~0.5 GB). Download the F16 GGUF:
  https://huggingface.co/nomic-ai/nomic-embed-text-v1.5-GGUF
  file: `nomic-embed-text-v1.5.f16.gguf`
  Set `EMBED_MODEL_FILE=` in `.env` to match.

Chat works without the embed model — the `embed` container will just keep
retrying until you add the file (it does not block chat).

Example:
```
models/
├── Qwen3-8B-Q4_K_M.gguf
└── nomic-embed-text-v1.5.f16.gguf
```
