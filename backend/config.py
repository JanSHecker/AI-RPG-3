from pathlib import Path
from typing import Optional

from pydantic import ConfigDict
from pydantic_settings import BaseSettings


BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent


class Settings(BaseSettings):
    model_config = ConfigDict(
        env_file=BASE_DIR / ".env",
        case_sensitive=False,
        protected_namespaces=("settings_",),
    )

    openrouter_api_key: Optional[str] = None
    lm_studio_base_url: str = "http://localhost:1234/v1"
    lm_studio_api_key: str = "lm-studio"
    host: str = "localhost"
    port: int = 8000
    database_path: str = "../world_data.sqlite3"
    worlds_dir: str = "../worlds"
    staple_items_path: str = "data/items/staple_items.json"
    staple_item_lore_dir: str = "data/items/lore"
    personalities_path: str = "data/personalities.json"
    primary_relationship_types_path: str = "data/primary_relationship_types.json"
    secondary_relationship_types_path: str = "data/secondary_relationship_types.json"
    model_name: str = "lmstudio:local-model"
    temperature: float = 0.7

    @property
    def database_file(self) -> Path:
        return (BASE_DIR / self.database_path).resolve()

    @property
    def worlds_path(self) -> Path:
        return (BASE_DIR / self.worlds_dir).resolve()

    @property
    def staple_items_file(self) -> Path:
        return (BASE_DIR / self.staple_items_path).resolve()

    @property
    def staple_item_lore_path(self) -> Path:
        return (BASE_DIR / self.staple_item_lore_dir).resolve()

    @property
    def personalities_file(self) -> Path:
        return (BASE_DIR / self.personalities_path).resolve()

    @property
    def primary_relationship_types_file(self) -> Path:
        return (BASE_DIR / self.primary_relationship_types_path).resolve()

    @property
    def secondary_relationship_types_file(self) -> Path:
        return (BASE_DIR / self.secondary_relationship_types_path).resolve()


settings = Settings()
