import httpx
import pytest

from app.llm.protocol import Message, Tool
from app.llm.providers.gemini import GeminiClient, GeminiError

MODEL = "gemini-flash-latest"
TOOL = Tool(
    name="report_finding",
    description="Report one audit finding",
    parameters={"type": "object", "properties": {"summary": {"type": "string"}}},
)


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


async def test_a_rate_limited_call_is_retried(monkeypatch):
    """Running three auditors at once hits per-minute limits routinely. That is
    the normal cost of concurrency, not a failure worth surfacing."""
    import asyncio

    slept: list[float] = []

    async def record_sleep(seconds):
        slept.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", record_sleep)
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(
                429,
                json={"error": {"message": "quota exceeded", "details": [{"retryDelay": "1.2s"}]}},
            )
        return httpx.Response(
            200,
            json={
                "candidates": [{"content": {"parts": [{"text": "ok"}]}}],
                "usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 2},
            },
        )

    original_init = httpx.AsyncClient.__init__

    def patched_init(self, *args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        original_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)

    response = await GeminiClient(api_key="k", model=MODEL).complete(
        [Message(role="user", content="hi")]
    )

    assert response.text == "ok"
    assert calls["n"] == 2, "the call should have been retried once"
    assert slept == [1.2], "the provider's own retryDelay should be honoured"


async def test_a_persistent_rate_limit_gives_a_readable_error(mock_transport, monkeypatch):
    """The raw body is kilobytes of quota metadata. A wall of JSON in front of
    someone reading why their run failed helps nobody."""
    import asyncio

    async def no_sleep(seconds):
        return None

    monkeypatch.setattr(asyncio, "sleep", no_sleep)
    mock_transport(
        {
            "error": {
                "message": "You exceeded your current quota. " + "x" * 5_000,
                "details": [{"@type": "QuotaFailure", "violations": [{"quotaId": "a"}]}],
            }
        },
        status=429,
    )

    with pytest.raises(GeminiError) as caught:
        await GeminiClient(api_key="k", model=MODEL).complete([Message(role="user", content="hi")])

    message = str(caught.value)
    assert "You exceeded your current quota" in message
    assert len(message) < 600, "the error must not carry the whole response body"
    assert "QuotaFailure" not in message


@pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
async def test_transient_provider_failures_are_retried(monkeypatch, status):
    """503 is the provider saying "temporary, try again". A real run threw away
    two auditors because only 429 was retried."""
    import asyncio

    async def no_sleep(seconds):
        return None

    monkeypatch.setattr(asyncio, "sleep", no_sleep)
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(status, json={"error": {"message": "try again"}})
        return httpx.Response(
            200,
            json={
                "candidates": [{"content": {"parts": [{"text": "ok"}]}}],
                "usageMetadata": {"promptTokenCount": 1, "candidatesTokenCount": 1},
            },
        )

    original_init = httpx.AsyncClient.__init__

    def patched_init(self, *args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        original_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)

    response = await GeminiClient(api_key="k", model=MODEL).complete(
        [Message(role="user", content="hi")]
    )

    assert response.text == "ok"
    assert calls["n"] == 2, f"{status} should have been retried"


async def test_a_client_error_is_not_retried(mock_transport):
    """A 400 means the request was wrong. Retrying it wastes time and quota."""
    captured = mock_transport({"error": {"message": "bad request"}}, status=400)

    with pytest.raises(GeminiError, match="400"):
        await GeminiClient(api_key="k", model=MODEL).complete([Message(role="user", content="hi")])

    assert len(captured) == 1
