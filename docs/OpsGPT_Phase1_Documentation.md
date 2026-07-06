# OpsGPT — What We Built (Phase 1) + Plain-English Glossary

This document explains, in simple language, **what OpsGPT is**, **what we built so
far**, and **what every technical word means** (embedding, token, RAG, etc.).
Think of it as the "explain it like I'm new to AI" guide for the project.

---

## 1. What is OpsGPT, in one paragraph?

OpsGPT is your **own private ChatGPT**, running entirely on your own server
(`192.168.0.188`) with no internet/cloud AI needed. You type a question in a web
page, and a local AI model answers it, word-by-word, like ChatGPT. Because it's
self-hosted, your data never leaves your machine. It's built to grow into a full
product: logins, document chat (RAG), multiple AI models, an admin dashboard, and
monitoring.

---

## 2. The big picture (how a message flows)

When you type "What is a Kubernetes liveness probe?" and hit Enter:

```
 You (browser)
     │  1. your question
     ▼
 Frontend (the web page)  ──►  nginx  ──►  Backend (FastAPI)
     ▲                                          │  2. picks the right "mode",
     │  4. words stream back                    │     adds instructions, forwards
     │                                          ▼
     └──────────────────────────────────  AI engine (llama.cpp)
                                                │  3. the model "thinks" and
                                                ▼     generates the answer
                                           The model file (Qwen3-8B)
```

1. The **web page** sends your question to the **backend**.
2. The **backend** decides which AI specialist to use (chat / reasoning / code),
   adds a hidden instruction, and forwards it to the AI engine.
3. The **AI engine** (llama.cpp) runs the **model** and produces the answer.
4. The answer **streams back** word-by-word to your screen.

Each box is a **Docker container** (a self-contained mini-computer). There are
three of them running right now.

---

## 3. The three running pieces

| Container | Nickname | Job |
|---|---|---|
| `opsgpt-llamacpp` | **The brain** | Runs the AI model and generates answers |
| `opsgpt-backend` | **The manager** | Security, routing, logging — the only part the world talks to |
| `opsgpt-frontend` | **The face** | The web page you see + serves the door (nginx) |

**Golden rule:** the browser never talks to the AI brain directly. It always goes
through the manager. That's how we'll later add logins, limits, and rules without
touching the AI engine.

---

## 4. The AI MODEL Glossary (the words that matter most)

### 🧠 Model
The "brain file." It's a big file full of numbers (billions of them) that has
"read" huge amounts of text and learned patterns of language. Ours is
**Qwen3-8B**. The "8B" = **8 billion** numbers (called *parameters*). More
parameters = smarter but slower and heavier.

### 🔤 Token
AI models don't read whole words — they read **tokens**, which are word-pieces.
"Kubernetes" might be 3 tokens: `Kube` + `rne` + `tes`. A token is roughly
¾ of a word. The model reads tokens and writes tokens one at a time.

### ⚡ Tokens per second (tok/s)
How fast the model writes. Ours does ~**2.7 tok/s** — about 2 words per second.
That's the typing speed you see. It's slow here because of the server's memory
speed (explained below), not a bug.

### 📦 GGUF
The **file format** of the model. Like `.mp4` is for video, `.gguf` is the format
llama.cpp uses for models. Our file is `Qwen_Qwen3-8B-Q4_K_M.gguf`.

### 🗜️ Quantization (the `Q4_K_M` part)
"Compressing" the model so it fits in memory and runs faster. The model's numbers
are normally very precise (16 bits each). **Q4** squeezes them to ~4 bits each —
the file goes from ~16 GB down to ~5 GB. Slightly less accurate, much faster and
lighter. `Q4_K_M` is a popular "good balance" recipe.

### 🌡️ Temperature
A "creativity dial." **Low (0.2)** = focused, predictable, repeats facts (good for
code). **High (0.8)** = more varied and creative (good for brainstorming). We use
low temperature for code, higher for chat.

