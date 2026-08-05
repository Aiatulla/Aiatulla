from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from app.llm.usage import Usage

Role = Literal["user", "assistant"]


@dataclass(frozen=True)
class Message:
    """One turn of a conversation, in provider-neutral form."""

    role: Role
    content: str


@dataclass(frozen=True)
class Tool:
    """A function the model may call.

    ``parameters`` is a JSON Schema object. Auditors return their findings by
    calling a tool rather than writing prose, so the result arrives already
    structured and never has to be parsed out of free text.
    """

    name: str
    description: str
    parameters: dict[str, Any]


@dataclass(frozen=True)
class ToolCall:
    """A model's request to call one tool, with the arguments it chose."""

    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class Response:
    """The result of one model call.

    ``usage`` is not optional. Every call is priced at the moment it is made, so
    the orchestrator can enforce a budget without recomputing anything later.
    """

    model: str
    usage: Usage
    text: str | None = None
    tool_calls: tuple[ToolCall, ...] = field(default_factory=tuple)


class LLMClient(Protocol):
    """The single interface every provider and wrapper implements.

    Keeping this to one method is what lets a cassette layer, a budget guard, or
    a different provider stand in for each other without any caller changing.
    """

    async def complete(
        self,
        messages: list[Message],
        tools: list[Tool] | None = None,
        system: str | None = None,
    ) -> Response:
        """Send a conversation to the model and return its reply."""
        ...
