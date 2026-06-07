import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

from config import settings


def _validate_personality_payload(payload: object) -> list[str]:
    if not isinstance(payload, list):
        raise ValueError("Personality catalog must be a JSON list.")

    cleaned: list[str] = []
    seen: set[str] = set()
    for index, entry in enumerate(payload):
        if not isinstance(entry, str):
            raise ValueError(f"Personality at index {index} must be a string.")
        value = entry.strip()
        if not value:
            raise ValueError(f"Personality at index {index} must not be empty.")
        if value in seen:
            raise ValueError(f"Duplicate personality found: {value}.")
        seen.add(value)
        cleaned.append(value)

    if not cleaned:
        raise ValueError("Personality catalog must contain at least one entry.")
    return cleaned


@lru_cache(maxsize=1)
def _load_default_personality_catalog() -> list[str]:
    path = settings.personalities_file
    if not path.exists():
        raise ValueError(f"Personality catalog file does not exist: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    return _validate_personality_payload(payload)


def load_personality_catalog(path: Optional[Path] = None) -> list[str]:
    if path is None:
        return list(_load_default_personality_catalog())
    if not path.exists():
        raise ValueError(f"Personality catalog file does not exist: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    return _validate_personality_payload(payload)
