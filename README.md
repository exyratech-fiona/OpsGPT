# OpsGPT

**A fully self-hosted, private ChatGPT-style AI assistant for DevOps teams.**
Runs entirely on your own hardware (CPU-only, no GPU). No prompt, document, or log
ever leaves your infrastructure.

OpsGPT can chat, reason, write code, answer questions from your own documents (RAG),
and *act* on your live infrastructure — Kubernetes, Elasticsearch and GitLab CI/CD —
through strictly read-only tools. It also exposes an **OpenAI-compatible API** so any
app or SDK can call your models with an API key.

---

## Contents
- [Features](#features)
- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Quick start](#quick-start)
- [Configuration](#configuration)
- [Models](#models)
- [First run & access](#first-run--access)
- [Tool integrations (MCP)](#tool-integrations-mcp)
- [API access & Swagger](#api-access--swagger)
- [Operations](#operations)
- [Performance notes](#performance-notes)
- [Project structure](#project-structure)
- [Troubleshooting](#troubleshooting)
- [Security](#security)

---

## Features

| Area | What you get |
|---|---|
| **Chat modes** | Ops Chat (Qwen3-8B), Ops Think (Phi-4-mini), Ops Code (X-Coder), Ops Docs (RAG) |
| **Streaming UI** | React/Tailwind, token-by-token SSE, markdown + code highlighting, Gemini-style glow |
| **Auth** | JWT sessions, bcrypt passwords, roles (admin/user/guest), `opsk_` API keys, HTTP Basic, `/auth/token` for gateway clients |
| **RAG** | Upload PDFs → BGE embeddings → pgvector search → **cross-encoder rerank** → answers with citations |
| **Agentic tools** | Read-only Kubernetes / Elasticsearch / GitLab, configurable in the UI |
| **OpenAI API** | `/v1/chat/completions`, `/v1/models`, `/v1/embeddings` (nomic + BGE), `/v1/rerank` (bge-reranker) |
| **Governance** | Per-user daily token limits, rate limiting, admin panel |
| **Monitoring** | Prometheus + Grafana, per-model health, in-app admin dashboard |
| **Hardening** | Log rotation, automated Postgres backups, TLS edge config |

---

## Architecture

One `docker compose up` brings up the whole platform:

```
   Browser ──HTTPS──► edge nginx (TLS) ──► frontend (React+nginx :8088)
                                              │  proxies /api /v1 /auth
                                              ▼
                                       backend (FastAPI)
   ┌────────┬─────┬───────┬──────┬─────────┬─────────┬───────┬──────────┐
   ▼        ▼     ▼       ▼      ▼         ▼         ▼       ▼
 llamacpp  phi  xcoder  embed  embed-bge reranker  redis  postgres
 Qwen3-8B Phi-4 X-Coder nomic  BGE-1024  bge-rrk   cache  +pgvector
   └──────────── llama.cpp inference servers ──────────┘     (mcp: k8s/es/gitlab)

   Monitoring: prometheus · grafana · node-exporter · cadvisor
   Maintenance: backup (scheduled pg_dump)
```

RAG uses a **two-stage retriever**: BGE-large-en-v1.5 embeddings fetch the top-20
candidates from pgvector, then the **bge-reranker-v2-m3** cross-encoder rescores
them and keeps the best 5 — much higher answer precision than embeddings alone.

The inference engine is **llama.cpp built from source** for the host CPU
(AVX2+FMA+F16C), serving quantized GGUF models over an OpenAI-compatible API.

---

## Prerequisites

- **Docker** 24+ and **Docker Compose v2** (`docker compose`, not `docker-compose`)
- **CPU** with AVX2 (any modern x86-64 server). No GPU required.
- **RAM**: ~24 GB free with all seven models loaded (less if you run fewer)
- **Disk**: ~17 GB for models + images
- `curl` (for the model download script)

---

## Quick start

```bash
# 1. Clone
git clone <your-repo-url> opsgpt && cd opsgpt

# 2. Configure — copy the template and edit the CHANGE-ME values
cp .env.example .env
#   edit .env: set POSTGRES_PASSWORD, OPSGPT_JWT_SECRET (openssl rand -hex 32),
#   OPSGPT_ADMIN_PASSWORD, GRAFANA_ADMIN_PASSWORD, OPSGPT_CORS_ORIGINS

# 3. Download the models (~15 GB) into ./models
bash scripts/download_models.sh

# 4. Launch
docker compose up -d

# 5. Watch the big model warm up (first start ~2-5 min)
docker compose ps
docker compose logs -f backend
```

Open **http://SERVER_IP:8088** and log in with the seed admin from your `.env`.

> First boot runs database migrations automatically and seeds the admin user.

> The Quick Start above is **Option A — the full server stack**. For Apple-Silicon
> Macs and image publishing, see **Deployment options** below.

---

## Deployment options

OpsGPT can be run several ways. They differ in *where* they run and *how much* of
the stack they include.

| Option | Runs on | Includes | Best for |
|---|---|---|---|
| **A. Full server stack** — repo root `docker-compose.yml` | Linux server | **Everything**: chat/think/code models, BGE embeddings + reranker, Web UI, PostgreSQL+pgvector, Redis, MCP tools, monitoring, backups, TLS edge | Production (the Quick Start above) |
| **B. Mac — build from source** — `deploy/mac/` | Apple-Silicon Mac | API-only subset: chat + embeddings, OpenAI `/v1` + Swagger, Postgres + Redis. Built natively (arm64). **No Web UI / reranker / MCP / monitoring.** | Developers building locally on a Mac |
| **C. Mac — pre-built images** — `deploy/client-mac/` | Apple-Silicon Mac | Same subset as B, but images are **pulled from Docker Hub** — nothing to build | Handing a ready-to-run package to an end-user |
| **D. Publish images** — `deploy/publish/` | Maintainer (any Docker host) | `publish.sh` builds the arm64 images and pushes them to Docker Hub so Option C can pull them | Preparing the Option-C package |

> The `deploy/` packages are a **lightweight, API-only** flavour (chat + embeddings +
> Swagger). The full experience — Web UI, RAG with reranking, MCP tools, monitoring —
> is **Option A**, the server stack this README's Quick Start covers.

### Option B — Mac, build from source (`deploy/mac/`)

```bash
cd deploy/mac
./setup.sh                    # creates .env with strong random secrets (prints the admin password)
#  put your GGUF file(s) in ./models  (see deploy/mac/models/README.md):
#    required: a Qwen3-8B GGUF  → set MODEL_FILE in .env to its exact filename
#    optional: nomic-embed-text-v1.5.f16.gguf  (enables /v1/embeddings)
docker compose up --build     # builds llama.cpp + backend natively for arm64 (first run is slow)
```
Then open **http://localhost:8000/api/docs** (Swagger). Get an API key with
`./make-key.sh` and call the API at `http://localhost:8000/v1`.

### Option C — Mac, run pre-built images (`deploy/client-mac/`)

Prereq: someone ran Option D and pushed the images. Then:

```bash
cd deploy/client-mac
./setup.sh                    # creates .env with secrets
#  edit .env:  DOCKERHUB_USER=<account the images were pushed to>
#              MODEL_FILE=<your Qwen3-8B GGUF filename in ./models>
#  put your GGUF file(s) in ./models
docker compose up -d          # pulls images from Docker Hub — no build
./make-key.sh                 # prints an opsk_ API key (shown once)
```
Then open **http://localhost:8000/api/docs** and use the key as a Bearer token.

### Option D — publish the Mac images (`deploy/publish/`)

Run once (on a Mac for a native build, or any Docker host via emulation):

```bash
docker login                                # to your Docker Hub account
cd deploy/publish
DOCKERHUB_USER=youruser ./publish.sh        # builds arm64 llamacpp + backend, pushes to Docker Hub
```
Then give the `deploy/client-mac/` folder to end-users (Option C) and tell them to
set `DOCKERHUB_USER=youruser` in their `.env`.

---

## Configuration

All configuration is via `.env` (see `.env.example` for the full annotated list).
The essentials to change before going live:

| Variable | Purpose |
|---|---|
| `HTTP_PORT` | Host port for the web UI (default 8088) |
| `POSTGRES_PASSWORD` | Database password — **change** |
| `OPSGPT_JWT_SECRET` | Session signing secret — **change** (`openssl rand -hex 32`) |
| `OPSGPT_ADMIN_EMAIL` / `OPSGPT_ADMIN_PASSWORD` | First admin, seeded once |
| `OPSGPT_CORS_ORIGINS` | Origin(s) the browser uses |
| `LLAMA_THREADS` / `LLAMA_CPUSET` | CPU tuning (see Performance) |
| `OPSGPT_RATE_LIMIT_PER_MIN` | Per-user request rate limit |

Most other variables have sensible compose defaults and can be omitted.

---

## Models

Seven models run as separate llama.cpp containers. They live in `./models/` and
are **not** stored in git (~15 GB total).

| File | Role | Dims |
|---|---|---|
| `Qwen_Qwen3-8B-Q4_K_M.gguf` | Ops Chat / Docs / all tool-calling | — |
| `Phi-4-mini-instruct-Q4_K_M.gguf` | Ops Think (fast reasoning) | — |
| `X-Coder-RL-Qwen3-8B.i1-Q4_K_M.gguf` | Ops Code | — |
| `bge-large-en-v1.5-f16.gguf` | **RAG embeddings** (default) + `/v1/embeddings` (`model=bge`) | 1024 |
| `nomic-embed-text-v1.5.f16.gguf` | Embeddings via `/v1/embeddings` (`model=nomic`) | 768 |
| `bge-reranker-v2-m3-Q8_0.gguf` | **RAG reranker** (retrieve-20 → rerank-5) + `/v1/rerank` | — |
| `Qwen_Qwen3-0.6B-Q8_0.gguf` *(optional)* | Speculative-decoding draft (experimental) | — |

`scripts/download_models.sh` fetches them from Hugging Face. Each source URL is
overridable at the top of the script (or via env vars) in case an upstream repo moves.
The filenames must match the `*_MODEL_FILE` values in `.env`.

**RAG embeddings note:** BGE-large-en-v1.5 caps at **512 tokens**, so document
chunks are sized to fit (see `chunk_chars`). The vector column is `vector(1024)`;
switching the embedding model to a different dimension needs a schema migration.

---

## First run & access

| Service | URL |
|---|---|
| Web UI | `http://SERVER_IP:8088` |
| API (OpenAI-compatible) | `http://SERVER_IP:8088/v1` |
| Swagger / API docs | `http://SERVER_IP:8088/api/docs` |
| Grafana | `http://SERVER_IP:3001` |

Log in as the seed admin, then **change the admin password** and create users from
the **Admin** panel. For a public domain with TLS, use the sample edge-nginx config
in `nginx/opsgpt.conf`.

---

## Tool integrations (MCP)

Open **Tool Connections** in the UI (admin) to add read-only integrations. Each has a
**Test connection** button, enable/disable toggle, and is used automatically when a
question is relevant.

- **Kubernetes** — paste a read-only kubeconfig (or mount one at
  `./secrets/kube-readonly.yaml`). Tools: list namespaces/pods, pod logs, describe,
  events, top. RBAC on the kubeconfig is the guardrail (use a `view`-bound account).
- **Elasticsearch** — URL + credentials. Read-only search/count/indices.
- **GitLab** — URL + a `read_api` token. List projects/pipelines/jobs/logs/MRs,
  a multi-project watchlist, and "latest pipeline across all projects".

---

## API access & Swagger

OpsGPT speaks the OpenAI API. Create an API key in the UI (**API Keys**), then:

```python
from openai import OpenAI
client = OpenAI(base_url="http://SERVER_IP:8088/v1", api_key="opsk_...")

client.chat.completions.create(
    model="qwen3-8b",                      # qwen3-8b | ops-think | ops-code
    messages=[{"role": "user", "content": "/no_think Explain a rolling update."}],
)
client.embeddings.create(model="bge-large-en-v1.5", input=["hello world"])  # or "nomic"
```

Endpoints: `POST /v1/chat/completions`, `GET /v1/models`, `POST /v1/embeddings`,
`POST /v1/rerank`. Example rerank:

```bash
curl http://SERVER_IP:8088/v1/rerank -H "Authorization: Bearer opsk_..." \
  -H "Content-Type: application/json" \
  -d '{"query":"data retention policy","documents":["doc a","doc b"],"top_n":5}'
```

**Auth options** (any of): `Authorization: Bearer opsk_...` (API key) · HTTP Basic
`email:password` · or `POST /auth/token` (username+password → bearer, for gateway
clients that cache a token). Interactive docs live at **`/api/docs`**.

---

## Operations

```bash
# helper script (wraps common tasks)
scripts/opsgpt.sh up | down | logs | backup | restore

# manual
docker compose ps
docker compose logs -f backend
docker compose restart frontend
```

- **Backups**: a sidecar runs `pg_dump` on a schedule into `./backups/`
  (`BACKUP_INTERVAL_HOURS`, `BACKUP_RETAIN_DAYS`).
- **Monitoring**: Grafana on `:3001`, Prometheus scrapes backend + all model servers.

> **Deploy note:** changing a model container's config forces it to reload the model
> (~5 min "unhealthy"). Because the backend waits for models to be healthy, after such
> a change let the models warm up, then `docker compose up -d backend`, and finally
> recreate the frontend so nginx re-resolves the backend.

---

## Performance notes

CPU inference is **memory-bandwidth-bound**. On a dual-socket Xeon E5-2650 v3 the 8B
model runs ~4.8 tok/s; Phi-4-mini ~8.6 tok/s. Key tuning (already defaulted in `.env`):

- `numactl --interleave=all` spreads model memory across both NUMA nodes (~1.8× faster).
- `LLAMA_THREADS` / `LLAMA_CPUSET` — lower these if the box shares CPU with other work.
- Quantized (Q4) models keep RAM and bandwidth demand low.

Speculative decoding with the 0.6B draft was benchmarked and **not adopted** on this
hardware (draft acceptance too low → net slower). A GPU or higher memory bandwidth is
required to meaningfully beat the CPU ceiling.

---

## Project structure

```
backend/            FastAPI app (auth, chat, RAG, tools, /v1 API), Alembic migrations
frontend/           React + Vite + Tailwind SPA, nginx reverse proxy
docker/llamacpp/    Dockerfile that builds llama.cpp from source for the host CPU
monitoring/         Prometheus + Grafana provisioning & dashboards
nginx/              Sample TLS edge config for a public domain
scripts/            download_models.sh, opsgpt.sh, pg_backup.sh
deploy/             Alternative packagings (see "Deployment options")
  ├─ mac/           Apple-Silicon Mac — build from source
  ├─ client-mac/    Apple-Silicon Mac — run pre-built Docker Hub images
  └─ publish/       publish.sh — build + push the Mac images to Docker Hub
docker-compose.yml  The full server stack (Option A)
.env.example        Annotated configuration template
models/             GGUF models (gitignored — see scripts/download_models.sh)
secrets/            kubeconfig etc. (gitignored)
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `backend` unhealthy on first start | The 8B model is still loading (~2-5 min). Watch `docker compose logs -f llamacpp`. |
| 502 from the UI | Backend was recreated with a new IP — recreate the frontend so nginx re-resolves. |
| Embedding/upload errors | Ensure `nomic-embed` model is present and the `embed` container is up. |
| Model download 404 | Override the URL at the top of `scripts/download_models.sh`. |
| Slow generation | Expected on CPU. See Performance notes; try Ops Think (Phi) for speed. |

---

## Security

- **Self-hosted** — no data leaves your network.
- Passwords bcrypt-hashed; API keys sha-256 hashed; JWT sessions.
- Infrastructure tools are **read-only**, enforced at the source (e.g. Kubernetes RBAC).
- Secrets (`.env`, `secrets/`, kubeconfig) are gitignored — never commit them.
- **Change** the seed admin password and `OPSGPT_JWT_SECRET` before production use.

---

*OpsGPT — self-hosted, private, production-grade. Built on llama.cpp + FastAPI + React.*
