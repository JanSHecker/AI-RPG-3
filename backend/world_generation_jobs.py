from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from database import db_session
from model_catalog import ConfiguredModel
from world_generation.pipeline import STEP_LABELS
from world_generator import build_world_draft, build_world_draft_from_job_steps, insert_world, validate_links


RUNNING_TASKS: dict[str, asyncio.Task] = {}
TASK_LOCK = asyncio.Lock()
ACTIVE_STATUSES = {"pending", "running", "retrying"}
FINISHED_STATUSES = {"done", "failed"}
STALE_RUNNING_SECONDS = 300
RECENT_FINISHED_LIMIT = 50


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _job_id() -> str:
    return f"gen-{uuid.uuid4().hex[:12]}"


def _step_id() -> str:
    return f"step-{uuid.uuid4().hex[:12]}"


def _step_label(step_name: str) -> str:
    if step_name.startswith("places_"):
        batch_name = step_name.removeprefix("places_").replace("_", " ")
        if batch_name.startswith("batch "):
            batch_name = batch_name.removeprefix("batch ")
        return f"Places batch {batch_name}"
    if step_name.startswith("npcs_"):
        place_name = step_name.removeprefix("npcs_place_").replace("_", " ")
        return f"NPC batch {place_name}"
    return STEP_LABELS.get(step_name, step_name)


def _row_to_dict(row) -> dict[str, Any]:
    return dict(row) if row is not None else {}


def _decode_step(row) -> dict[str, Any]:
    data = _row_to_dict(row)
    data["attempts"] = int(data.get("attempts") or 0)
    data["latency_ms"] = data.get("latency_ms")
    try:
        prompt_messages = json.loads(data.get("prompt_messages") or "[]")
    except json.JSONDecodeError:
        prompt_messages = []
    data["prompt_messages"] = prompt_messages if isinstance(prompt_messages, list) else []
    return data


def _load_job_model(job: dict[str, Any]) -> ConfiguredModel:
    return ConfiguredModel(
        id=f"{job['provider']}:{job['model_name']}",
        label=job["model_name"],
        provider=job["provider"],
        model_name=job["model_name"],
    )


def create_generation_job(prompt: str, model: ConfiguredModel) -> dict[str, Any]:
    job_id = _job_id()
    timestamp = now_iso()
    with db_session() as conn:
        conn.execute(
            "INSERT INTO generation_jobs (id, prompt, provider, model_name, status, world_id, error, resume_step_name, created_at, updated_at, started_at, finished_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (job_id, prompt, model.provider, model.model_name, "pending", None, "", None, timestamp, timestamp, None, None),
        )
        for step_name, label in STEP_LABELS.items():
            conn.execute(
                "INSERT INTO generation_job_steps (id, job_id, step_name, label, status, attempts, error, raw_response, parsed_payload, latency_ms, started_at, finished_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (_step_id(), job_id, step_name, label, "pending", 0, "", "", "", None, None, None),
            )
    job = get_generation_job(job_id)
    if not job:
        raise RuntimeError("Generation job was not created.")
    return job


def restart_generation_job(job_id: str, model: ConfiguredModel) -> Optional[dict[str, Any]]:
    timestamp = now_iso()
    with db_session() as conn:
        job = conn.execute("SELECT status FROM generation_jobs WHERE id = ?", (job_id,)).fetchone()
        if not job:
            return None
        if job["status"] != "failed":
            raise ValueError("Only failed generation jobs can be restarted.")
        conn.execute(
            """
            UPDATE generation_jobs
            SET status = 'pending',
                provider = ?,
                model_name = ?,
                world_id = NULL,
                error = '',
                resume_step_name = NULL,
                updated_at = ?,
                started_at = NULL,
                finished_at = NULL
            WHERE id = ?
            """,
            (model.provider, model.model_name, timestamp, job_id),
        )
        conn.execute(
            """
            UPDATE generation_job_steps
            SET status = 'pending',
                attempts = 0,
                error = '',
                prompt_messages = '[]',
                raw_response = '',
                parsed_payload = '',
                latency_ms = NULL,
                started_at = NULL,
                finished_at = NULL
            WHERE job_id = ?
            """,
            (job_id,),
        )
    return get_generation_job(job_id)


