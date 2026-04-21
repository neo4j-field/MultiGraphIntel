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


_STRIP_KEYS = ("$schema", "additionalProperties", "title", "$defs", "definitions")


def _normalize_schema(schema: dict[str, Any] | None) -> dict[str, Any]:
    """Make a JSON Schema Gemini-compatible.

    Gemini's function_declarations accept a restricted subset of JSON Schema:
      - `anyOf`/`oneOf` must not contain a {type: null} branch.
      - `type: null` alone is not allowed; nullability is expressed with
        `nullable: true` on the sibling schema.
      - Vendor extensions like $schema, $defs, title, additionalProperties
        are rejected at arbitrary depth.

    We walk the tree recursively, strip the forbidden keys, collapse single-
    branch anyOf/oneOf after removing null variants, and rewrite leftover
    null variants as nullable flags.
    """
    if not schema:
        return {"type": "object", "properties": {}}
    normalized = _walk(schema)
    if isinstance(normalized, dict):
        normalized.setdefault("type", "object")
        if normalized["type"] == "object":
            normalized.setdefault("properties", {})
    return normalized


def _walk(node: Any) -> Any:
    if isinstance(node, list):
        return [_walk(item) for item in node]
    if not isinstance(node, dict):
        return node
    cleaned: dict[str, Any] = {}
    for key, value in node.items():
        if key in _STRIP_KEYS:
            continue
        cleaned[key] = _walk(value)
    for variant_key in ("anyOf", "oneOf"):
        if variant_key in cleaned:
            branches = [b for b in cleaned[variant_key] if _branch_type(b) != "null"]
            had_null = len(branches) != len(cleaned[variant_key])
            if len(branches) == 1:
                merged = dict(branches[0])
                if had_null:
                    merged["nullable"] = True
                cleaned.pop(variant_key)
                # Copy the single branch onto the parent, preserving keys
                # that the parent already had (e.g. description, default).
                for mk, mv in merged.items():
                    cleaned.setdefault(mk, mv)
            elif branches:
                cleaned[variant_key] = branches
                if had_null:
                    cleaned["nullable"] = True
            else:
                cleaned.pop(variant_key)
    return cleaned


def _branch_type(branch: Any) -> str | None:
    if isinstance(branch, dict):
        return branch.get("type")
    return None
