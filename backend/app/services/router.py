"""OpsGPT mode router.

Maps a logical *mode* to a concrete route: which upstream model to use, the
system prompt that frames the assistant, and sane generation defaults.

Phase 1 runs a single llama.cpp server, so every route points at the same
upstream. The interface, prompts, and the `auto` classifier are already in
place; Phase 5 swaps `upstream_url` per mode (or triggers a model hot-swap)
without any change to callers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.config import Settings


@dataclass(frozen=True)
class Route:
    mode: str
    display_name: str
    model: str
    description: str
    system_prompt: str
    temperature: float
    # Qwen3 / X-Coder are hybrid reasoning models. We toggle their <think> phase
    # via the /think and /no_think soft switches. On CPU-only inference, thinking
    # is expensive, so only Ops Think enables it.
    thinking: bool = False
    # Tool providers this route may use (e.g. "kubernetes"). Empty = plain chat.
    tools: tuple[str, ...] = ()


_CHAT = Route(
    mode="ops-chat",
    display_name="Ops Chat",
    model="qwen3-8b",
    description="General assistant for DevOps & platform engineering.",
    system_prompt=(
        "You are OpsGPT, an enterprise AI assistant specialised in DevOps, "
        "cloud, and platform engineering. Be precise, practical, and concise. "
        "Prefer correct, production-grade answers over verbose ones. Use "
        "Markdown for formatting and fenced code blocks for any code."
    ),
    temperature=0.7,
    thinking=False,
)

_THINK = Route(
    mode="ops-think",
    display_name="Ops Think",
    model="phi-4-mini",
    description="Step-by-step reasoning and analysis.",
    system_prompt=(
        "You are OpsGPT in reasoning mode. Think carefully and work through the "
        "problem step by step before giving a final, clearly-marked answer. "
        "Show the key reasoning, not filler."
    ),
    temperature=0.4,
    thinking=True,
)

_CODE = Route(
    mode="ops-code",
    display_name="Ops Code",
    model="x-coder",
    description="Programming, scripting, and IaC.",
    system_prompt=(
        "You are OpsGPT in coding mode, an expert software and infrastructure "
        "engineer. Return correct, idiomatic, production-ready code with brief "
        "explanations. Always use fenced code blocks with the right language "
        "tag. Never invent APIs."
    ),
    temperature=0.2,
)

_DOCS = Route(
    mode="ops-docs",
    display_name="Ops Docs",
    model="qwen3-8b",
    description="Chat over your documents (RAG).",
    system_prompt=(
        "You are OpsGPT in document mode. Answer strictly from the provided "
        "context. If the answer is not in the context, say so. Cite the source "
        "pages you used."
    ),
    temperature=0.3,
)

_CLUSTER = Route(
    mode="ops-cluster",
    display_name="Ops Cluster",
    model="qwen3-8b",
    description="Investigate your Kubernetes cluster (read-only) with live tools.",
    system_prompt=(
        "You are OpsGPT in cluster mode, a Kubernetes SRE assistant with "
        "READ-ONLY access to a live cluster via tools. When a question needs "
        "live data, call the appropriate k8s_* tool rather than guessing. "
        "Prefer the smallest set of calls that answers the question. After "
        "gathering data, give a concise, correct answer and cite the namespace/"
        "resource you looked at. You cannot modify the cluster."
    ),
    temperature=0.2,
    thinking=False,
    tools=("kubernetes",),
)

_ROUTES: dict[str, Route] = {
    r.mode: r for r in (_CHAT, _THINK, _CODE, _DOCS, _CLUSTER)
}

# Heuristics for `auto` routing. Cheap, deterministic, explainable — good enough
# until a learned classifier replaces it later.
_CODE_PATTERNS = re.compile(
    r"```|\b(docker|kubernetes|k8s|terraform|ansible|bash|python|fastapi|"
    r"sql|yaml|regex|function|class|def |import |traceback|stack ?trace|"
    r"compile|refactor|bug|exception)\b",
    re.IGNORECASE,
)
_THINK_PATTERNS = re.compile(
    r"\b(why|prove|reason|step[- ]by[- ]step|analyz|analyse|compare|trade[- ]?off|"
    r"derive|explain how|root cause)\b",
    re.IGNORECASE,
)


class ModeRouter:
    """Selects a :class:`Route` for a request."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @staticmethod
    def routes() -> list[Route]:
        return list(_ROUTES.values())

    def classify(self, text: str) -> str:
        """Pick a mode from the latest user message (used when mode='auto')."""
        if _CODE_PATTERNS.search(text):
            return "ops-code"
        if _THINK_PATTERNS.search(text):
            return "ops-think"
        return "ops-chat"

    def resolve(self, mode: str, last_user_message: str) -> Route:
        if mode == "auto":
            mode = self.classify(last_user_message)
        return _ROUTES.get(mode, _CHAT)