def _retry_parent_and_downstream(step_name: str) -> tuple[str, list[str], list[str]]:
    if step_name.startswith("places_"):
        return (
            "villages_places",
            ["villages_places", "character_diagram", "npcs", "relationships"],
            ["npcs_", "relationships_"],
        )
    if step_name.startswith("npcs_"):
        return ("npcs", ["npcs", "relationships"], ["relationships_"])
    if step_name.startswith("relationships_"):
        return ("relationships", ["relationships"], [])
    raise ValueError("Only failed batch steps can be retried.")


def _required_resume_checkpoints(step_name: str) -> list[str]:
    base = ["region", "factions", "location_plan"]
    if step_name.startswith("places_"):
        return base
    base.extend(["villages_places", "character_diagram"])
    if step_name.startswith("npcs_"):
        return base
    base.append("npcs")
    return base


def _validate_resume_checkpoints(conn, job_id: str, step_name: str) -> None:
    required = _required_resume_checkpoints(step_name)
    placeholders = ",".join("?" for _ in required)
    rows = conn.execute(
        f"SELECT step_name, status, parsed_payload FROM generation_job_steps WHERE job_id = ? AND step_name IN ({placeholders})",
        [job_id, *required],
    ).fetchall()
    by_name = {row["step_name"]: row for row in rows}
    missing = [
        name
        for name in required
        if name not in by_name or by_name[name]["status"] != "done" or not by_name[name]["parsed_payload"]
    ]
    if missing:
        raise ValueError(f"Cannot resume this job because checkpoint(s) are missing: {', '.join(missing)}. Use full restart instead.")


def retry_generation_job_step(job_id: str, step_name: str, model: ConfiguredModel) -> Optional[dict[str, Any]]:
    parent_step, aggregate_steps, downstream_prefixes = _retry_parent_and_downstream(step_name)
    timestamp = now_iso()
    with db_session() as conn:
        job = conn.execute("SELECT status FROM generation_jobs WHERE id = ?", (job_id,)).fetchone()
        if not job:
            return None
        if job["status"] != "failed":
            raise ValueError("Only failed generation jobs can retry a batch step.")
        step = conn.execute(
            "SELECT status FROM generation_job_steps WHERE job_id = ? AND step_name = ?",
            (job_id, step_name),
        ).fetchone()
        if not step:
            raise ValueError("Generation batch step not found.")
        if step["status"] != "failed":
            raise ValueError("Only failed batch steps can be retried.")
        _validate_resume_checkpoints(conn, job_id, step_name)

        conn.execute(
            """
            UPDATE generation_jobs
            SET status = 'pending',
                provider = ?,
                model_name = ?,
                world_id = NULL,
                error = '',
                resume_step_name = ?,
                updated_at = ?,
                started_at = NULL,
                finished_at = NULL
            WHERE id = ?
            """,
            (model.provider, model.model_name, step_name, timestamp, job_id),
        )

        reset_exact = [step_name, *aggregate_steps]
        placeholders = ",".join("?" for _ in reset_exact)
        conn.execute(
            f"""
            UPDATE generation_job_steps
            SET status = 'pending',
                attempts = 0,
                error = '',
                prompt_messages = '[]',
                raw_response = '',
                parsed_payload = '',
                latency_ms = NULL,
                started_at = NULL,
                finished_at = NULL
            WHERE job_id = ? AND step_name IN ({placeholders})
            """,
            [job_id, *reset_exact],
        )
        batch_prefix = step_name.split("_", 1)[0] + "_"
        conn.execute(
            """
            UPDATE generation_job_steps
            SET status = 'pending',
                attempts = 0,
                error = '',
                prompt_messages = '[]',
                raw_response = '',
                parsed_payload = '',
                latency_ms = NULL,
                started_at = NULL,
                finished_at = NULL
            WHERE job_id = ? AND step_name LIKE ? AND status != 'done'
            """,
            (job_id, f"{batch_prefix}%"),
        )
        for prefix in downstream_prefixes:
            conn.execute(
                """
                UPDATE generation_job_steps
                SET status = 'pending',
                    attempts = 0,
                    error = '',
                    prompt_messages = '[]',
                    raw_response = '',
                    parsed_payload = '',
                    latency_ms = NULL,
                    started_at = NULL,
                    finished_at = NULL
                WHERE job_id = ? AND step_name LIKE ?
                """,
                (job_id, f"{prefix}%"),
            )
    return get_generation_job(job_id)


