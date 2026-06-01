import asyncio

from model_catalog import ConfiguredModel
from providers import chat_completion, strict_json_schema


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {"choices": [{"message": {"content": "{\"ok\":true}"}}]}
        self.text = ""

    def json(self):
        return self._payload


class FakeAsyncClient:
    def __init__(self, recorder):
        self.recorder = recorder

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def post(self, url, headers=None, json=None):
        self.recorder["url"] = url
        self.recorder["headers"] = headers
        self.recorder["json"] = json
        return FakeResponse()


def test_strict_json_schema_closes_object_shapes():
    schema = strict_json_schema(
        "sample",
        {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"name": {"type": "string"}},
                    },
                }
            },
        },
    )

    assert schema["json_schema"]["strict"] is True
    assert schema["json_schema"]["schema"]["additionalProperties"] is False
    assert schema["json_schema"]["schema"]["properties"]["items"]["items"]["additionalProperties"] is False


def test_chat_completion_sends_strict_schema_to_openrouter(monkeypatch):
    captured = {}

    def fake_async_client(*args, **kwargs):
        return FakeAsyncClient(captured)

    monkeypatch.setattr("providers.httpx.AsyncClient", fake_async_client)

    model = ConfiguredModel(
        id="openrouter:owl-alpha",
        label="Owl Alpha",
        provider="openrouter",
        model_name="owl-alpha",
    )

    asyncio.run(
        chat_completion(
            model,
            [{"role": "user", "content": "Return JSON."}],
            temperature=0,
            response_format=strict_json_schema(
                "probe",
                {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]},
            ),
        )
    )

    assert captured["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert captured["json"]["response_format"]["type"] == "json_schema"
    assert captured["json"]["provider"] == {"require_parameters": True}


def test_chat_completion_sends_strict_schema_to_lmstudio_without_provider_routing(monkeypatch):
    captured = {}

    def fake_async_client(*args, **kwargs):
        return FakeAsyncClient(captured)

    monkeypatch.setattr("providers.httpx.AsyncClient", fake_async_client)

    model = ConfiguredModel(
        id="lmstudio:local-model",
        label="LM Studio",
        provider="lmstudio",
        model_name="local-model",
    )

    asyncio.run(
        chat_completion(
            model,
            [{"role": "user", "content": "Return JSON."}],
            temperature=0,
            response_format=strict_json_schema(
                "probe",
                {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]},
            ),
        )
    )

    assert captured["url"].endswith("/chat/completions")
    assert captured["json"]["response_format"]["type"] == "json_schema"
    assert "provider" not in captured["json"]
