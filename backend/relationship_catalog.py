import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

from config import settings


def _validate_relationship_payload(payload: object) -> list[str]:
    if not isinstance(payload, list):
        raise ValueError("Relationship type catalog must be a JSON list.")

    cleaned: list[str] = []
    seen: set[str] = set()
    for index, entry in enumerate(payload):
        if not isinstance(entry, str):
            raise ValueError(f"Relationship type at index {index} must be a string.")
        value = entry.strip()
        if not value:
            raise ValueError(f"Relationship type at index {index} must not be empty.")
        if value in seen:
            raise ValueError(f"Duplicate relationship type found: {value}.")
        seen.add(value)
        cleaned.append(value)

    if not cleaned:
        raise ValueError("Relationship type catalog must contain at least one entry.")
    return cleaned


def _load_relationship_file(path: Path, label: str) -> list[str]:
    if not path.exists():
        raise ValueError(f"{label} relationship type catalog file does not exist: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    return _validate_relationship_payload(payload)


def _ensure_no_overlap(primary: list[str], secondary: list[str]) -> None:
    overlap = sorted(set(primary) & set(secondary))
    if overlap:
        raise ValueError(f"Relationship type catalogs must not overlap: {overlap}.")


@lru_cache(maxsize=1)
def _load_default_primary_relationship_catalog() -> list[str]:
    return _load_relationship_file(settings.primary_relationship_types_file, "Primary")


@lru_cache(maxsize=1)
def _load_default_secondary_relationship_catalog() -> list[str]:
    return _load_relationship_file(settings.secondary_relationship_types_file, "Secondary")


@lru_cache(maxsize=1)
def _load_default_relationship_catalog() -> list[str]:
    primary = _load_default_primary_relationship_catalog()
    secondary = _load_default_secondary_relationship_catalog()
    _ensure_no_overlap(primary, secondary)
    return [*primary, *secondary]


def load_primary_relationship_catalog(path: Optional[Path] = None) -> list[str]:
    if path is None:
        return list(_load_default_primary_relationship_catalog())
    return _load_relationship_file(path, "Primary")


def load_secondary_relationship_catalog(path: Optional[Path] = None) -> list[str]:
    if path is None:
        return list(_load_default_secondary_relationship_catalog())
    return _load_relationship_file(path, "Secondary")


def load_relationship_catalog(primary_path: Optional[Path] = None, secondary_path: Optional[Path] = None) -> list[str]:
    if primary_path is None and secondary_path is None:
        return list(_load_default_relationship_catalog())
    primary = load_primary_relationship_catalog(primary_path or settings.primary_relationship_types_file)
    secondary = load_secondary_relationship_catalog(secondary_path or settings.secondary_relationship_types_file)
    _ensure_no_overlap(primary, secondary)
    return [*primary, *secondary]
