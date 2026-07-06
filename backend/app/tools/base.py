"""Tool abstraction for agentic tool-calling.

A Tool pairs an OpenAI-compatible JSON schema (advertised to the model) with an
async handler (executed when the model calls it). The ToolRegistry groups tools
and is the seam where external MCP servers can later contribute tools too.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

ToolHandler = Callable[[dict], Awaitable[str]]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict  # JSON Schema for the arguments object
    handler: ToolHandler

    def openai_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def __len__(self) -> int:
        return len(self._tools)

    def all_tools(self) -> list[Tool]:
        return list(self._tools.values())

    def schemas(self) -> list[dict]:
        return [t.openai_schema() for t in self._tools.values()]

    async def execute(self, name: str, arguments: dict) -> str:
        tool = self._tools.get(name)
        if tool is None:
            return f"Error: unknown tool '{name}'."
        try:
            return await tool.handler(arguments)
        except Exception as exc:  # never let a tool crash the chat loop
            return f"Error executing '{name}': {exc}"