def get_generation_job(job_id: str) -> Optional[dict[str, Any]]:
    with db_session() as conn:
        job = conn.execute("SELECT * FROM generation_jobs WHERE id = ?", (job_id,)).fetchone()
        if not job:
            return None
        steps = conn.execute(
            "SELECT * FROM generation_job_steps WHERE job_id = ? ORDER BY rowid",
            (job_id,),
        ).fetchall()
    data = _row_to_dict(job)
    data["steps"] = [_decode_step(step) for step in steps]
    return data


def list_generation_jobs(limit: int = RECENT_FINISHED_LIMIT) -> list[dict[str, Any]]:
    with db_session() as conn:
        rows = conn.execute(
            """
            SELECT * FROM generation_jobs
            WHERE status IN ('pending', 'running', 'retrying')
               OR id IN (
                   SELECT id FROM generation_jobs
                   WHERE status IN ('done', 'failed')
                   ORDER BY updated_at DESC
                   LIMIT ?
               )
            ORDER BY updated_at DESC
            """,
            (limit,),
        ).fetchall()
        job_ids = [row["id"] for row in rows]
        steps_by_job: dict[str, list[dict[str, Any]]] = {job_id: [] for job_id in job_ids}
        if job_ids:
            placeholders = ",".join("?" for _ in job_ids)
            step_rows = conn.execute(
                f"SELECT * FROM generation_job_steps WHERE job_id IN ({placeholders}) ORDER BY rowid",
                job_ids,
            ).fetchall()
            for step in step_rows:
                steps_by_job[step["job_id"]].append(_decode_step(step))
    jobs = []
    for row in rows:
        data = _row_to_dict(row)
        data["steps"] = steps_by_job.get(data["id"], [])
        jobs.append(data)
    return jobs


async def clear_finished_generation_jobs() -> int:
    with db_session() as conn:
        rows = conn.execute(
            "SELECT id FROM generation_jobs WHERE status IN ('done', 'failed')"
        ).fetchall()
        job_ids = [row["id"] for row in rows]
        if job_ids:
            placeholders = ",".join("?" for _ in job_ids)
            conn.execute(f"DELETE FROM generation_jobs WHERE id IN ({placeholders})", job_ids)
    return len(job_ids)


async def clear_active_generation_jobs() -> int:
    async with TASK_LOCK:
        with db_session() as conn:
            rows = conn.execute(
                "SELECT id FROM generation_jobs WHERE status IN ('pending', 'running', 'retrying')"
            ).fetchall()
            job_ids = [row["id"] for row in rows]
            for job_id in job_ids:
                task = RUNNING_TASKS.pop(job_id, None)
                if task and not task.done():
                    task.cancel()
            if job_ids:
                placeholders = ",".join("?" for _ in job_ids)
                conn.execute(f"DELETE FROM generation_jobs WHERE id IN ({placeholders})", job_ids)
    return len(job_ids)


def update_job_status(job_id: str, status: str, *, error: str = "", world_id: Optional[str] = None) -> None:
    timestamp = now_iso()
    started_at = timestamp if status == "running" else None
    finished_at = timestamp if status in FINISHED_STATUSES else None
    with db_session() as conn:
        conn.execute(
            """
            UPDATE generation_jobs
            SET status = ?,
                error = ?,
                world_id = COALESCE(?, world_id),
                resume_step_name = CASE WHEN ? IN ('done', 'failed') THEN NULL ELSE resume_step_name END,
                updated_at = ?,
                started_at = COALESCE(started_at, ?),
                finished_at = ?
            WHERE id = ?
            """,
            (status, error, world_id, status, timestamp, started_at, finished_at, job_id),
        )


