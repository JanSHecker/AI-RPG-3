import json
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from config import BASE_DIR, settings


class ConfiguredModel(BaseModel):
    id: str
    label: str
    provider: str
    model_name: str


def get_models_path() -> Path:
    return BASE_DIR / "models.json"


def get_active_model_path() -> Path:
    return BASE_DIR / "active_model.json"


def load_model_catalog() -> list[ConfiguredModel]:
    path = get_models_path()
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        return []
    models: list[ConfiguredModel] = []
    for item in payload:
        if isinstance(item, dict):
            models.append(ConfiguredModel.model_validate(item))
    return models


def load_active_model_id() -> Optional[str]:
    path = get_active_model_path()
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return None
    value = payload.get("model_id") or payload.get("model_name")
    return value.strip() if isinstance(value, str) and value.strip() else None


def save_active_model_id(model_id: str) -> None:
    get_active_model_path().write_text(
        json.dumps({"model_id": model_id}, indent=2),
        encoding="utf-8",
    )


def resolve_active_model() -> ConfiguredModel:
    catalog = load_model_catalog()
    active_id = load_active_model_id() or settings.model_name
    for model in catalog:
        if model.id == active_id or model.model_name == active_id:
            return model
    if catalog:
        return catalog[0]
    return ConfiguredModel(
        id="lmstudio:local-model",
        label="LM Studio Local Model",
        provider="lmstudio",
        model_name="local-model",
    )


def find_model(model_id: str) -> Optional[ConfiguredModel]:
    for model in load_model_catalog():
        if model.id == model_id:
            return model
    return None
