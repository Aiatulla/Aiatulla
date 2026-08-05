import asyncio
from typing import Any

import httpx

from app.llm.protocol import Message, Response, Tool, ToolCall
from app.llm.usage import build_usage

_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

# Three attempts, because a per-minute limit clears in about a minute and a
# per-day limit will not clear at all. Retrying past that just delays the error.
MAX_ATTEMPTS = 3
_FALLBACK_DELAY_SECONDS = 2.0
_MAX_ERROR_CHARS = 400

# Gemini names the assistant role "model". Everything above this adapter uses the
# provider-neutral names from protocol.py.
_ROLE_TO_GEMINI = {"user": "user", "assistant": "model"}


class GeminiError(RuntimeError):
    """Raised when the Gemini API returns an error or an unreadable payload."""


class GeminiClient:
    """Talks to Gemini over plain HTTP.

    A thin adapter rather than the vendor SDK: the only job here is translating
    between our types and the wire format, which keeps the recorded cassettes
    readable and makes a second provider a copy of this file.
    """

    def __init__(self, api_key: str, model: str, timeout_seconds: float = 60.0) -> None:
        self._model = model
        self._timeout = timeout_seconds
        # The key travels in a header, never in the query string. URLs end up in
        # server logs, proxy logs and error traces; headers do not.
        self._headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}

    async def complete(
        self,
        messages: list[Message],
        tools: list[Tool] | None = None,
        system: str | None = None,
    ) -> Response:
        payload = self._build_payload(messages, tools, system)

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            for attempt in range(MAX_ATTEMPTS):
                http_response = await client.post(
                    f"{_BASE_URL}/models/{self._model}:generateContent",
                    headers=self._headers,
                    json=payload,
                )

                if http_response.status_code == httpx.codes.OK:
                    return self._parse(http_response.json())

                # Rate limits are the normal cost of running several auditors at
                # once, not a failure. The response says how long to wait, so
                # honour it rather than guessing.
                rate_limited = http_response.status_code == httpx.codes.TOO_MANY_REQUESTS
                if rate_limited and attempt < MAX_ATTEMPTS - 1:
                    await asyncio.sleep(_retry_delay(http_response, attempt))
                    continue

                break

        # The body may quote the request but never the key, which is a header.
        raise GeminiError(
            f"Gemini returned {http_response.status_code}: {_readable_error(http_response)}"
        )

    def _build_payload(
        self,
        messages: list[Message],
        tools: list[Tool] | None,
        system: str | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "contents": [
                {"role": _ROLE_TO_GEMINI[message.role], "parts": [{"text": message.content}]}
                for message in messages
            ]
        }

        if system is not None:
            payload["systemInstruction"] = {"parts": [{"text": system}]}

        if tools:
            payload["tools"] = [
                {
                    "functionDeclarations": [
                        {
                            "name": tool.name,
                            "description": tool.description,
                            "parameters": tool.parameters,
                        }
                        for tool in tools
                    ]
                }
            ]
            # Force a tool call. An auditor that replies in prose has failed to
            # produce a usable finding, so we would rather the call error than
            # return something the orchestrator has to guess at.
            payload["toolConfig"] = {"functionCallingConfig": {"mode": "ANY"}}

        return payload

    def _parse(self, body: dict[str, Any]) -> Response:
        """Turn a Gemini payload into a Response.

        Raises rather than returning empty values, because a silently empty
        response would look to the orchestrator like an auditor that found nothing.
        """
        try:
            candidates = body["candidates"]
            parts = candidates[0]["content"]["parts"]
            usage_metadata = body["usageMetadata"]
        except (KeyError, IndexError) as exc:
            raise GeminiError(f"Unexpected Gemini payload shape: {body}") from exc

        text_fragments = [part["text"] for part in parts if "text" in part]
        tool_calls = tuple(
            ToolCall(
                name=part["functionCall"]["name"], arguments=part["functionCall"].get("args", {})
            )
            for part in parts
            if "functionCall" in part
        )

        return Response(
            model=self._model,
            usage=build_usage(
                model=self._model,
                # Absent on some responses; a missing count means zero, not a crash.
                input_tokens=usage_metadata.get("promptTokenCount", 0),
                output_tokens=usage_metadata.get("candidatesTokenCount", 0),
            ),
            text="".join(text_fragments) if text_fragments else None,
            tool_calls=tool_calls,
        )


def _retry_delay(response: httpx.Response, attempt: int) -> float:
    """How long to wait before retrying a rate-limited call.

    Gemini returns a RetryInfo block saying exactly how long to wait. Using it
    beats a guess, and falls back to exponential backoff when it is absent.
    """
    try:
        for detail in response.json()["error"].get("details", []):
            raw = detail.get("retryDelay")
            if raw:
                return float(str(raw).removesuffix("s"))
    except (ValueError, KeyError, TypeError):
        pass

    return float(_FALLBACK_DELAY_SECONDS * (2**attempt))


def _readable_error(response: httpx.Response) -> str:
    """Pull the human-readable message out of an error response.

    The raw body is several kilobytes of quota metadata. Storing all of it puts
    a wall of JSON in front of anyone trying to read why their run failed.
    """
    try:
        message = str(response.json()["error"]["message"])
    except (ValueError, KeyError, TypeError):
        message = response.text

    message = " ".join(message.split())
    if len(message) > _MAX_ERROR_CHARS:
        return message[:_MAX_ERROR_CHARS] + "..."
    return message