async def update_job_step(job_id: str, step_name: str, status: str, payload: dict[str, Any]) -> None:
    timestamp = now_iso()
    started_at = timestamp if status == "running" else None
    finished_at = timestamp if status in {"done", "failed"} else None
    parsed_payload = payload.get("parsed_payload")
    parsed_text = json.dumps(parsed_payload, ensure_ascii=False) if parsed_payload is not None else None
    prompt_messages = payload.get("prompt_messages")
    prompt_messages_text = json.dumps(prompt_messages, ensure_ascii=False) if prompt_messages is not None else None
    label = payload.get("label") or _step_label(step_name)
    with db_session() as conn:
        cursor = conn.execute(
            """
            UPDATE generation_job_steps
            SET status = ?,
                attempts = ?,
                error = ?,
                prompt_messages = COALESCE(?, prompt_messages),
                raw_response = COALESCE(?, raw_response),
                parsed_payload = COALESCE(?, parsed_payload),
                latency_ms = COALESCE(?, latency_ms),
                started_at = COALESCE(started_at, ?),
                finished_at = ?,
                label = COALESCE(?, label)
            WHERE job_id = ? AND step_name = ?
            """,
            (
                status,
                int(payload.get("attempts") or 0),
                payload.get("error") or "",
                prompt_messages_text,
                payload.get("raw_response"),
                parsed_text,
                payload.get("latency_ms"),
                started_at,
                finished_at,
                label,
                job_id,
                step_name,
            ),
        )
        if cursor.rowcount == 0:
            conn.execute(
                """
                INSERT INTO generation_job_steps
                    (id, job_id, step_name, label, status, attempts, error, prompt_messages, raw_response, parsed_payload, latency_ms, started_at, finished_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _step_id(),
                    job_id,
                    step_name,
                    label,
                    status,
                    int(payload.get("attempts") or 0),
                    payload.get("error") or "",
                    prompt_messages_text or "[]",
                    payload.get("raw_response") or "",
                    parsed_text or "",
                    payload.get("latency_ms"),
                    started_at,
                    finished_at,
                ),
            )
        conn.execute(
            "UPDATE generation_jobs SET updated_at = ? WHERE id = ?",
            (timestamp, job_id),
        )


def _mark_stale_running_jobs() -> None:
    now = datetime.now(timezone.utc)
    with db_session() as conn:
        rows = conn.execute("SELECT id, updated_at FROM generation_jobs WHERE status = 'running'").fetchall()
        for row in rows:
            if row["id"] in RUNNING_TASKS and not RUNNING_TASKS[row["id"]].done():
                continue
            try:
                updated_at = datetime.fromisoformat(row["updated_at"])
            except ValueError:
                updated_at = now
            if (now - updated_at).total_seconds() >= STALE_RUNNING_SECONDS or row["id"] not in RUNNING_TASKS:
                conn.execute(
                    "UPDATE generation_jobs SET status = 'retrying', error = ?, updated_at = ? WHERE id = ?",
                    ("Generation task stopped reporting progress and will be resumed.", now_iso(), row["id"]),
                )


def _next_queued_job() -> Optional[dict[str, Any]]:
    with db_session() as conn:
        row = conn.execute(
            "SELECT * FROM generation_jobs WHERE status IN ('pending', 'retrying') ORDER BY created_at ASC LIMIT 1"
        ).fetchone()
    return _row_to_dict(row) if row else None


async def ensure_generation_tasks() -> None:
    _mark_stale_running_jobs()
    async with TASK_LOCK:
        active_task = next((task for task in RUNNING_TASKS.values() if not task.done()), None)
        if active_task:
            return
        job = _next_queued_job()
        if not job:
            return
        RUNNING_TASKS[job["id"]] = asyncio.create_task(_run_generation_job(job["id"]))


async def _run_generation_job(job_id: str) -> None:
    try:
        job = get_generation_job(job_id)
        if not job or job.get("status") == "done":
            return
        update_job_status(job_id, "running")
        model = _load_job_model(job)

        async def updater(step_name: str, status: str, payload: dict[str, Any]) -> None:
            await update_job_step(job_id, step_name, status, payload)

        if job.get("resume_step_name"):
            draft, raw_response, latency_ms = await build_world_draft_from_job_steps(
                job["prompt"],
                model,
                job.get("steps") or [],
                job["resume_step_name"],
                updater,
            )
        else:
            draft, raw_response, latency_ms = await build_world_draft(job["prompt"], model, updater)
        validate_links(draft)
        if not get_generation_job(job_id):
            return
        world_id = insert_world(job["prompt"], model, draft, raw_response, latency_ms)
        update_job_status(job_id, "done", world_id=world_id)
    except Exception as exc:
        update_job_status(job_id, "failed", error=str(exc))
    finally:
        async with TASK_LOCK:
            current_task = RUNNING_TASKS.get(job_id)
            if current_task is asyncio.current_task():
                RUNNING_TASKS.pop(job_id, None)
        await ensure_generation_tasks()
