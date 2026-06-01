import json
from time import perf_counter
from typing import Any, Optional

import httpx

from config import settings
from model_catalog import ConfiguredModel


class ProviderError(RuntimeError):
    pass


def _closed_json_schema(node: Any) -> Any:
    if isinstance(node, dict):
        updated = {key: _closed_json_schema(value) for key, value in node.items()}
        if updated.get("type") == "object" and "properties" in updated and "additionalProperties" not in updated:
            updated["additionalProperties"] = False
        return updated
    if isinstance(node, list):
        return [_closed_json_schema(item) for item in node]
    return node


def strict_json_schema(name: str, schema: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": name,
            "strict": True,
            "schema": _closed_json_schema(schema),
        },
    }


def extract_text_content(payload: Any) -> str:
    if isinstance(payload, str):
        return payload
    if isinstance(payload, list):
        parts: list[str] = []
        for item in payload:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and item.get("type") == "text":
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts).strip()
    return str(payload or "").strip()


def _provider_config(model: ConfiguredModel) -> tuple[str, str, dict[str, str]]:
    if model.provider == "openrouter":
        if not settings.openrouter_api_key:
            raise ProviderError("OPENROUTER_API_KEY is not configured.")
        return (
            "https://openrouter.ai/api/v1",
            settings.openrouter_api_key,
            {
                "HTTP-Referer": "https://github.com/local/ai-rpg-3",
                "X-Title": "AI RPG 3",
            },
        )
    if model.provider == "lmstudio":
        return (
            settings.lm_studio_base_url.rstrip("/"),
            settings.lm_studio_api_key,
            {},
        )
    raise ProviderError(f"Provider {model.provider} does not support LLM calls.")


async def chat_completion(
    model: ConfiguredModel,
    messages: list[dict[str, str]],
    temperature: Optional[float] = None,
    response_format: Optional[dict[str, Any]] = None,
) -> tuple[str, int]:
    base_url, api_key, extra_headers = _provider_config(model)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        **extra_headers,
    }
    body = {
        "model": model.model_name,
        "messages": messages,
        "temperature": settings.temperature if temperature is None else temperature,
    }
    if response_format is not None:
        body["response_format"] = response_format
        if model.provider == "openrouter":
            body["provider"] = {"require_parameters": True}
    started = perf_counter()
    async with httpx.AsyncClient(timeout=90) as client:
        response = await client.post(f"{base_url}/chat/completions", headers=headers, json=body)
    latency_ms = int((perf_counter() - started) * 1000)
    if response.status_code >= 400:
        raise ProviderError(f"{response.status_code}: {response.text[:500]}")
    payload = response.json()
    choices = payload.get("choices") if isinstance(payload, dict) else None
    if not choices:
        raise ProviderError("Provider returned no choices.")
    content = choices[0].get("message", {}).get("content")
    text = extract_text_content(content)
    if not text:
        raise ProviderError("Provider returned empty content.")
    return text, latency_ms


def parse_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.lower().startswith("json"):
            stripped = stripped[4:].strip()
    first = stripped.find("{")
    last = stripped.rfind("}")
    if first == -1 or last == -1 or last <= first:
        raise ProviderError("Provider did not return a JSON object.")
    return json.loads(stripped[first : last + 1])
