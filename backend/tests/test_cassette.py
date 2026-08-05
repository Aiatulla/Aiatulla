from decimal import Decimal

import pytest

from app.llm.cassette import CassetteClient, CassetteMissError, CassetteMode
from app.llm.protocol import Message, Response, Tool, ToolCall
from app.llm.usage import build_usage

MODEL = "gemini-2.0-flash"
MESSAGES = [Message(role="user", content="audit this repository")]
TOOL = Tool(
    name="report_finding",
    description="Report one audit finding",
    parameters={"type": "object", "properties": {"summary": {"type": "string"}}},
)


class FakeClient:
    """Stands in for a real provider so recording needs no network or key."""

    def __init__(self) -> None:
        self.calls = 0
        self._model = "gemini-2.0-flash"

    async def complete(self, messages, tools=None, system=None) -> Response:
        self.calls += 1
        return Response(
            model=self._model,
            usage=build_usage(self._model, input_tokens=1_000, output_tokens=200),
            text=None,
            tool_calls=(ToolCall(name="report_finding", arguments={"summary": "unused module"}),),
        )


async def test_record_then_replay_returns_the_same_response(tmp_path):
    inner = FakeClient()
    recorder = CassetteClient(tmp_path, MODEL, mode=CassetteMode.RECORD, inner=inner)

    recorded = await recorder.complete(MESSAGES, tools=[TOOL])

    player = CassetteClient(tmp_path, MODEL, mode=CassetteMode.REPLAY)
    replayed = await player.complete(MESSAGES, tools=[TOOL])

    assert replayed == recorded
    assert inner.calls == 1, "replay must not reach the provider"


async def test_replay_preserves_decimal_cost(tmp_path):
    """Round-tripping cost through a float would reintroduce rounding error."""
    recorder = CassetteClient(tmp_path, MODEL, mode=CassetteMode.RECORD, inner=FakeClient())
    recorded = await recorder.complete(MESSAGES)

    replayed = await CassetteClient(tmp_path, MODEL, mode=CassetteMode.REPLAY).complete(MESSAGES)

    assert isinstance(replayed.usage.cost_usd, Decimal)
    assert replayed.usage.cost_usd == recorded.usage.cost_usd


async def test_missing_cassette_raises_instead_of_calling_out(tmp_path):
    """A silent fallback to the network would make CI slow, paid and flaky."""
    player = CassetteClient(tmp_path, MODEL, mode=CassetteMode.REPLAY)

    with pytest.raises(CassetteMissError, match="Re-record"):
        await player.complete(MESSAGES)


@pytest.mark.parametrize(
    ("messages", "tools", "system"),
    [
        ([Message(role="user", content="a different question")], [TOOL], None),
        (MESSAGES, None, None),
        (MESSAGES, [TOOL], "a system prompt that was not recorded"),
    ],
    ids=["changed_prompt", "changed_tools", "changed_system"],
)
async def test_changed_request_misses_the_cassette(tmp_path, messages, tools, system):
    """The whole point: an edited prompt must not replay the previous answer."""
    recorder = CassetteClient(tmp_path, MODEL, mode=CassetteMode.RECORD, inner=FakeClient())
    await recorder.complete(MESSAGES, tools=[TOOL])

    player = CassetteClient(tmp_path, MODEL, mode=CassetteMode.REPLAY)

    with pytest.raises(CassetteMissError):
        await player.complete(messages, tools=tools, system=system)


async def test_recording_without_a_real_client_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="needs a real client"):
        CassetteClient(tmp_path, MODEL, mode=CassetteMode.RECORD)
