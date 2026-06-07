import asyncio
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from config import settings
from database import db_session, init_db
from item_catalog import load_staple_catalog, seed_npc_inventory
from main import app
from model_catalog import ConfiguredModel, find_model, load_model_catalog, resolve_active_model, save_active_model_id
from world_generation_jobs import RUNNING_TASKS, get_generation_job, restart_generation_job, update_job_step
from world_generation.schemas import (
    FACTION_COUNT,
    FACTION_LOCATION_COUNT,
    NPC_COUNT,
    PERSONALITIES,
    PLACE_COUNT,
    PLACE_TYPES,
    RELATIONSHIP_COUNT,
    RELATIONSHIP_TYPES,
    FactionDraft,
    NpcDraft,
    PlaceDraft,
    RegionDraft,
    RelationshipDraft,
    WorldDraft,
)
from world_generator import insert_world
from world_repository import list_table, read_lore, safe_lore_path


def sample_model() -> ConfiguredModel:
    return ConfiguredModel(id="lmstudio:local-model", label="LM Studio", provider="lmstudio", model_name="local-model")


def sample_personalities(idx: int) -> list[str]:
    return [PERSONALITIES[(idx + offset) % len(PERSONALITIES)] for offset in range(3)]


def test_npc_personality_aliases_are_canonicalized():
    npc = NpcDraft(
        ref="npc-alias-test",
        name="Alias Test",
        age=30,
        personality=["steady", "pragmatic", "sensitive"],
        job="warden",
        faction_ref=None,
        home_place_ref="place-1",
        current_place_ref="place-1",
        status="active",
        lore="Alias test lore.",
    )

    assert npc.personality == ["stable", "pragmatic", "empathetic"]


def sample_world_draft() -> WorldDraft:
    places = [
        PlaceDraft(
            ref=f"place-{idx + 1}",
            name=f"Place {idx + 1}",
            place_type=PLACE_TYPES[idx % len(PLACE_TYPES)],
            summary=f"Summary for place {idx + 1}",
            x=(10 + idx * 7) % 101,
            y=(15 + idx * 8) % 101,
            terrain="hills",
            danger_level=(idx % 5) + 1,
            population_estimate=0 if idx in {3, 4, 5, 6} else 200 + idx * 50,
            controlling_faction_ref=f"faction-{(idx // FACTION_LOCATION_COUNT) + 1}" if idx < FACTION_COUNT * FACTION_LOCATION_COUNT else None,
            parent_place_ref=None,
            lore=f"# Place {idx + 1}\n\nLore for place {idx + 1}.",
        )
        for idx in range(PLACE_COUNT)
    ]
    factions = [
        FactionDraft(
            ref=f"faction-{idx + 1}",
            name=f"Faction {idx + 1}",
            type="council",
            goals=f"Goal {idx + 1}",
            public_reputation="steady",
            power_level=(idx % 5) + 1,
            home_place_ref=None,
            required_places=[
                {
                    "name": f"Faction {idx + 1} Hall",
                    "description": f"A required home base for faction {idx + 1}.",
                }
            ],
            required_characters=[
                {
                    "name": f"Faction {idx + 1} Envoy",
                    "description": f"A required representative for faction {idx + 1}.",
                }
            ],
            requirement_relationships=[
                {
                    "source_kind": "place",
                    "source_name": f"Faction {idx + 1} Hall",
                    "target_kind": "character",
                    "target_name": f"Faction {idx + 1} Envoy",
                    "relation_type": "base of operations",
                    "description": f"The envoy operates from the faction {idx + 1} hall.",
                }
            ],
            lore=f"# Faction {idx + 1}\n\nLore for faction {idx + 1}.",
        )
        for idx in range(FACTION_COUNT)
    ]
    npcs = [
        NpcDraft(
            ref=f"npc-{idx + 1:03d}",
            name=f"NPC {idx + 1}",
            age=20 + (idx % 30),
            personality=sample_personalities(idx),
            job="warden",
            faction_ref=factions[idx % FACTION_COUNT].ref if idx % 5 else None,
            home_place_ref=places[idx % PLACE_COUNT].ref,
            current_place_ref=places[(idx + 1) % PLACE_COUNT].ref,
            status="active",
            lore=f"# NPC {idx + 1}\n\nLore for NPC {idx + 1}.",
        )
        for idx in range(NPC_COUNT)
    ]
    relationships = [
        RelationshipDraft(
            ref=f"rel-faction-{idx + 1}",
            source_type="faction",
            source_ref=factions[idx].ref,
            target_type="faction",
            target_ref=factions[(idx + 1) % FACTION_COUNT].ref,
            relation_type=RELATIONSHIP_TYPES[RELATIONSHIP_TYPES.index("rivalry")],
            description=f"Faction {idx + 1} competes with faction {(idx + 1) % FACTION_COUNT + 1}.",
        )
        for idx in range(FACTION_COUNT)
    ]
    relationships.extend(
        RelationshipDraft(
            ref=f"rel-npc-{idx + 1}",
            source_type="npc",
            source_ref=npcs[idx].ref,
            target_type="place",
            target_ref=npcs[idx].current_place_ref,
            relation_type=RELATIONSHIP_TYPES[RELATIONSHIP_TYPES.index("local tie")],
            description=f"NPC {idx + 1} is closely tied to their current place.",
        )
        for idx in range(RELATIONSHIP_COUNT - FACTION_COUNT)
    )
    return WorldDraft(
        title="Test Frontier",
        region=RegionDraft(
            name="The Test Frontier",
            description="A generated test frontier.",
        ),
        places=places,
        factions=factions,
        npcs=npcs,
        relationships=relationships,
    )


