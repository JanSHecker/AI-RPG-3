import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from config import settings


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS worlds (
    id TEXT PRIMARY KEY,
    prompt TEXT NOT NULL,
    title TEXT NOT NULL,
    seed INTEGER NOT NULL,
    status TEXT NOT NULL,
    provider TEXT NOT NULL,
    model_name TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS regions (
    id TEXT PRIMARY KEY,
    world_id TEXT NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    summary TEXT NOT NULL,
    climate TEXT NOT NULL,
    danger_profile TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS factions (
    id TEXT PRIMARY KEY,
    world_id TEXT NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    goals TEXT NOT NULL,
    public_reputation TEXT NOT NULL,
    power_level INTEGER NOT NULL,
    home_place_id TEXT
);

CREATE TABLE IF NOT EXISTS places (
    id TEXT PRIMARY KEY,
    world_id TEXT NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
    region_id TEXT NOT NULL REFERENCES regions(id) ON DELETE CASCADE,
    parent_place_id TEXT,
    name TEXT NOT NULL,
    place_type TEXT NOT NULL,
    summary TEXT NOT NULL,
    x INTEGER NOT NULL,
    y INTEGER NOT NULL,
    terrain TEXT NOT NULL,
    danger_level INTEGER NOT NULL,
    population_estimate INTEGER NOT NULL,
    controlling_faction_id TEXT
);

CREATE TABLE IF NOT EXISTS npcs (
    id TEXT PRIMARY KEY,
    world_id TEXT NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    age INTEGER NOT NULL,
    personality TEXT NOT NULL,
    job TEXT NOT NULL,
    faction_id TEXT,
    home_place_id TEXT NOT NULL,
    current_place_id TEXT NOT NULL,
    status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS relationships (
    id TEXT PRIMARY KEY,
    world_id TEXT NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
    source_type TEXT NOT NULL,
    source_id TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    description TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS world_items (
    id TEXT PRIMARY KEY,
    world_id TEXT NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    rarity TEXT NOT NULL,
    summary TEXT NOT NULL,
    tags_json TEXT NOT NULL DEFAULT '[]',
    value INTEGER NOT NULL,
    weight REAL NOT NULL,
    stackable INTEGER NOT NULL,
    consumable INTEGER NOT NULL,
    equip_slot TEXT,
    effect_summary TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS npc_inventory_items (
    id TEXT PRIMARY KEY,
    world_id TEXT NOT NULL REFERENCES worlds(id) ON DELETE CASCADE,
    npc_id TEXT NOT NULL REFERENCES npcs(id) ON DELETE CASCADE,
    item_source_type TEXT NOT NULL,
    item_id TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    condition TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS generation_runs (
    id TEXT PRIMARY KEY,
    world_id TEXT,
    provider TEXT NOT NULL,
    model_name TEXT NOT NULL,
    prompt TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    latency_ms INTEGER,
    error TEXT NOT NULL DEFAULT '',
    raw_response TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS generation_jobs (
    id TEXT PRIMARY KEY,
    prompt TEXT NOT NULL,
    provider TEXT NOT NULL,
    model_name TEXT NOT NULL,
    status TEXT NOT NULL,
    world_id TEXT,
    error TEXT NOT NULL DEFAULT '',
    resume_step_name TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS generation_job_steps (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES generation_jobs(id) ON DELETE CASCADE,
    step_name TEXT NOT NULL,
    label TEXT NOT NULL,
    status TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    error TEXT NOT NULL DEFAULT '',
    prompt_messages TEXT NOT NULL DEFAULT '[]',
    raw_response TEXT NOT NULL DEFAULT '',
    parsed_payload TEXT NOT NULL DEFAULT '',
    latency_ms INTEGER,
    started_at TEXT,
    finished_at TEXT,
    UNIQUE(job_id, step_name)
);

CREATE TABLE IF NOT EXISTS play_sessions (
    id TEXT PRIMARY KEY,
    world_id TEXT NOT NULL UNIQUE REFERENCES worlds(id) ON DELETE CASCADE,
    character_name TEXT NOT NULL,
    character_summary TEXT NOT NULL,
    current_place_id TEXT NOT NULL,
    mode TEXT NOT NULL DEFAULT 'default',
    conversation_npc_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS play_messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES play_sessions(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    npc_id TEXT,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_places_world ON places(world_id);
CREATE INDEX IF NOT EXISTS idx_npcs_world ON npcs(world_id);
CREATE INDEX IF NOT EXISTS idx_factions_world ON factions(world_id);
CREATE INDEX IF NOT EXISTS idx_relationships_world ON relationships(world_id);
CREATE INDEX IF NOT EXISTS idx_world_items_world ON world_items(world_id);
CREATE INDEX IF NOT EXISTS idx_npc_inventory_world ON npc_inventory_items(world_id);
CREATE INDEX IF NOT EXISTS idx_npc_inventory_npc ON npc_inventory_items(npc_id);
CREATE INDEX IF NOT EXISTS idx_generation_jobs_status ON generation_jobs(status, updated_at);
CREATE INDEX IF NOT EXISTS idx_generation_job_steps_job ON generation_job_steps(job_id);
CREATE INDEX IF NOT EXISTS idx_play_sessions_world ON play_sessions(world_id);
CREATE INDEX IF NOT EXISTS idx_play_messages_session ON play_messages(session_id, created_at);
"""


def connect(path: Optional[Path] = None) -> sqlite3.Connection:
    db_path = path or settings.database_file
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(path: Optional[Path] = None) -> None:
    with connect(path) as conn:
        conn.executescript(SCHEMA)
        generation_job_columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(generation_jobs)").fetchall()
        }
        if "resume_step_name" not in generation_job_columns:
            conn.execute("ALTER TABLE generation_jobs ADD COLUMN resume_step_name TEXT")

        generation_step_columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(generation_job_steps)").fetchall()
        }
        if "prompt_messages" not in generation_step_columns:
            conn.execute("ALTER TABLE generation_job_steps ADD COLUMN prompt_messages TEXT NOT NULL DEFAULT '[]'")

        play_session_columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(play_sessions)").fetchall()
        }
        if "mode" not in play_session_columns:
            conn.execute("DELETE FROM play_sessions")
            conn.execute("ALTER TABLE play_sessions ADD COLUMN mode TEXT NOT NULL DEFAULT 'default'")
        if "conversation_npc_id" not in play_session_columns:
            conn.execute("DELETE FROM play_sessions")
            conn.execute("ALTER TABLE play_sessions ADD COLUMN conversation_npc_id TEXT")


@contextmanager
def db_session(path: Optional[Path] = None) -> Iterator[sqlite3.Connection]:
    conn = connect(path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
