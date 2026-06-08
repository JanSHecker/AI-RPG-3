from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional, TypeVar

from pydantic import BaseModel, ValidationError

from model_catalog import ConfiguredModel
from providers import ProviderError, chat_completion, parse_json_object, strict_json_schema


StepUpdater = Callable[[str, str, dict[str, Any]], Awaitable[None]]
T = TypeVar("T", bound=BaseModel)
MAX_STEP_ATTEMPTS = 3

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


def _format_loc(loc: tuple[Any, ...] | list[Any]) -> str:
    parts: list[str] = []
    for entry in loc:
        if isinstance(entry, int):
            if parts:
                parts[-1] = f"{parts[-1]}[{entry}]"
            else:
                parts.append(f"[{entry}]")
        else:
            parts.append(str(entry))
    return ".".join(parts)


def _lookup_path(value: Any, loc: tuple[Any, ...] | list[Any]) -> Any:
    current = value
    for entry in loc:
        if isinstance(current, dict) and isinstance(entry, str):
            current = current.get(entry)
        elif isinstance(current, list) and isinstance(entry, int) and 0 <= entry < len(current):
            current = current[entry]
        else:
            return None
    return current


def _invalid_values_from_message(message: str) -> list[str]:
    match = re.search(r"got (\[[^\]]+\])", message)
    if not match:
        return []
    return re.findall(r"['\"]([^'\"]+)['\"]", match.group(1))


def validation_feedback(exc: Exception, payload: Optional[dict[str, Any]] = None) -> str:
    text = validation_text(exc)
    if not isinstance(exc, ValidationError):
        return text

    summaries: list[str] = []
    for error in exc.errors()[:5]:
        loc = error.get("loc", ())
        path = _format_loc(loc)
        message = str(error.get("msg") or error.get("ctx", {}).get("error") or "")
        parent = _lookup_path(payload, loc[:-1]) if payload and loc else None
        ref = parent.get("ref") if isinstance(parent, dict) else None
        input_value = error.get("input")

        summary = f"- At {path}"
        if ref:
            summary += f" for ref '{ref}'"
        summary += f": {message}"

        invalid_values = _invalid_values_from_message(message)
        if invalid_values:
            summary += f" Replace {invalid_values} with exact allowed catalog value(s)."
        elif input_value is not None:
            summary += f" Submitted value was {json.dumps(input_value, ensure_ascii=False, default=str)}."
        summaries.append(summary)

    if not summaries:
        return text
    return f"{text}\n\nCorrection summary:\n" + "\n".join(summaries)


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
        payload: Optional[dict[str, Any]] = None
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
            previous_error = validation_feedback(exc, payload)
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
