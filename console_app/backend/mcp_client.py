"""MCP client adapter that fans out to the three substrate shims.

Each chat request opens one short-lived MCP session per substrate, lists the
tools, and resolves tool calls that the LLM decides to make. Because each
shim is configured with stateless_http=True, there is no per-session state
to worry about and the per-request overhead is a single HTTP round-trip per
tool call.
"""
from __future__ import annotations

from contextlib import AsyncExitStack
from dataclasses import dataclass
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


SUBSTRATE_SEPARATOR = "__"


@dataclass
class FunctionDeclaration:
    """Gemini-compatible function declaration built from an MCP tool."""
    name: str
    description: str
    parameters: dict[str, Any]


class MultiMCPClient:
    """Holds ClientSession handles for every substrate in one exit stack.

    Use as an async context manager. On __aenter__ it connects to each
    configured URL and lists the tools. Tool names are namespaced as
    ``{substrate}__{tool_name}`` so the LLM sees which substrate it is
    calling at a glance.
    """

    def __init__(self, substrate_urls: dict[str, str]) -> None:
        self.substrate_urls = substrate_urls
        self._stack: AsyncExitStack | None = None
        self._sessions: dict[str, ClientSession] = {}
        self._tool_substrate: dict[str, str] = {}
        self._tool_original_name: dict[str, str] = {}
        self.declarations: list[FunctionDeclaration] = []

    async def __aenter__(self) -> "MultiMCPClient":
        self._stack = AsyncExitStack()
        await self._stack.__aenter__()
        for substrate, url in self.substrate_urls.items():
            read, write, _ = await self._stack.enter_async_context(streamablehttp_client(url))
            session = await self._stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            self._sessions[substrate] = session
            tools = await session.list_tools()
            for tool in tools.tools:
                qualified = f"{substrate}{SUBSTRATE_SEPARATOR}{tool.name}"
                self._tool_substrate[qualified] = substrate
                self._tool_original_name[qualified] = tool.name
                self.declarations.append(
                    FunctionDeclaration(
                        name=qualified,
                        description=tool.description or f"{substrate} tool {tool.name}",
                        parameters=_normalize_schema(tool.inputSchema),
                    )
                )
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._stack is not None:
            await self._stack.__aexit__(exc_type, exc, tb)
            self._stack = None
        self._sessions.clear()

    async def call_tool(self, qualified_name: str, arguments: dict[str, Any]) -> str:
        if qualified_name not in self._tool_substrate:
            raise KeyError(f"Unknown tool: {qualified_name}")
        substrate = self._tool_substrate[qualified_name]
        original = self._tool_original_name[qualified_name]
        session = self._sessions[substrate]
        result = await session.call_tool(original, arguments or {})
        # MCP tool results are a list of content parts; for JSON tools we
        # typically get one or more text blocks containing stringified JSON.
        parts: list[str] = []
        for content in result.content:
            text = getattr(content, "text", None)
            if text is not None:
                parts.append(text)
        return "\n".join(parts) if parts else ""


def _normalize_schema(schema: dict[str, Any] | None) -> dict[str, Any]:
    """Ensure the JSON Schema is in the shape Gemini's function_declarations expect."""
    if not schema:
        return {"type": "object", "properties": {}}
    normalized = dict(schema)
    normalized.setdefault("type", "object")
    normalized.setdefault("properties", {})
    # Gemini rejects schemas with $schema, additionalProperties, and title
    # at arbitrary locations. Strip them at the top level.
    for key in ("$schema", "additionalProperties", "title"):
        normalized.pop(key, None)
    return normalized