def insert_generation_job(job_id: str, status: str, prompt: str = "A test job") -> None:
    with db_session() as conn:
        conn.execute(
            """
            INSERT INTO generation_jobs
                (id, prompt, provider, model_name, status, world_id, error, created_at, updated_at, started_at, finished_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                prompt,
                "lmstudio",
                "local-model",
                status,
                None,
                "",
                "2026-05-30T00:00:00+00:00",
                "2026-05-30T00:00:00+00:00",
                None,
                None,
            ),
        )


def count_rows(db_path: Path, table: str) -> int:
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        conn.close()


def test_schema_initializes_blank_database(tmp_path):
    db_path = tmp_path / "world.sqlite3"
    init_db(db_path)
    assert db_path.exists()
    assert count_rows(db_path, "worlds") == 0


def test_schema_initializes_play_tables(tmp_path):
    db_path = tmp_path / "world.sqlite3"
    init_db(db_path)

    conn = sqlite3.connect(db_path)
    try:
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
        }
        columns = {row[1] for row in conn.execute("PRAGMA table_info(play_sessions)").fetchall()}
    finally:
        conn.close()

    assert "play_sessions" in tables
    assert "play_messages" in tables
    assert {"mode", "conversation_npc_id"}.issubset(columns)


def test_play_session_schema_migration_resets_existing_sessions(tmp_path, monkeypatch):
    db_path = tmp_path / "world.sqlite3"
    monkeypatch.setattr(settings, "database_path", str(db_path))
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(
            """
            CREATE TABLE worlds (
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
            CREATE TABLE play_sessions (
                id TEXT PRIMARY KEY,
                world_id TEXT NOT NULL UNIQUE REFERENCES worlds(id) ON DELETE CASCADE,
                character_name TEXT NOT NULL,
                character_summary TEXT NOT NULL,
                current_place_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE play_messages (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL REFERENCES play_sessions(id) ON DELETE CASCADE,
                kind TEXT NOT NULL,
                npc_id TEXT,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        conn.execute(
            "INSERT INTO worlds VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("world-old", "prompt", "Old World", 1, "done", "test", "test", "now", "now"),
        )
        conn.execute(
            "INSERT INTO play_sessions VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("play-old", "world-old", "Name", "Summary", "place-old", "now", "now"),
        )
        conn.execute(
            "INSERT INTO play_messages VALUES (?, ?, ?, ?, ?, ?)",
            ("msg-old", "play-old", "system", None, "old", "now"),
        )
        conn.commit()
    finally:
        conn.close()

    init_db()

    conn = sqlite3.connect(db_path)
    try:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(play_sessions)").fetchall()}
        session_count = conn.execute("SELECT COUNT(*) FROM play_sessions").fetchone()[0]
        message_count = conn.execute("SELECT COUNT(*) FROM play_messages").fetchone()[0]
    finally:
        conn.close()

    assert {"mode", "conversation_npc_id"}.issubset(columns)
    assert session_count == 0
    assert message_count == 0


def test_schema_adds_prompt_messages_to_existing_job_steps_table(tmp_path):
    db_path = tmp_path / "world.sqlite3"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE generation_job_steps (
                id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL,
                step_name TEXT NOT NULL,
                label TEXT NOT NULL,
                status TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                error TEXT NOT NULL DEFAULT '',
                raw_response TEXT NOT NULL DEFAULT '',
                parsed_payload TEXT NOT NULL DEFAULT '',
                latency_ms INTEGER,
                started_at TEXT,
                finished_at TEXT,
                UNIQUE(job_id, step_name)
            )
            """
        )
        conn.commit()
    finally:
        conn.close()

    init_db(db_path)

    conn = sqlite3.connect(db_path)
    try:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(generation_job_steps)").fetchall()}
    finally:
        conn.close()

    assert "prompt_messages" in columns


def test_generation_job_step_update_inserts_dynamic_batch_steps(tmp_path, monkeypatch):
    db_path = tmp_path / "world.sqlite3"
    monkeypatch.setattr(settings, "database_path", str(db_path))
    init_db()
    insert_generation_job("gen-dynamic", "running")

    asyncio.run(
        update_job_step(
            "gen-dynamic",
            "places_batch_faction_1",
            "running",
            {"attempts": 1, "error": "", "label": "Ashen Guard Locations"},
        )
    )

    with db_session() as conn:
        row = conn.execute(
            "SELECT step_name, label, status, attempts FROM generation_job_steps WHERE job_id = ?",
            ("gen-dynamic",),
        ).fetchone()

    assert row["step_name"] == "places_batch_faction_1"
    assert row["label"] == "Ashen Guard Locations"
    assert row["status"] == "running"
    assert row["attempts"] == 1


def test_generation_job_step_update_stores_prompt_messages(tmp_path, monkeypatch):
    db_path = tmp_path / "world.sqlite3"
    monkeypatch.setattr(settings, "database_path", str(db_path))
    init_db()
    insert_generation_job("gen-prompts", "running")
    messages = [
        {"role": "system", "content": "Create valid JSON."},
        {"role": "user", "content": "World prompt:\nA glass desert"},
    ]

    asyncio.run(
        update_job_step(
            "gen-prompts",
            "region",
            "running",
            {"attempts": 1, "error": "", "prompt_messages": messages},
        )
    )

    job = get_generation_job("gen-prompts")

    assert job is not None
    assert job["steps"][0]["prompt_messages"] == messages


def test_restart_generation_job_resets_failed_job(tmp_path, monkeypatch):
    db_path = tmp_path / "world.sqlite3"
    monkeypatch.setattr(settings, "database_path", str(db_path))
    init_db()
    insert_generation_job("gen-failed", "failed")
    asyncio.run(
        update_job_step(
            "gen-failed",
            "region",
            "failed",
            {
                "attempts": 2,
                "error": "Bad JSON",
                "prompt_messages": [{"role": "user", "content": "Bad prompt"}],
                "raw_response": "{oops}",
                "parsed_payload": {"bad": True},
            },
        )
    )
    with db_session() as conn:
        conn.execute("UPDATE generation_jobs SET error = ?, started_at = ?, finished_at = ? WHERE id = ?", (
            "Bad JSON",
            "2026-05-30T00:00:01+00:00",
            "2026-05-30T00:00:02+00:00",
            "gen-failed",
        ))

    restart_model = ConfiguredModel(
        id="openrouter:restart-model",
        label="Restart Model",
        provider="openrouter",
        model_name="restart-model",
    )
    job = restart_generation_job("gen-failed", restart_model)

    assert job is not None
    assert job["status"] == "pending"
    assert job["provider"] == "openrouter"
    assert job["model_name"] == "restart-model"
    assert job["error"] == ""
    assert job["started_at"] is None
    assert job["finished_at"] is None
    assert job["steps"][0]["status"] == "pending"
    assert job["steps"][0]["attempts"] == 0
    assert job["steps"][0]["error"] == ""
    assert job["steps"][0]["prompt_messages"] == []
    assert job["steps"][0]["raw_response"] == ""
    assert job["steps"][0]["parsed_payload"] == ""


def test_restart_generation_job_rejects_non_failed_jobs(tmp_path, monkeypatch):
    db_path = tmp_path / "world.sqlite3"
    monkeypatch.setattr(settings, "database_path", str(db_path))
    init_db()
    insert_generation_job("gen-done", "done")

    with pytest.raises(ValueError):
        restart_generation_job("gen-done", sample_model())


def test_restart_generation_job_api_uses_requested_model(tmp_path, monkeypatch):
    import api

    db_path = tmp_path / "world.sqlite3"
    worlds_path = tmp_path / "worlds"
    monkeypatch.setattr(settings, "database_path", str(db_path))
    monkeypatch.setattr(settings, "worlds_dir", str(worlds_path))
    RUNNING_TASKS.clear()
    init_db()
    insert_generation_job("gen-failed-api", "failed")

    async def skip_task_startup():
        return None

    monkeypatch.setattr(api, "ensure_generation_tasks", skip_task_startup)

    with TestClient(app) as client:
        response = client.post(
            "/generation-jobs/gen-failed-api/restart",
            json={"model_id": "openrouter:minimax/minimax-m2.5:free"},
        )

    assert response.status_code == 202
    job = response.json()["job"]
    assert job["status"] == "pending"
    assert job["provider"] == "openrouter"
    assert job["model_name"] == "minimax/minimax-m2.5:free"


def test_restart_generation_job_api_uses_requested_query_model(tmp_path, monkeypatch):
    import api

    db_path = tmp_path / "world.sqlite3"
    worlds_path = tmp_path / "worlds"
    monkeypatch.setattr(settings, "database_path", str(db_path))
    monkeypatch.setattr(settings, "worlds_dir", str(worlds_path))
    RUNNING_TASKS.clear()
    init_db()
    insert_generation_job("gen-failed-query-api", "failed")

    async def skip_task_startup():
        return None

    monkeypatch.setattr(api, "ensure_generation_tasks", skip_task_startup)

    with TestClient(app) as client:
        response = client.post(
            "/generation-jobs/gen-failed-query-api/restart",
            params={"model_id": "openrouter:google/gemma-4-26b-a4b-it:free"},
        )

    assert response.status_code == 202
    job = response.json()["job"]
    assert job["status"] == "pending"
    assert job["provider"] == "openrouter"
    assert job["model_name"] == "google/gemma-4-26b-a4b-it:free"


def test_world_insert_inserts_structured_data_and_lore(tmp_path):
    db_path = tmp_path / "world.sqlite3"
    worlds_path = tmp_path / "worlds"
    init_db(db_path)
    model = sample_model()
    draft = sample_world_draft()

    world_id = insert_world("A bitter borderland around a broken imperial road", model, draft, "{}", 0, db_path, worlds_path)

    assert count_rows(db_path, "worlds") == 1
    assert count_rows(db_path, "places") >= 8
    assert count_rows(db_path, "npcs") >= 20
    assert count_rows(db_path, "npc_inventory_items") >= 20
    assert (worlds_path / world_id / "region.md").exists()
    assert any((worlds_path / world_id / "places").iterdir())
    assert (worlds_path / world_id / "items").exists()


def test_invalid_links_are_atomic(tmp_path):
    db_path = tmp_path / "world.sqlite3"
    worlds_path = tmp_path / "worlds"
    init_db(db_path)
    model = sample_model()
    draft = sample_world_draft()
    draft.npcs[0].home_place_ref = "missing-place"

    with pytest.raises(ValueError):
        insert_world("A haunted salt marsh", model, draft, "{}", 0, db_path, worlds_path)

    assert count_rows(db_path, "worlds") == 0
    assert not worlds_path.exists()


def test_model_catalog_and_active_model_round_trip():
    models = load_model_catalog()
    assert any(model.provider == "openrouter" for model in models)
    assert any(model.provider == "lmstudio" for model in models)
    save_active_model_id("lmstudio:local-model")
    assert resolve_active_model().id == "lmstudio:local-model"
    assert find_model("lmstudio:local-model") is not None


def test_lore_path_rejects_unknown_entity_type():
    with pytest.raises(ValueError):
        safe_lore_path("world-1", "bad", "../x")


def test_invalid_inventory_links_are_atomic(tmp_path):
    db_path = tmp_path / "world.sqlite3"
    worlds_path = tmp_path / "worlds"
    init_db(db_path)
    model = sample_model()
    draft = sample_world_draft()
    inventory = seed_npc_inventory("world-test", draft.npcs, 1234)
    inventory[0].item_id = "missing-staple-item"

    with pytest.raises(ValueError):
        insert_world("A trade road through black pine country", model, draft, "{}", 0, db_path, worlds_path, inventory_items=inventory)

    assert count_rows(db_path, "worlds") == 0
    assert not worlds_path.exists()


def test_staple_catalog_loads_with_lore():
    items = load_staple_catalog()
    assert len(items) >= 10
    assert all(item.lore_path and item.lore_path.exists() for item in items)


def test_read_staple_lore_from_shared_catalog():
    content = read_lore("world-unused", "staple-items", "staple-ration-pack")
    assert content is not None
    assert "Ration Pack" in content


def test_create_world_returns_generation_job_and_completes_pipeline(tmp_path, monkeypatch):
    import world_generation_jobs

    db_path = tmp_path / "world.sqlite3"
    worlds_path = tmp_path / "worlds"
    monkeypatch.setattr(settings, "database_path", str(db_path))
    monkeypatch.setattr(settings, "worlds_dir", str(worlds_path))
    RUNNING_TASKS.clear()
    init_db()

    async def fake_build_world_draft(prompt: str, model: ConfiguredModel, updater=None):
        draft = sample_world_draft()
        if updater:
            step_payloads = {
                "region": {"title": draft.title, "region": draft.region.model_dump()},
                "factions": {"factions": [faction.model_dump() for faction in draft.factions]},
                "location_plan": {"slots": []},
                "villages_places": {"places": [place.model_dump() for place in draft.places]},
                "character_diagram": {"slots": []},
                "npcs": {"npcs": [npc.model_dump() for npc in draft.npcs]},
                "relationships": {"relationships": [rel.model_dump() for rel in draft.relationships]},
            }
            for step_name, parsed_payload in step_payloads.items():
                await updater(step_name, "running", {"attempts": 1, "error": ""})
                await updater(step_name, "done", {"attempts": 1, "error": "", "parsed_payload": parsed_payload, "latency_ms": 0})
        return draft, "{}", 0

    monkeypatch.setattr(world_generation_jobs, "build_world_draft", fake_build_world_draft)

    with TestClient(app) as client:
        response = client.post(
            "/worlds",
            json={
                "prompt": "A cold frontier of market villages",
                "model_id": "lmstudio:local-model",
            },
        )
        assert response.status_code == 202
        job = response.json()["job"]
        assert job["status"] in {"pending", "running", "done"}
        assert len(job["steps"]) == 7

        completed = None
        for _ in range(20):
            payload = client.get(f"/generation-jobs/{job['id']}").json()["job"]
            if payload["status"] in {"done", "failed"}:
                completed = payload
                break

        assert completed is not None
        assert completed["status"] == "done"
        assert completed["world_id"]
        assert all(step["status"] == "done" for step in completed["steps"])
        assert len(client.get("/worlds").json()["worlds"]) == 1


def test_generation_job_cleanup_endpoints_clear_finished_and_active(tmp_path, monkeypatch):
    db_path = tmp_path / "world.sqlite3"
    worlds_path = tmp_path / "worlds"
    monkeypatch.setattr(settings, "database_path", str(db_path))
    monkeypatch.setattr(settings, "worlds_dir", str(worlds_path))
    RUNNING_TASKS.clear()
    init_db()
    insert_generation_job("gen-done", "done", "Finished job")
    insert_generation_job("gen-failed", "failed", "Failed job")
    insert_generation_job("gen-pending", "pending", "Pending job")
    insert_generation_job("gen-running", "running", "Running job")

    with TestClient(app) as client:
        finished_response = client.delete("/generation-jobs/finished")
        assert finished_response.status_code == 200
        assert finished_response.json()["deleted"] == 2

        remaining_ids = {job["id"] for job in finished_response.json()["jobs"]}
        assert remaining_ids == {"gen-pending", "gen-running"}

        active_response = client.delete("/generation-jobs/active")
        assert active_response.status_code == 200
        assert active_response.json()["deleted"] == 2
        assert client.get("/generation-jobs").json()["jobs"] == []


def test_item_api_endpoints(tmp_path, monkeypatch):
    db_path = tmp_path / "world.sqlite3"
    worlds_path = tmp_path / "worlds"
    monkeypatch.setattr(settings, "database_path", str(db_path))
    monkeypatch.setattr(settings, "worlds_dir", str(worlds_path))
    RUNNING_TASKS.clear()
    init_db()
    model = sample_model()
    world_id = insert_world("A rain-lashed border market with old keeps", model, sample_world_draft(), "{}", 0)

    with TestClient(app) as client:
        staple_payload = client.get("/staple-items")
        assert staple_payload.status_code == 200
        assert len(staple_payload.json()["items"]) >= 10

        items_payload = client.get(f"/worlds/{world_id}/items")
        assert items_payload.status_code == 200
        items = items_payload.json()["items"]
        assert items
        assert all(item["source_type"] in {"staple", "world"} for item in items)

        world_items_payload = client.get(f"/worlds/{world_id}/world-items")
        assert world_items_payload.status_code == 200
        assert world_items_payload.json()["items"] == []

        inventory_payload = client.get(f"/worlds/{world_id}/npc-inventory")
        assert inventory_payload.status_code == 200
        inventory = inventory_payload.json()["inventory"]
        assert inventory
        assert inventory[0]["npc_name"]

        item = items[0]
        lore_payload = client.get(f"/worlds/{world_id}/lore/{item['lore_entity_type']}/{item['id']}")
        assert lore_payload.status_code == 200
        assert lore_payload.json()["content"]


def test_play_state_api_creates_session(tmp_path, monkeypatch):
    db_path = tmp_path / "world.sqlite3"
    worlds_path = tmp_path / "worlds"
    monkeypatch.setattr(settings, "database_path", str(db_path))
    monkeypatch.setattr(settings, "worlds_dir", str(worlds_path))
    RUNNING_TASKS.clear()
    init_db()
    world_id = insert_world("A road of low winter shrines", sample_model(), sample_world_draft(), "{}", 0)

    with TestClient(app) as client:
        response = client.get(f"/worlds/{world_id}/play")

    assert response.status_code == 200
    payload = response.json()
    assert payload["session"]["world_id"] == world_id
    assert payload["session"]["mode"] == "default"
    assert payload["session"]["conversation_npc_id"] is None
    assert payload["character"]["name"] == "Kaelen Duskborn"
    assert payload["current_place"]["id"] in {place["id"] for place in payload["places"]}
    assert payload["present_npcs"]
    assert payload["current_place"]["id"] in {npc["current_place_id"] for npc in payload["present_npcs"]}
    assert payload["messages"][0]["kind"] == "system"


def test_play_travel_rejects_invalid_place_and_updates_location(tmp_path, monkeypatch):
    db_path = tmp_path / "world.sqlite3"
    worlds_path = tmp_path / "worlds"
    monkeypatch.setattr(settings, "database_path", str(db_path))
    monkeypatch.setattr(settings, "worlds_dir", str(worlds_path))
    RUNNING_TASKS.clear()
    init_db()
    first_world_id = insert_world("A copper hill road", sample_model(), sample_world_draft(), "{}", 0)
    first_place = list_table(first_world_id, "places")[0]

    with TestClient(app) as client:
        rejected = client.post(
            f"/worlds/{first_world_id}/play/travel",
            json={"place_id": "missing-place"},
        )
        accepted = client.post(
            f"/worlds/{first_world_id}/play/travel",
            json={"place_id": first_place["id"]},
        )

    assert rejected.status_code == 400
    assert accepted.status_code == 200
    payload = accepted.json()
    assert payload["session"]["current_place_id"] == first_place["id"]
    assert payload["messages"][-1]["kind"] == "travel"


def test_play_input_default_free_form_is_noop(tmp_path, monkeypatch):
    import api

    db_path = tmp_path / "world.sqlite3"
    worlds_path = tmp_path / "worlds"
    monkeypatch.setattr(settings, "database_path", str(db_path))
    monkeypatch.setattr(settings, "worlds_dir", str(worlds_path))
    RUNNING_TASKS.clear()
    init_db()
    world_id = insert_world("A quiet road market", sample_model(), sample_world_draft(), "{}", 0)

    async def unexpected_chat_completion(*args, **kwargs):
        raise AssertionError("Default free-form input should not call the LLM.")

    monkeypatch.setattr(api, "chat_completion", unexpected_chat_completion)

    with TestClient(app) as client:
        before = client.get(f"/worlds/{world_id}/play").json()
        response = client.post(
            f"/worlds/{world_id}/play/input",
            json={"input": "I look around the square."},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["session"]["mode"] == "default"
    assert payload["messages"] == before["messages"]


def test_play_input_travel_and_talk_commands_change_state(tmp_path, monkeypatch):
    db_path = tmp_path / "world.sqlite3"
    worlds_path = tmp_path / "worlds"
    monkeypatch.setattr(settings, "database_path", str(db_path))
    monkeypatch.setattr(settings, "worlds_dir", str(worlds_path))
    RUNNING_TASKS.clear()
    init_db()
    world_id = insert_world("A road of lantern posts", sample_model(), sample_world_draft(), "{}", 0)

    with TestClient(app) as client:
        state = client.get(f"/worlds/{world_id}/play").json()
        npc_place_ids = {npc["current_place_id"] for npc in list_table(world_id, "npcs")}
        destination = next(
            place for place in state["places"]
            if place["id"] != state["current_place"]["id"] and place["id"] in npc_place_ids
        )
        travelled = client.post(
            f"/worlds/{world_id}/play/input",
            json={"input": f"/travel {destination['name']}"},
        )
        state = travelled.json()
        npc = state["present_npcs"][0]
        talked = client.post(
            f"/worlds/{world_id}/play/input",
            json={"input": f"/talk {npc['name']}"},
        )

    assert travelled.status_code == 200
    assert state["session"]["current_place_id"] == destination["id"]
    assert state["session"]["mode"] == "default"
    assert talked.status_code == 200
    payload = talked.json()
    assert payload["session"]["mode"] == "conversation"
    assert payload["session"]["conversation_npc_id"] == npc["id"]
    assert payload["conversation_npc"]["id"] == npc["id"]
    assert payload["messages"][-1]["kind"] == "system"


def test_play_input_conversation_dialogue_and_exit(tmp_path, monkeypatch):
    import api

    db_path = tmp_path / "world.sqlite3"
    worlds_path = tmp_path / "worlds"
    monkeypatch.setattr(settings, "database_path", str(db_path))
    monkeypatch.setattr(settings, "worlds_dir", str(worlds_path))
    RUNNING_TASKS.clear()
    init_db()
    world_id = insert_world("A market beneath red awnings", sample_model(), sample_world_draft(), "{}", 0)
    captured = {}

    async def fake_chat_completion(model, messages, temperature=None, response_format=None):
        captured["messages"] = messages
        return "The west gate closes before dusk.", 12

    monkeypatch.setattr(api, "chat_completion", fake_chat_completion)

    with TestClient(app) as client:
        state = client.get(f"/worlds/{world_id}/play").json()
        npc = state["present_npcs"][0]
        entered = client.post(
            f"/worlds/{world_id}/play/input",
            json={"input": f"/talk {npc['name']}"},
        )
        blocked = client.post(
            f"/worlds/{world_id}/play/input",
            json={"input": f"/travel {state['places'][0]['name']}"},
        )
        replied = client.post(
            f"/worlds/{world_id}/play/input",
            json={"input": "What should I know?"},
        )
        exited = client.post(
            f"/worlds/{world_id}/play/input",
            json={"input": "/exit"},
        )

    assert entered.status_code == 200
    assert blocked.status_code == 400
    assert replied.status_code == 200
    reply_payload = replied.json()
    assert reply_payload["session"]["mode"] == "conversation"
    assert reply_payload["messages"][-2]["kind"] == "player"
    assert reply_payload["messages"][-1]["kind"] == "npc"
    assert "What should I know?" in captured["messages"][1]["content"]
    assert exited.status_code == 200
    exit_payload = exited.json()
    assert exit_payload["session"]["mode"] == "default"
    assert exit_payload["session"]["conversation_npc_id"] is None
    assert exit_payload["messages"][-1]["kind"] == "system"


def test_play_input_rejects_invalid_commands(tmp_path, monkeypatch):
    db_path = tmp_path / "world.sqlite3"
    worlds_path = tmp_path / "worlds"
    monkeypatch.setattr(settings, "database_path", str(db_path))
    monkeypatch.setattr(settings, "worlds_dir", str(worlds_path))
    RUNNING_TASKS.clear()
    init_db()
    world_id = insert_world("A hill road without good signs", sample_model(), sample_world_draft(), "{}", 0)

    with TestClient(app) as client:
        missing_place = client.post(
            f"/worlds/{world_id}/play/input",
            json={"input": "/travel Nowhere"},
        )
        missing_npc = client.post(
            f"/worlds/{world_id}/play/input",
            json={"input": "/talk Nobody"},
        )

    assert missing_place.status_code == 400
    assert missing_npc.status_code == 400


def test_play_talk_uses_llm_and_stores_messages(tmp_path, monkeypatch):
    import api

    db_path = tmp_path / "world.sqlite3"
    worlds_path = tmp_path / "worlds"
    monkeypatch.setattr(settings, "database_path", str(db_path))
    monkeypatch.setattr(settings, "worlds_dir", str(worlds_path))
    RUNNING_TASKS.clear()
    init_db()
    world_id = insert_world("A market beneath black pines", sample_model(), sample_world_draft(), "{}", 0)
    npc = list_table(world_id, "npcs")[0]
    captured = {}

    async def fake_chat_completion(model, messages, temperature=None, response_format=None):
        captured["model"] = model
        captured["messages"] = messages
        captured["temperature"] = temperature
        return "Keep your voice low; the road has been listening.", 9

    monkeypatch.setattr(api, "chat_completion", fake_chat_completion)

    with TestClient(app) as client:
        missing = client.post(
            f"/worlds/{world_id}/play/talk",
            json={"npc_id": "missing-npc", "message": "Hello?"},
        )
        response = client.post(
            f"/worlds/{world_id}/play/talk",
            json={"npc_id": npc["id"], "message": "What should I know about this place?"},
        )

    assert missing.status_code == 404
    assert response.status_code == 200
    messages = response.json()["messages"]
    assert messages[-2]["kind"] == "player"
    assert messages[-1]["kind"] == "npc"
    assert "What should I know" in captured["messages"][1]["content"]
    assert npc["name"] in captured["messages"][0]["content"]
