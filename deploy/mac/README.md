# OpsGPT — Mac (Apple Silicon) API package

Run the OpsGPT model server + an **OpenAI-compatible API** (chat + embeddings)
with **Swagger docs**, entirely in Docker, on an Apple Silicon Mac (M-series).

Everything builds **natively for arm64** on your Mac — no pre-built binaries,
nothing to install except Docker.

---

## 1. Prerequisites

- **Docker Desktop for Mac (Apple Silicon)** — https://www.docker.com/products/docker-desktop/
  In Docker Desktop → **Settings → Resources**, give it **at least 10 GB memory**
  (the 8B model needs ~6 GB; the M4 Air 16 GB is fine).
- Your **Qwen3-8B GGUF** file (e.g. `Qwen3-8B-Q4_K_M.gguf`).
- ~10 GB free disk.

> Docker on macOS runs Linux containers in a lightweight VM and is **CPU-only**
> (no Metal GPU inside containers). The M4's fast cores still give usable speed
> for an API — expect a few tokens/sec for the 8B model. For maximum speed you'd
> run the model natively (Ollama/llama.cpp with Metal); this package prioritises
> "one command, fully self-contained".

## 2. Add your model(s)

Put your GGUF into `./models/` and set its filename in `.env` (next step). See
[`models/README.md`](models/README.md). Optional: add the nomic-embed GGUF if you
want the `/v1/embeddings` endpoint.

## 3. Configure + start

```bash
cd deploy/mac
./setup.sh                 # creates .env with strong random secrets (prints the admin password)
# edit .env if your GGUF filename differs from the default
docker compose up --build  # first run compiles llama.cpp for arm64 (~5-10 min) + loads the model
```

The API is ready when the backend logs show `startup`. The **first** model load
takes ~1-2 minutes.

## 4. Open Swagger

**http://localhost:8000/api/docs**

- Interactive docs for the whole API, including the OpenAI-compatible `/v1`
  endpoints (`/v1/models`, `/v1/chat/completions`, `/v1/embeddings`).

## 5. Get an API key

```bash
./make-key.sh
```

This prints an `opsk_...` key (shown once — save it). Use it as a Bearer token.
In Swagger, click **Authorize** (top right) and paste `Bearer opsk_...`.

## 6. Call the API

List models:
```bash
curl http://localhost:8000/v1/models \
  -H "Authorization: Bearer opsk_YOURKEY"
```

Chat completion (OpenAI format):
```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer opsk_YOURKEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3-8b",
    "messages": [{"role": "user", "content": "Say hello in one sentence."}]
  }'
```

Streaming (SSE):
```bash
curl -N http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer opsk_YOURKEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen3-8b","stream":true,"messages":[{"role":"user","content":"count to 5"}]}'
```

Embeddings:
```bash
curl http://localhost:8000/v1/embeddings \
  -H "Authorization: Bearer opsk_YOURKEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"nomic-embed-text","input":"the quick brown fox"}'
```

Works with any OpenAI SDK by pointing `base_url` at `http://localhost:8000/v1`:
```python
from openai import OpenAI
client = OpenAI(base_url="http://localhost:8000/v1", api_key="opsk_YOURKEY")
print(client.chat.completions.create(
    model="qwen3-8b",
    messages=[{"role": "user", "content": "hi"}],
).choices[0].message.content)
```

---

## Managing the stack

```bash
docker compose ps                 # status
docker compose logs -f backend    # API logs
docker compose logs -f llamacpp   # model server logs
docker compose down               # stop
docker compose down -v            # stop + wipe the database volume
```

## Troubleshooting

- **`docker compose up` errors about OPSGPT_JWT_SECRET** → run `./setup.sh` first.
- **Model server keeps restarting** → the GGUF filename in `.env` (`MODEL_FILE`)
  must exactly match the file in `./models/`. Check `docker compose logs llamacpp`.
- **`/v1/embeddings` fails** → you need the nomic-embed GGUF in `./models/`
  (see `models/README.md`). Chat works without it.
- **Slow first response** → the model is loading; subsequent calls are faster.
- **Out of memory / container killed** → raise Docker Desktop's memory to 10-12 GB,
  or use a smaller quant (e.g. Q4_K_M) of the model.

## What's inside

| Service     | Purpose                                              | Port |
|-------------|------------------------------------------------------|------|
| `llamacpp`  | Qwen3-8B chat model (llama.cpp, OpenAI-compatible)   | —    |
| `embed`     | nomic-embed embeddings model                         | —    |
| `backend`   | FastAPI — Swagger `/api/docs` + `/v1` API            | 8000 |
| `postgres`  | users + API keys                                     | —    |
| `redis`     | rate limiting / cache                                | —    |

Only the backend port is exposed to your Mac; the rest talk on an internal
Docker network.
