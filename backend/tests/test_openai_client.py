import json

import pytest

from app.llm.protocol import Message, Tool
from app.llm.providers.openai import OpenAIClient, OpenAIError

MODEL = "gpt-4o-mini"
TOOL = Tool(
    name="report_findings",
    description="Report audit findings",
    parameters={"type": "object", "properties": {"findings": {"type": "array"}}},
)

TOOL_CALL_REPLY = {
    "choices": [
        {
            "message": {
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "report_findings",
                            # A JSON string, not an object. This is the difference
                            # from the other two providers.
                            "arguments": '{"findings": [{"category": "unused_module"}]}',
                        },
                    }
                ],
            }
        }
    ],
    "usage": {"prompt_tokens": 1_000, "completion_tokens": 200},
}

TEXT_REPLY = {
    "choices": [{"message": {"content": "ok", "tool_calls": None}}],
    "usage": {"prompt_tokens": 1, "completion_tokens": 1},
}


async def test_tool_arguments_are_decoded_from_their_json_string(mock_transport):
    """OpenAI returns arguments as text. Callers must not have to know that."""
    mock_transport(TOOL_CALL_REPLY)

    response = await OpenAIClient(api_key="k", model=MODEL).complete(
        [Message(role="user", content="audit")], tools=[TOOL]
    )

    assert response.tool_calls[0].arguments == {"findings": [{"category": "unused_module"}]}


async def test_usage_field_names_are_translated(mock_transport):
    """OpenAI says prompt_tokens and completion_tokens where the others say input and output."""
    mock_transport(TOOL_CALL_REPLY)

    response = await OpenAIClient(api_key="k", model=MODEL).complete(
        [Message(role="user", content="audit")]
    )

    assert response.usage.input_tokens == 1_000
    assert response.usage.output_tokens == 200


async def test_the_key_travels_in_a_header_not_the_url(mock_transport):
    captured = mock_transport(TEXT_REPLY)

    await OpenAIClient(api_key="sk-secret-value", model=MODEL).complete(
        [Message(role="user", content="hi")]
    )

    assert "sk-secret-value" not in str(captured[0].url)
    assert captured[0].headers["Authorization"] == "Bearer sk-secret-value"


async def test_system_prompt_becomes_the_first_message(mock_transport):
    """Unlike Anthropic, where system is a top-level field."""
    captured = mock_transport(TEXT_REPLY)

    await OpenAIClient(api_key="k", model=MODEL).complete(
        [Message(role="user", content="hi")], system="you are an auditor"
    )

    messages = json.loads(captured[0].content)["messages"]
    assert messages[0] == {"role": "system", "content": "you are an auditor"}
    assert messages[1]["role"] == "user"


async def test_tools_are_wrapped_in_a_function_envelope_and_forced(mock_transport):
    captured = mock_transport(TEXT_REPLY)

    await OpenAIClient(api_key="k", model=MODEL).complete(
        [Message(role="user", content="hi")], tools=[TOOL]
    )

    body = json.loads(captured[0].content)
    assert body["tools"][0]["type"] == "function"
    assert body["tools"][0]["function"]["parameters"] == TOOL.parameters
    assert body["tool_choice"] == "required"


async def test_malformed_tool_arguments_raise(mock_transport):
    """Better a loud failure than a finding built from half-parsed arguments."""
    mock_transport(
        {
            "choices": [
                {
                    "message": {
                        "content": None,
                        "tool_calls": [
                            {"function": {"name": "report_findings", "arguments": "{not json"}}
                        ],
                    }
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        }
    )

    with pytest.raises(OpenAIError, match="not valid JSON"):
        await OpenAIClient(api_key="k", model=MODEL).complete(
            [Message(role="user", content="hi")], tools=[TOOL]
        )


async def test_http_error_raises(mock_transport):
    mock_transport({"error": {"message": "rate limited"}}, status=429)

    with pytest.raises(OpenAIError, match="429"):
        await OpenAIClient(api_key="k", model=MODEL).complete([Message(role="user", content="hi")])


async def test_unexpected_payload_shape_raises(mock_transport):
    mock_transport({"choices": []})

    with pytest.raises(OpenAIError, match="Unexpected"):
        await OpenAIClient(api_key="k", model=MODEL).complete([Message(role="user", content="hi")])