### 📏 Context window
The model's "short-term memory" — how much conversation it can see at once,
measured in tokens. Ours is 8192 tokens (~6000 words). Older messages beyond that
get forgotten. Bigger context = remembers more but uses more RAM.

### 💭 Reasoning model / "thinking"
Some models (like Qwen3) can **think out loud** before answering — writing a
private scratchpad of reasoning first. Great for hard problems (our "Ops Think"
mode shows this in a collapsible box), but slow, so we **turn it off** for normal
chat to get fast, direct answers.

### 🧭 Inference
The act of **running** the model to get an answer. "Doing inference" = "asking the
AI to generate text." The `llama.cpp` container is our *inference engine*.

### 🤖 LLM (Large Language Model)
The category our model belongs to. "Large" = billions of parameters, "Language" =
it works with text. ChatGPT, Claude, and Qwen3 are all LLMs.

---

## 5. The RAG / Document Glossary (for Phase 4 — "chat with your PDFs")

### 🔢 Embedding  ⭐ (you asked about this one)
An **embedding turns text into a list of numbers that captures its *meaning***.
Imagine every sentence gets GPS coordinates on a giant "map of meaning."
Sentences with similar meaning land **close together** on the map, even if they
use different words.

- "How do I restart a pod?" and "way to reboot a kubernetes container" use
  different words but mean almost the same thing → their number-lists are **near**
  each other.
- "banana bread recipe" lands **far away**.

So an embedding = the *meaning* of text, written as numbers (e.g. a list of 768
numbers). We have a special small model just for this: `nomic-embed-text`.

### 📐 Vector
Just the technical word for "that list of numbers." An embedding **is** a vector.
"768-dimensional vector" just means "a list of 768 numbers."

### 🗄️ Vector database (ChromaDB)
A special database that stores embeddings (vectors) and can instantly answer
*"which stored texts are closest in meaning to this question?"* Normal databases
search by exact words; a vector database searches by **meaning**.

### 📚 RAG (Retrieval-Augmented Generation)
The technique for "chatting with your own documents." Step by step:
1. **Retrieval** — split your PDF into chunks, embed each chunk, store them in the
   vector database. When you ask a question, embed the question and find the
   closest chunks (the relevant paragraphs).
2. **Augmented** — paste those relevant chunks into the prompt as context.
3. **Generation** — the model answers using *your document's* content, and can
   cite the page it came from.

In short: **RAG = let the AI look up your documents before answering**, so it
gives accurate, sourced answers instead of guessing.

---

## 6. The INFRASTRUCTURE Glossary (the DevOps side)

### 🐳 Docker image vs. container
- **Image** = a frozen template (like a `.iso` or a class in code). Built once.
- **Container** = a running copy of an image (like an object/instance). We have 3
  containers running from 3 images.

