# OpsGPT — run on your Mac (Apple Silicon)

This package **pulls pre-built images from Docker Hub** and runs an
OpenAI-compatible API (chat + embeddings) with Swagger docs. **Nothing to build.**

## 1. Prerequisites
- **Docker Desktop for Mac (Apple Silicon)** — https://www.docker.com/products/docker-desktop/
  In **Settings → Resources**, give it **≥ 10 GB memory**.
- Your **Qwen3-8B GGUF** file.

## 2. Add your model
Put your GGUF into `./models/` (see `models/README.md`). Optional: add the
nomic-embed GGUF if you want the `/v1/embeddings` endpoint.

## 3. Configure
```bash
./setup.sh          # creates .env with random secrets (prints the admin password)
```
Then open `.env` and set:
- `DOCKERHUB_USER=` → the Docker Hub account the images were published to (your supplier gives you this)
- `MODEL_FILE=` → the exact filename of your GGUF in `./models`

## 4. Run
```bash
docker compose up -d      # pulls the images and starts everything
docker compose logs -f backend   # watch until you see "startup"
```
First run downloads the images and loads the model (~1–2 min).

## 5. Use it
- **Swagger:** http://localhost:8000/api/docs
- **Get an API key:** `./make-key.sh`  → prints an `opsk_…` key (save it)

Chat:
```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer opsk_YOURKEY" -H "Content-Type: application/json" \
  -d '{"model":"qwen3-8b","messages":[{"role":"user","content":"Say hello."}]}'
```

Embeddings:
```bash
curl http://localhost:8000/v1/embeddings \
  -H "Authorization: Bearer opsk_YOURKEY" -H "Content-Type: application/json" \
  -d '{"model":"nomic-embed-text","input":"the quick brown fox"}'
```

Any OpenAI SDK works with `base_url=http://localhost:8000/v1`.

## Manage
```bash
docker compose ps
docker compose pull        # get newer images later
docker compose down        # stop
docker compose down -v     # stop + wipe the database
```

## Notes
- Docker on macOS is **CPU-only** (no Metal in containers), so the 8B model runs
  at moderate speed on the M4 — fine for an API. Subsequent calls are faster once
  the model is warm.
- If the `llamacpp` container restarts: the `MODEL_FILE` in `.env` must match the
  file in `./models`. Check `docker compose logs llamacpp`.
