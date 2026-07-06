"""Prometheus metrics + lightweight in-process counters for the admin dashboard.

The Prometheus objects feed /metrics (scraped by Prometheus -> Grafana). The
RUNTIME dict gives the in-app admin dashboard instant totals without a query.
"""

from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

HTTP_REQUESTS = Counter(
    "opsgpt_http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status"],
)
HTTP_LATENCY = Histogram(
    "opsgpt_http_request_duration_seconds",
    "HTTP request latency (seconds)",
    ["path"],
)
CHAT_REQUESTS = Counter(
    "opsgpt_chat_requests_total",
    "Chat completions requested",
    ["mode", "model"],
)
TOKENS_GENERATED = Counter(
    "opsgpt_tokens_generated_total",
    "Tokens generated",
    ["model"],
)
TOOL_CALLS = Counter(
    "opsgpt_tool_calls_total",
    "Tool calls executed",
    ["tool"],
)

# Fast, in-process running totals for the admin dashboard.
RUNTIME: dict[str, float] = {
    "chats": 0,
    "tokens": 0,
    "tool_calls": 0,
}


def record_chat(mode: str, model: str) -> None:
    CHAT_REQUESTS.labels(mode=mode, model=model).inc()
    RUNTIME["chats"] += 1


def record_tokens(model: str, n: int) -> None:
    if n > 0:
        TOKENS_GENERATED.labels(model=model).inc(n)
        RUNTIME["tokens"] += n


def record_tool_call(tool: str) -> None:
    TOOL_CALLS.labels(tool=tool).inc()
    RUNTIME["tool_calls"] += 1


def render_latest() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST
