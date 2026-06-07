import json
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from database import db_session
from world_repository import get_world, read_lore, row_to_dict


TEST_CHARACTER = {
    "name": "Kaelen Duskborn",
    "summary": "A guarded wanderer testing the world's first playable loop.",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_npc(row: dict[str, Any]) -> dict[str, Any]:
    try:
        parsed = json.loads(row.get("personality") or "[]")
    except (TypeError, json.JSONDecodeError):
        parsed = row.get("personality")
    row["personality"] = parsed if isinstance(parsed, list) else [parsed] if parsed else []
    return row


def _first_place(world_id: str) -> Optional[dict[str, Any]]:
    with db_session() as conn:
        row = conn.execute(
            "SELECT * FROM places WHERE world_id = ? ORDER BY name LIMIT 1",
            (world_id,),
        ).fetchone()
    return row_to_dict(row) if row else None


def _get_session(world_id: str) -> Optional[dict[str, Any]]:
    with db_session() as conn:
        row = conn.execute("SELECT * FROM play_sessions WHERE world_id = ?", (world_id,)).fetchone()
    return row_to_dict(row) if row else None


def ensure_play_session(world_id: str) -> dict[str, Any]:
    session = _get_session(world_id)
    if session:
        return session

    if not get_world(world_id):
        raise ValueError("World not found.")

    place = _first_place(world_id)
    if not place:
        raise ValueError("World has no places to explore.")

    timestamp = now_iso()
    session_id = f"play-{uuid4().hex[:12]}"
    welcome = f"{TEST_CHARACTER['name']} arrives at {place['name']}. {place.get('summary', '')}".strip()
    with db_session() as conn:
        conn.execute(
            """
            INSERT INTO play_sessions
                (id, world_id, character_name, character_summary, current_place_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                world_id,
                TEST_CHARACTER["name"],
                TEST_CHARACTER["summary"],
                place["id"],
                timestamp,
                timestamp,
            ),
        )
        conn.execute(
            """
            INSERT INTO play_messages (id, session_id, kind, npc_id, content, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (f"msg-{uuid4().hex[:12]}", session_id, "system", None, welcome, timestamp),
        )

    return _get_session(world_id) or {}


def _list_places(world_id: str) -> list[dict[str, Any]]:
    with db_session() as conn:
        rows = conn.execute("SELECT * FROM places WHERE world_id = ? ORDER BY name", (world_id,)).fetchall()
    return [row_to_dict(row) for row in rows]


def _list_npcs(world_id: str) -> list[dict[str, Any]]:
    with db_session() as conn:
        rows = conn.execute("SELECT * FROM npcs WHERE world_id = ? ORDER BY name", (world_id,)).fetchall()
    return [_parse_npc(row_to_dict(row)) for row in rows]


def _list_messages(session_id: str, limit: int = 80) -> list[dict[str, Any]]:
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT * FROM (
                SELECT * FROM play_messages
                WHERE session_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            )
            ORDER BY created_at ASC
            """,
            (session_id, limit),
        ).fetchall()
    return [row_to_dict(row) for row in rows]


def get_play_state(world_id: str) -> Optional[dict[str, Any]]:
    world = get_world(world_id)
    if not world:
        return None

    session = ensure_play_session(world_id)
    places = _list_places(world_id)
    npcs = _list_npcs(world_id)
    place_by_id = {place["id"]: place for place in places}
    current_place = place_by_id.get(session["current_place_id"]) or places[0] if places else None
    present_npcs = [
        npc for npc in npcs
        if npc.get("current_place_id") == session.get("current_place_id")
    ]

    return {
        "world": world,
        "session": session,
        "character": {
            "name": session["character_name"],
            "summary": session["character_summary"],
        },
        "current_place": current_place,
        "places": places,
        "present_npcs": present_npcs,
        "messages": _list_messages(session["id"]),
    }


def travel_play_session(world_id: str, place_id: str) -> dict[str, Any]:
    session = ensure_play_session(world_id)
    with db_session() as conn:
        place = conn.execute(
            "SELECT * FROM places WHERE world_id = ? AND id = ?",
            (world_id, place_id),
        ).fetchone()
        if not place:
            raise ValueError("Place does not belong to this world.")

        place_row = row_to_dict(place)
        timestamp = now_iso()
        conn.execute(
            "UPDATE play_sessions SET current_place_id = ?, updated_at = ? WHERE id = ?",
            (place_id, timestamp, session["id"]),
        )
        content = f"You travel to {place_row['name']}. {place_row.get('summary', '')}".strip()
        conn.execute(
            """
            INSERT INTO play_messages (id, session_id, kind, npc_id, content, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (f"msg-{uuid4().hex[:12]}", session["id"], "travel", None, content, timestamp),
        )

    state = get_play_state(world_id)
    if state is None:
        raise ValueError("World not found.")
    return state


def get_npc_for_play(world_id: str, npc_id: str) -> Optional[dict[str, Any]]:
    with db_session() as conn:
        row = conn.execute("SELECT * FROM npcs WHERE world_id = ? AND id = ?", (world_id, npc_id)).fetchone()
    return _parse_npc(row_to_dict(row)) if row else None


def get_faction(world_id: str, faction_id: Optional[str]) -> Optional[dict[str, Any]]:
    if not faction_id:
        return None
    with db_session() as conn:
        row = conn.execute("SELECT * FROM factions WHERE world_id = ? AND id = ?", (world_id, faction_id)).fetchone()
    return row_to_dict(row) if row else None


def list_npc_relationships(world_id: str, npc_id: str) -> list[dict[str, Any]]:
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT * FROM relationships
            WHERE world_id = ?
              AND ((source_type = 'npc' AND source_id = ?) OR (target_type = 'npc' AND target_id = ?))
            ORDER BY id
            """,
            (world_id, npc_id, npc_id),
        ).fetchall()
    return [row_to_dict(row) for row in rows]


def append_play_message(world_id: str, kind: str, content: str, npc_id: Optional[str] = None) -> dict[str, Any]:
    session = ensure_play_session(world_id)
    timestamp = now_iso()
    with db_session() as conn:
        conn.execute(
            """
            INSERT INTO play_messages (id, session_id, kind, npc_id, content, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (f"msg-{uuid4().hex[:12]}", session["id"], kind, npc_id, content, timestamp),
        )
        conn.execute("UPDATE play_sessions SET updated_at = ? WHERE id = ?", (timestamp, session["id"]))
    return _list_messages(session["id"])[-1]


def lore_excerpt(world_id: str, entity_type: str, entity_id: str, limit: int = 1800) -> str:
    try:
        content = read_lore(world_id, entity_type, entity_id) or ""
    except ValueError:
        return ""
    return content[:limit]
