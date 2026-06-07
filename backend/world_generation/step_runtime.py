from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional, TypeVar

from pydantic import BaseModel, ValidationError

from model_catalog import ConfiguredModel
from providers import ProviderError, chat_completion, parse_json_object, strict_json_schema


StepUpdater = Callable[[str, str, dict[str, Any]], Awaitable[None]]
T = TypeVar("T", bound=BaseModel)
MAX_STEP_ATTEMPTS = 2

STEP_LABELS = {
    "region": "Region",
    "factions": "Factions",
    "location_plan": "Location Plan",
    "villages_places": "Villages & Places",
    "character_diagram": "Character Diagram",
    "npcs": "NPCs",
    "relationships": "Relationships",
}


@dataclass
class AttemptRecord:
    attempt: int
    status: str
    error: str = ""
    raw_response: str = ""
    latency_ms: Optional[int] = None
    parsed_payload: Optional[dict[str, Any]] = None

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "attempt": self.attempt,
            "status": self.status,
        }
        if self.error:
            payload["error"] = self.error
        if self.raw_response:
            payload["raw_response"] = self.raw_response
        if self.latency_ms is not None:
            payload["latency_ms"] = self.latency_ms
        if self.parsed_payload is not None:
            payload["parsed_payload"] = self.parsed_payload
        return payload


@dataclass
class StepTranscript:
    name: str
    label: str
    status: str = "pending"
    attempts: list[AttemptRecord] = field(default_factory=list)
    latency_ms: Optional[int] = None
    parsed_payload: Optional[dict[str, Any]] = None

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": self.name,
            "label": self.label,
            "status": self.status,
            "attempts": [attempt.to_payload() for attempt in self.attempts],
        }
        if self.latency_ms is not None:
            payload["latency_ms"] = self.latency_ms
        if self.parsed_payload is not None:
            payload["parsed_payload"] = self.parsed_payload
        return payload


class AgentFrameworkChatAdapter:
    async def complete_json(
        self,
        *,
        model: ConfiguredModel,
        step_name: str,
        schema: type[T],
        messages: list[dict[str, str]],
    ) -> tuple[str, int]:
        return await chat_completion(
            model,
            messages,
            response_format=strict_json_schema(step_name, schema.model_json_schema()),
        )


CHAT_ADAPTER = AgentFrameworkChatAdapter()


async def update_step(updater: Optional[StepUpdater], step_name: str, status: str, **payload: Any) -> None:
    if updater:
        await updater(step_name, status, payload)


def validation_text(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        return json.dumps(exc.errors(), ensure_ascii=False, default=str)[:4000]
    return str(exc)[:4000]


def transcript_payloads(transcripts: list[StepTranscript]) -> list[dict[str, Any]]:
    return [transcript.to_payload() for transcript in transcripts]


def step_label(step_name: str) -> str:
    if step_name == "world_items":
        return "World Items"
    return STEP_LABELS.get(step_name, step_name)


async def run_structured_step(
    *,
    model: ConfiguredModel,
    step_name: str,
    schema: type[T],
    build_messages: Callable[[Optional[str], Optional[str]], list[dict[str, str]]],
    updater: Optional[StepUpdater],
    transcripts: list[StepTranscript],
    initial_previous_error: Optional[str] = None,
    initial_previous_response: Optional[str] = None,
    validate_parsed: Optional[Callable[[T], None]] = None,
) -> tuple[T, StepTranscript]:
    previous_error = initial_previous_error
    previous_response = initial_previous_response
    transcript = StepTranscript(name=step_name, label=step_label(step_name))

    for attempt in range(1, MAX_STEP_ATTEMPTS + 1):
        messages = build_messages(previous_error, previous_response)
        await update_step(updater, step_name, "running", attempts=attempt, error="", prompt_messages=messages)
        text = ""
        try:
            text, latency_ms = await CHAT_ADAPTER.complete_json(
                model=model,
                step_name=step_name,
                schema=schema,
                messages=messages,
            )
            payload = parse_json_object(text)
            parsed = schema.model_validate(payload)
            if validate_parsed:
                validate_parsed(parsed)
            attempt_record = AttemptRecord(
                attempt=attempt,
                status="done",
                raw_response=text,
                latency_ms=latency_ms,
                parsed_payload=parsed.model_dump(),
            )
            transcript.status = "done"
            transcript.attempts.append(attempt_record)
            transcript.latency_ms = latency_ms
            transcript.parsed_payload = parsed.model_dump()
            transcripts.append(transcript)
            await update_step(
                updater,
                step_name,
                "done",
                attempts=attempt,
                error="",
                raw_response=text,
                parsed_payload=parsed.model_dump(),
                latency_ms=latency_ms,
            )
            return parsed, transcript
        except Exception as exc:
            previous_error = validation_text(exc)
            previous_response = text
            transcript.attempts.append(
                AttemptRecord(
                    attempt=attempt,
                    status="failed",
                    error=previous_error,
                    raw_response=previous_response,
                )
            )
            if attempt >= MAX_STEP_ATTEMPTS:
                transcript.status = "failed"
                transcripts.append(transcript)
                await update_step(
                    updater,
                    step_name,
                    "failed",
                    attempts=attempt,
                    error=previous_error,
                    raw_response=previous_response,
                )
                raise ProviderError(f"{step_label(step_name)} generation failed: {previous_error}") from exc
            await update_step(
                updater,
                step_name,
                "retrying",
                attempts=attempt,
                error=previous_error,
                raw_response=previous_response,
            )

    raise ProviderError(f"{step_label(step_name)} generation failed.")
