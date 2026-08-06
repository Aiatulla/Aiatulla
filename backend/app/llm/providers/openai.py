import json
from typing import Any

import httpx

from app.llm.protocol import Message, Response, Tool, ToolCall
from app.llm.usage import build_usage

_URL = "https://api.openai.com/v1/chat/completions"


class OpenAIError(RuntimeError):
    """Raised when the OpenAI API returns an error or an unreadable payload."""


class OpenAIClient:
    """Talks to the OpenAI chat completions API over plain HTTP."""

    def __init__(self, api_key: str, model: str, timeout_seconds: float = 180.0) -> None:
        self._model = model
        self._timeout = timeout_seconds
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
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
            raise OpenAIError(f"OpenAI returned {http_response.status_code}: {http_response.text}")

        return self._parse(http_response.json())

    def _build_payload(
        self,
        messages: list[Message],
        tools: list[Tool] | None,
        system: str | None,
    ) -> dict[str, Any]:
        # The system prompt is the first message here, unlike Anthropic's
        # top-level field or Gemini's systemInstruction.
        wire_messages: list[dict[str, str]] = []
        if system is not None:
            wire_messages.append({"role": "system", "content": system})
        wire_messages += [
            {"role": message.role, "content": message.content} for message in messages
        ]

        payload: dict[str, Any] = {"model": self._model, "messages": wire_messages}

        if tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters,
                    },
                }
                for tool in tools
            ]
            # Force a tool call, as with the other providers.
            payload["tool_choice"] = "required"

        return payload

    def _parse(self, body: dict[str, Any]) -> Response:
        try:
            message = body["choices"][0]["message"]
            usage = body["usage"]
        except (KeyError, IndexError) as exc:
            raise OpenAIError(f"Unexpected OpenAI payload shape: {body}") from exc

        tool_calls = tuple(
            ToolCall(
                name=call["function"]["name"],
                # OpenAI returns arguments as a JSON string, where the other two
                # providers return an object. Decoding here keeps that difference
                # from leaking to callers.
                arguments=self._decode_arguments(call["function"]["arguments"]),
            )
            for call in message.get("tool_calls") or []
        )

        return Response(
            model=self._model,
            usage=build_usage(
                model=self._model,
                input_tokens=usage.get("prompt_tokens", 0),
                output_tokens=usage.get("completion_tokens", 0),
            ),
            text=message.get("content"),
            tool_calls=tool_calls,
        )

    @staticmethod
    def _decode_arguments(raw: str) -> dict[str, Any]:
        try:
            decoded: dict[str, Any] = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise OpenAIError(f"Tool arguments were not valid JSON: {raw!r}") from exc
        return decoded
