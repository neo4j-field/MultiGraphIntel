"""Router agent loop: Gemini decides, MCP tools execute.

Flow per chat request:

  1. Open short-lived MCP sessions to the three substrate shims.
  2. Convert each MCP tool into a Gemini function declaration.
  3. Send the user message and function declarations to Gemini.
  4. If Gemini returns a function call, dispatch it via MCP, append the
     result to the conversation, and loop. Otherwise return the final text.

The loop caps at MAX_AGENT_ITERATIONS to prevent runaway chains.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from google import genai
from google.genai import types

from .config import (
    GEMINI_MODEL,
    LOCATION,
    MAX_AGENT_ITERATIONS,
    MCP_ANALYTICAL_URL,
    MCP_INTELLIGENCE_URL,
    MCP_OPERATIONAL_URL,
    PROJECT_ID,
)
from .mcp_client import MultiMCPClient
from .prompts import ROUTER_SYSTEM_INSTRUCTION


logger = logging.getLogger("router-agent")


def _to_gemini_tool(client: MultiMCPClient) -> types.Tool:
    return types.Tool(
        function_declarations=[
            types.FunctionDeclaration(
                name=d.name,
                description=d.description,
                parameters=d.parameters,
            )
            for d in client.declarations
        ]
    )


async def run_router(user_message: str) -> dict[str, Any]:
    """Run a single chat turn. Returns a structured result.

    Result shape:
      {
        "answer": "<final text>",
        "tool_calls": [ {"substrate": "operational", "tool": "get_account",
                          "arguments": {...}, "result_preview": "..."}, ... ],
      }
    """
    substrate_urls = {
        "operational": MCP_OPERATIONAL_URL,
        "analytical": MCP_ANALYTICAL_URL,
        "intelligence": MCP_INTELLIGENCE_URL,
    }

    gemini = genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION)
    tool_calls: list[dict[str, Any]] = []

    async with MultiMCPClient(substrate_urls) as mcp_client:
        tool_decl = _to_gemini_tool(mcp_client)
        contents: list[types.Content] = [
            types.Content(role="user", parts=[types.Part.from_text(text=user_message)])
        ]
        config = types.GenerateContentConfig(
            system_instruction=ROUTER_SYSTEM_INSTRUCTION,
            tools=[tool_decl],
            temperature=0.2,
        )

        for iteration in range(MAX_AGENT_ITERATIONS):
            response = await gemini.aio.models.generate_content(
                model=GEMINI_MODEL,
                contents=contents,
                config=config,
            )
            candidate = response.candidates[0] if response.candidates else None
            if candidate is None or candidate.content is None:
                return {"answer": "No response from model.", "tool_calls": tool_calls}

            function_calls = [
                part.function_call
                for part in (candidate.content.parts or [])
                if part.function_call is not None
            ]

            if not function_calls:
                answer_text = "".join(
                    part.text for part in (candidate.content.parts or []) if part.text
                )
                return {"answer": answer_text.strip(), "tool_calls": tool_calls}

            contents.append(candidate.content)
            response_parts: list[types.Part] = []
            for fc in function_calls:
                name = fc.name
                args = dict(fc.args) if fc.args else {}
                logger.info("Dispatching tool call: %s %s", name, args)
                try:
                    raw = await mcp_client.call_tool(name, args)
                    tool_calls.append(
                        {
                            "substrate": name.split("__", 1)[0],
                            "tool": name.split("__", 1)[1],
                            "arguments": args,
                            "result_preview": raw[:500],
                        }
                    )
                    payload = {"result": _parse_maybe_json(raw)}
                except Exception as exc:
                    logger.warning("Tool %s raised: %s", name, exc)
                    tool_calls.append(
                        {
                            "substrate": name.split("__", 1)[0]
                            if "__" in name
                            else "unknown",
                            "tool": name,
                            "arguments": args,
                            "error": str(exc),
                        }
                    )
                    payload = {"error": str(exc)}
                response_parts.append(
                    types.Part.from_function_response(name=name, response=payload)
                )
            contents.append(types.Content(role="user", parts=response_parts))

        return {
            "answer": "Reached the tool-call iteration cap before producing a final answer.",
            "tool_calls": tool_calls,
        }


def _parse_maybe_json(text: str) -> Any:
    """MCP text payloads are often JSON stringified; unwrap for cleaner re-injection."""
    text = text.strip()
    if not text:
        return ""
    if text[0] in "{[":
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
    # Try multi-part concatenations (MCP returns one text block per result item).
    lines = [line for line in text.split("\n") if line.strip()]
    parsed = []
    for line in lines:
        if line.strip()[:1] in "{[":
            try:
                parsed.append(json.loads(line))
                continue
            except json.JSONDecodeError:
                pass
        parsed.append(line)
    if len(parsed) == 1:
        return parsed[0]
    return parsed
