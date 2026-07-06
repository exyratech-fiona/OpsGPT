"""Agentic tool-calling loop.

Given a conversation and a ToolRegistry, repeatedly:
  1. ask the model (with the tool schemas) for the next step,
  2. if it requests tool calls -> execute them and feed results back,
  3. otherwise -> emit the final answer.

Yields protocol events (dicts) the API layer forwards to the browser as SSE:
  {"type":"reasoning","content":...}
  {"type":"tool_call","name":...,"arguments":{...}}
  {"type":"tool_result","name":...,"result":...}
  {"type":"token","content":...}
  {"type":"done"}  /  {"type":"error","message":...}
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import orjson

from app.core.logging import get_logger
from app.services.llama_client import LlamaClient, LlamaClientError
from app.tools.base import ToolRegistry

logger = get_logger(__name__)

MAX_ROUNDS = 6


async def run_tool_loop(
    *,
    llama: LlamaClient,
    registry: ToolRegistry,
    messages: list[dict],
    temperature: float,
    top_p: float,
    max_tokens: int,
    model: str = "opsgpt",
) -> AsyncIterator[dict]:
    tool_schemas = registry.schemas()
    convo: list[dict] = list(messages)

    try:
        for _ in range(MAX_ROUNDS):
            # Stream this round: content/reasoning go live; tool_calls arrive last.
            content_acc = ""
            tool_calls: list[dict] = []
            stats: dict | None = None
            async for kind, payload in llama.stream_chat_tools(
                messages=convo,
                tools=tool_schemas,
                temperature=temperature,
                top_p=top_p,
                max_tokens=max_tokens,
                model=model,
            ):
                if kind == "reasoning":
                    yield {"type": "reasoning", "content": payload}
                elif kind == "content":
                    content_acc += payload  # type: ignore[operator]
                    yield {"type": "token", "content": payload}
                elif kind == "tool_calls":
                    tool_calls = payload  # type: ignore[assignment]
                elif kind == "stats":
                    stats = payload  # type: ignore[assignment]

            if not tool_calls:
                if stats:
                    yield {"type": "stats", **stats}
                yield {"type": "done"}
                return

            # Record the assistant turn (with its tool_calls) before the results.
            convo.append(
                {
                    "role": "assistant",
                    "content": content_acc,
                    "tool_calls": tool_calls,
                }
            )

            for tc in tool_calls:
                fn = tc.get("function", {})
                name = fn.get("name", "")
                try:
                    args = orjson.loads(fn.get("arguments") or "{}")
                    if not isinstance(args, dict):
                        args = {}
                except orjson.JSONDecodeError:
                    args = {}

                yield {"type": "tool_call", "name": name, "arguments": args}
                result = await registry.execute(name, args)
                yield {"type": "tool_result", "name": name, "result": result[:1500]}

                convo.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.get("id", ""),
                        "name": name,
                        "content": result,
                    }
                )

        # Exhausted the round budget without a final answer.
        yield {
            "type": "token",
            "content": "I reached the tool-call limit. Based on the data gathered "
            "above, please refine your question if you need more detail.",
        }
        yield {"type": "done"}

    except LlamaClientError as exc:
        logger.error("tool_loop_inference_failed", extra={"error": str(exc)})
        yield {"type": "error", "message": "Inference failed during tool use."}
    except Exception:  # pragma: no cover
        logger.exception("tool_loop_crashed")
        yield {"type": "error", "message": "Unexpected error during tool use."}
