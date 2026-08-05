import json

import pytest

from app.llm.protocol import Message, Tool
from app.llm.providers.anthropic import AnthropicClient, AnthropicError

MODEL = "claude-sonnet-5"
TOOL = Tool(
    name="report_findings",
    description="Report audit findings",
    parameters={"type": "object", "properties": {"findings": {"type": "array"}}},
)

TOOL_USE_REPLY = {
    "content": [
        {
            "type": "tool_use",
            "id": "toolu_1",
            "name": "report_findings",
            "input": {"findings": [{"category": "unused_module"}]},
        }
    ],
    "usage": {"input_tokens": 1_000, "output_tokens": 200},
}

TEXT_REPLY = {
    "content": [{"type": "text", "text": "ok"}],
    "usage": {"input_tokens": 1, "output_tokens": 1},
}


async def test_parses_a_tool_use_block(mock_transport):
    mock_transport(TOOL_USE_REPLY)
    client = AnthropicClient(api_key="test-key", model=MODEL)

    response = await client.complete([Message(role="user", content="audit")], tools=[TOOL])

    assert len(response.tool_calls) == 1
    assert response.tool_calls[0].name == "report_findings"
    assert response.tool_calls[0].arguments == {"findings": [{"category": "unused_module"}]}
    assert response.usage.input_tokens == 1_000
    assert response.usage.output_tokens == 200


async def test_the_key_travels_in_a_header_not_the_url(mock_transport):
    captured = mock_transport(TEXT_REPLY)
    client = AnthropicClient(api_key="sk-ant-secret-value", model=MODEL)

    await client.complete([Message(role="user", content="hi")])

    assert "sk-ant-secret-value" not in str(captured[0].url)
    assert captured[0].headers["x-api-key"] == "sk-ant-secret-value"


async def test_the_api_version_is_pinned(mock_transport):
    """The API is versioned by this header. Letting it drift would change
    response shapes without any code change here."""
    captured = mock_transport(TEXT_REPLY)

    await AnthropicClient(api_key="k", model=MODEL).complete([Message(role="user", content="hi")])

    assert captured[0].headers["anthropic-version"] == "2023-06-01"


async def test_system_prompt_is_a_top_level_field(mock_transport):
    """Anthropic takes system separately, unlike OpenAI where it is a message."""
    captured = mock_transport(TEXT_REPLY)

    await AnthropicClient(api_key="k", model=MODEL).complete(
        [Message(role="user", content="hi")], system="you are an auditor"
    )

    body = json.loads(captured[0].content)
    assert body["system"] == "you are an auditor"
    assert all(entry["role"] != "system" for entry in body["messages"])


async def test_tools_are_sent_as_input_schema_and_forced(mock_transport):
    captured = mock_transport(TEXT_REPLY)

    await AnthropicClient(api_key="k", model=MODEL).complete(
        [Message(role="user", content="hi")], tools=[TOOL]
    )

    body = json.loads(captured[0].content)
    assert body["tools"][0]["input_schema"] == TOOL.parameters
    assert body["tool_choice"] == {"type": "any"}


async def test_max_tokens_is_always_sent(mock_transport):
    """Anthropic rejects a request without it, so this must never be optional."""
    captured = mock_transport(TEXT_REPLY)

    await AnthropicClient(api_key="k", model=MODEL).complete([Message(role="user", content="hi")])

    assert json.loads(captured[0].content)["max_tokens"] > 0


async def test_http_error_raises(mock_transport):
    mock_transport({"error": {"message": "overloaded"}}, status=529)

    with pytest.raises(AnthropicError, match="529"):
        await AnthropicClient(api_key="k", model=MODEL).complete(
            [Message(role="user", content="hi")]
        )


async def test_unexpected_payload_shape_raises(mock_transport):
    mock_transport({"unexpected": True})

    with pytest.raises(AnthropicError, match="Unexpected"):
        await AnthropicClient(api_key="k", model=MODEL).complete(
            [Message(role="user", content="hi")]
        )
