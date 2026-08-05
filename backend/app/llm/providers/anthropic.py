from typing import Any

import httpx

from app.llm.protocol import Message, Response, Tool, ToolCall
from app.llm.usage import build_usage

_URL = "https://api.anthropic.com/v1/messages"

# Pinned rather than floating: the API is versioned by this header, and letting
# it drift would change response shapes without a code change.
_API_VERSION = "2023-06-01"

# Anthropic requires max_tokens. A findings array is small, so this is generous
# enough not to truncate one and small enough to bound an unexpected reply.
_MAX_TOKENS = 8_192


class AnthropicError(RuntimeError):
    """Raised when the Anthropic API returns an error or an unreadable payload."""


class AnthropicClient:
    """Talks to the Anthropic Messages API over plain HTTP.

    A sibling of the Gemini adapter, deliberately not sharing a base class with
    it: the two wire formats differ in every detail that matters, and a shared
    parent would be an abstraction over nothing.
    """

    def __init__(self, api_key: str, model: str, timeout_seconds: float = 60.0) -> None:
        self._model = model
        self._timeout = timeout_seconds
        # The key is a header, never a query parameter: URLs reach server logs,
        # proxy logs and error traces.
        self._headers = {
            "x-api-key": api_key,
            "anthropic-version": _API_VERSION,
            "content-type": "application/json",
        }

    async def complete(
        self,
        messages: list[Message],
        tools: list[Tool] | None = None,
        system: str | None = None,
    ) -> Response:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            http_response = await client.post(
                _URL,
                headers=self._headers,
                json=self._build_payload(messages, tools, system),
            )

        if http_response.status_code != httpx.codes.OK:
            raise AnthropicError(
                f"Anthropic returned {http_response.status_code}: {http_response.text}"
            )

        return self._parse(http_response.json())

    def _build_payload(
        self,
        messages: list[Message],
        tools: list[Tool] | None,
        system: str | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self._model,
            "max_tokens": _MAX_TOKENS,
            # Anthropic uses "user" and "assistant", the same names as our protocol.
            "messages": [
                {"role": message.role, "content": message.content} for message in messages
            ],
        }

        if system is not None:
            # A top-level field here, not a message with a system role.
            payload["system"] = system

        if tools:
            payload["tools"] = [
                {
                    "name": tool.name,
                    "description": tool.description,
                    # Anthropic calls the schema input_schema, Gemini calls it parameters.
                    "input_schema": tool.parameters,
                }
                for tool in tools
            ]
            # Force a tool call: an auditor replying in prose has not produced a
            # usable finding.
            payload["tool_choice"] = {"type": "any"}

        return payload

    def _parse(self, body: dict[str, Any]) -> Response:
        """Turn an Anthropic payload into a Response.

        Raises rather than returning empty values, since a silently empty response
        would look to the orchestrator like an auditor that found nothing.
        """
        try:
            content = body["content"]
            usage = body["usage"]
        except KeyError as exc:
            raise AnthropicError(f"Unexpected Anthropic payload shape: {body}") from exc

        text_blocks = [block["text"] for block in content if block.get("type") == "text"]
        tool_calls = tuple(
            ToolCall(name=block["name"], arguments=block.get("input", {}))
            for block in content
            if block.get("type") == "tool_use"
        )

        return Response(
            model=self._model,
            usage=build_usage(
                model=self._model,
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
            ),
            text="".join(text_blocks) if text_blocks else None,
            tool_calls=tool_calls,
        )