### 📄 Dockerfile
The **recipe** that builds an image — a list of steps ("install this, copy that,
run this command"). We wrote one that **downloads llama.cpp's source code and
compiles it** tuned for this exact CPU.

### 🏗️ Multi-stage build
A Dockerfile trick: use a big "kitchen" stage with all the compilers to build the
program, then copy only the **finished dish** into a tiny final image — leaving
the mess behind. That's why our AI engine image is only 113 MB instead of ~1.5 GB.

### 🎼 docker-compose
A file (`docker-compose.yml`) that describes **all the containers and how they
connect**, so one command (`docker compose up`) starts the whole system together.
Like a conductor for the orchestra.

### 🚪 nginx / reverse proxy
**nginx** is the front door. A **reverse proxy** means: the outside world knocks on
one door (port 8088), and nginx quietly routes the request to the right room
inside (the web page, or `/api/...` to the backend). It also makes word-by-word
streaming work smoothly.

### ⚙️ FastAPI (the backend)
A Python framework for building the "manager" service. It handles the API
(`/api/chat/stream`, `/api/health`, etc.). This is where we'll add **logins, rate
limits, and model routing** in later phases.

### 🎨 Frontend (React / Vite / Tailwind)
The web page. **React** = builds the interactive UI, **Vite** = the build tool that
packages it, **Tailwind** = the styling system that gives it the clean dark look.

### 🔌 API / OpenAI-compatible
An **API** is a standard way for programs to talk to each other. llama.cpp speaks
the **same API language as OpenAI/ChatGPT**, so tools that work with ChatGPT can
point at our server instead — no code changes.

### 📡 Streaming / SSE
**SSE (Server-Sent Events)** is the technique that lets the answer appear
**word-by-word** instead of waiting for the whole thing. The server keeps the
connection open and pushes each token as it's generated.

### 🧱 System prompt
A hidden instruction we put *before* your message, like "You are OpsGPT, a DevOps
assistant. Be concise. Use Markdown." It sets the AI's personality and rules. You
never see it, but it shapes every answer.

### 🧭 Modes / model routing
OpsGPT has four "specialists":
- **Ops Chat** — general questions
- **Ops Think** — hard problems (shows its reasoning)
- **Ops Code** — programming & scripts
- **Ops Docs** — chat with your documents (Phase 4)

"**Auto**" mode reads your question and picks the right specialist automatically.

---

## 7. The PERFORMANCE Glossary (why it's ~2.7 words/sec)

### 🧮 AVX2 / FMA (SIMD)
Special "do-many-math-operations-at-once" features in the CPU. We compiled
llama.cpp to use them — like upgrading from doing sums one-at-a-time to doing 8 at
once. This is the main *compute* speedup.

### 🧠💾 Memory bandwidth (the real bottleneck)
To write **one** token, the CPU must read the **entire 5 GB model** from RAM. So
speed is limited by **how fast RAM can be read**, not how fast the CPU thinks.
This server's RAM throughput is the ceiling → ~2.7 tok/s. A faster compiler won't
help; faster/more RAM would.

### 🔗 NUMA / socket
This server has **two CPUs (sockets)**, each with its **own** bank of RAM. Reading
*your own* socket's RAM is fast; reaching *across* to the other socket's RAM is
slow. We **pinned** the AI to **one socket** so it always uses its local, fast RAM.

### ⚖️ numa_balancing
A Linux feature that was **moving the model's memory back and forth** between the
two sockets while it ran — causing slowdowns. We turned it off.

---

## 8. What's working right now

✅ Live at **http://192.168.0.188:8088**
✅ Streaming chat (word-by-word), dark ChatGPT-style UI
✅ Markdown + code syntax highlighting, copy / stop / regenerate buttons
✅ Conversation history + search (saved in your browser for now)
✅ 4 modes with automatic routing
✅ "Thinking" shown live for Ops Think mode
✅ All self-hosted, no cloud, no internet needed to chat

---

## 9. How to operate it (handy commands on the server)

```bash
cd ~/OpsGPT

docker compose ps                 # see status of all 3 containers
docker compose restart            # restart everything
docker compose logs -f backend    # watch the backend logs live
docker compose logs -f llamacpp   # watch the AI engine logs live
docker compose down               # stop everything
docker compose up -d              # start everything

# tuning lives in:  ~/OpsGPT/.env   (model file, threads, NUMA, port)
```

---

## 10. The roadmap (what's next)

| Phase | What it adds | In simple terms |
|---|---|---|
| 1 ✅ | Streaming chat UI | *(done — what this doc describes)* |
| 2 | Auth (JWT, API keys, PostgreSQL) | Logins & user accounts |
| 3 | Redis | Speed cache + sessions |
| 4 | RAG (ChromaDB, embeddings) | **Chat with your PDFs** |
| 5 | Multi-model routing | Auto-switch between the 4 AI models |
| 6 | Admin dashboard + Prometheus/Grafana | Usage stats, monitoring, graphs |
| 7 | Production hardening | HTTPS, backups, health checks |

---

*Generated as part of the OpsGPT build. Lives at `~/OpsGPT/docs/` on the server.*
