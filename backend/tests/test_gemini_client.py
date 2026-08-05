import httpx
import pytest

from app.llm.protocol import Message, Tool
from app.llm.providers.gemini import GeminiClient, GeminiError

TOOL = Tool(
    name="report_finding",
    description="Report one audit finding",
    parameters={"type": "object", "properties": {"summary": {"type": "string"}}},
)


@pytest.fixture
def mock_transport(monkeypatch):
    """Route every httpx.AsyncClient through a canned response.

    This exercises the adapter, our code, without a network call or an API key.
    Cassettes cover the layer above; this covers request building and parsing.
    """

    def install(payload: dict, status: int = 200) -> list[httpx.Request]:
        captured: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(status, json=payload)

        original_init = httpx.AsyncClient.__init__

        def patched_init(self, *args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(handler)
            original_init(self, *args, **kwargs)

        monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)
        return captured

    return install


async def test_parses_tool_call_and_usage(mock_transport):
    mock_transport(
        {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "functionCall": {
                                    "name": "report_finding",
                                    "args": {"summary": "unused module"},
                                }
                            }
                        ]
                    }
                }
            ],
            "usageMetadata": {"promptTokenCount": 1_000, "candidatesTokenCount": 200},
        }
    )
    client = GeminiClient(api_key="test-key", model="gemini-2.0-flash")

    response = await client.complete([Message(role="user", content="audit this")], tools=[TOOL])

    assert len(response.tool_calls) == 1
    assert response.tool_calls[0].name == "report_finding"
    assert response.tool_calls[0].arguments == {"summary": "unused module"}
    assert response.usage.input_tokens == 1_000
    assert response.usage.output_tokens == 200
    # 1000 in at $0.10/1M plus 200 out at $0.40/1M.
    assert str(response.usage.cost_usd) == "0.00018"


async def test_api_key_travels_in_header_not_url(mock_transport):
    """A key in the query string leaks into server, proxy and error logs."""
    captured = mock_transport(
        {
            "candidates": [{"content": {"parts": [{"text": "ok"}]}}],
            "usageMetadata": {"promptTokenCount": 1, "candidatesTokenCount": 1},
        }
    )
    client = GeminiClient(api_key="secret-key-value", model="gemini-2.0-flash")

    await client.complete([Message(role="user", content="hello")])

    request = captured[0]
    assert "secret-key-value" not in str(request.url)
    assert request.headers["x-goog-api-key"] == "secret-key-value"


async def test_tools_force_a_tool_call(mock_transport):
    """An auditor replying in prose has not produced a usable finding."""
    captured = mock_transport(
        {
            "candidates": [{"content": {"parts": [{"text": "ok"}]}}],
            "usageMetadata": {"promptTokenCount": 1, "candidatesTokenCount": 1},
        }
    )
    client = GeminiClient(api_key="test-key", model="gemini-2.0-flash")

    await client.complete([Message(role="user", content="hi")], tools=[TOOL])

    import json

    body = json.loads(captured[0].content)
    assert body["toolConfig"]["functionCallingConfig"]["mode"] == "ANY"


async def test_assistant_role_is_translated_for_gemini(mock_transport):
    """Gemini calls the assistant role "model"; callers above never see that."""
    captured = mock_transport(
        {
            "candidates": [{"content": {"parts": [{"text": "ok"}]}}],
            "usageMetadata": {"promptTokenCount": 1, "candidatesTokenCount": 1},
        }
    )
    client = GeminiClient(api_key="test-key", model="gemini-2.0-flash")

    await client.complete(
        [Message(role="user", content="hi"), Message(role="assistant", content="hello")]
    )

    import json

    body = json.loads(captured[0].content)
    assert [entry["role"] for entry in body["contents"]] == ["user", "model"]


async def test_http_error_raises(mock_transport):
    mock_transport({"error": {"message": "quota exceeded"}}, status=429)
    client = GeminiClient(api_key="test-key", model="gemini-2.0-flash")

    with pytest.raises(GeminiError, match="429"):
        await client.complete([Message(role="user", content="hi")])


async def test_unexpected_payload_shape_raises(mock_transport):
    """An empty Response would look to the orchestrator like an auditor finding nothing."""
    mock_transport({"candidates": []})
    client = GeminiClient(api_key="test-key", model="gemini-2.0-flash")

    with pytest.raises(GeminiError, match="Unexpected"):
        await client.complete([Message(role="user", content="hi")])
