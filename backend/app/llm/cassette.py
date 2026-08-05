import hashlib
import json
from dataclasses import asdict
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Any

from app.llm.protocol import LLMClient, Message, Response, Tool, ToolCall
from app.llm.usage import Usage


class CassetteMode(StrEnum):
    """How the cassette layer behaves when a call is made.

    StrEnum so the value reads as plain text in an environment variable and in a
    log line, without every call site reaching for ``.value``.
    """

    REPLAY = "replay"
    """Serve from disk. A miss is an error. This is what tests and CI use."""

    RECORD = "record"
    """Call the real provider and write the reply to disk. Run by hand, rarely."""


class CassetteMissError(RuntimeError):
    """Raised in replay mode when no recording matches the request.

    Failing loudly is the point. A cassette layer that fell back to the network
    would turn one edited prompt into a slow, paid, non-deterministic test suite
    without anybody noticing.
    """


class CassetteClient:
    """Wraps a real client so model calls can be recorded once and replayed forever.

    The recorded key covers the model, system prompt, messages and tool schemas.
    Change any of them and the key changes, so an edited prompt misses the
    cassette instead of quietly replaying an answer to the previous question.
    """

    def __init__(
        self,
        cassette_dir: Path,
        model: str,
        mode: CassetteMode = CassetteMode.REPLAY,
        inner: LLMClient | None = None,
    ) -> None:
        if mode is CassetteMode.RECORD and inner is None:
            raise ValueError("Recording needs a real client to record from")

        self._dir = cassette_dir
        # Passed in rather than read off the inner client: in replay mode there is
        # no inner client, and a key that differs between record and replay would
        # never match what was written.
        self._model = model
        self._mode = mode
        self._inner = inner

    async def complete(
        self,
        messages: list[Message],
        tools: list[Tool] | None = None,
        system: str | None = None,
    ) -> Response:
        path = self._dir / f"{self._key(messages, tools, system)}.json"

        if self._mode is CassetteMode.REPLAY:
            if not path.exists():
                raise CassetteMissError(
                    f"No cassette at {path}. The prompt, tools or model changed. "
                    f"Re-record with CassetteMode.RECORD."
                )
            return _deserialise(json.loads(path.read_text()))

        # Record mode. The constructor guarantees inner is set.
        assert self._inner is not None
        response = await self._inner.complete(messages=messages, tools=tools, system=system)

        self._dir.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(_serialise(response), indent=2, sort_keys=True))
        return response

    def _key(self, messages: list[Message], tools: list[Tool] | None, system: str | None) -> str:
        """Hash everything that could change the reply.

        sort_keys makes the hash stable across dictionary ordering, so the same
        request produces the same filename on every machine.
        """
        fingerprint = {
            "model": self._model,
            "system": system,
            "messages": [asdict(message) for message in messages],
            "tools": [asdict(tool) for tool in tools] if tools else None,
        }
        canonical = json.dumps(fingerprint, sort_keys=True)
        return hashlib.sha256(canonical.encode()).hexdigest()[:32]


def _serialise(response: Response) -> dict[str, Any]:
    """Convert a Response to JSON-safe primitives.

    cost_usd becomes a string, not a float: reading it back as a float would
    reintroduce the rounding that Decimal exists to avoid.
    """
    return {
        "model": response.model,
        "usage": {
            "model": response.usage.model,
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "cost_usd": str(response.usage.cost_usd),
        },
        "text": response.text,
        "tool_calls": [
            {"name": call.name, "arguments": call.arguments} for call in response.tool_calls
        ],
    }


def _deserialise(raw: dict[str, Any]) -> Response:
    """Rebuild a Response from a recorded cassette."""
    usage = raw["usage"]
    return Response(
        model=raw["model"],
        usage=Usage(
            model=usage["model"],
            input_tokens=usage["input_tokens"],
            output_tokens=usage["output_tokens"],
            cost_usd=Decimal(usage["cost_usd"]),
        ),
        text=raw["text"],
        tool_calls=tuple(
            ToolCall(name=call["name"], arguments=call["arguments"]) for call in raw["tool_calls"]
        ),
    )
