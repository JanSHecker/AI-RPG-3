from time import perf_counter
from typing import Optional

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel

from database import init_db
from model_catalog import ConfiguredModel, find_model, load_model_catalog, resolve_active_model, save_active_model_id
from providers import ProviderError, chat_completion
from world_repository import (
    delete_world,
    get_world,
    list_npc_inventory_items,
    list_resolved_items,
    list_table,
    list_worlds,
    read_lore,
)
from world_generation_jobs import (
    clear_active_generation_jobs,
    clear_finished_generation_jobs,
    create_generation_job,
    ensure_generation_tasks,
    get_generation_job,
    list_generation_jobs,
    restart_generation_job,
)
from item_catalog import load_staple_catalog


router = APIRouter()


class ActiveModelRequest(BaseModel):
    model_id: str


class ModelTestSelection(BaseModel):
    id: str
    provider: str
    model_name: str
    label: Optional[str] = None


class ModelTestRequest(BaseModel):
    models: list[ModelTestSelection]
    prompt: str = "Reply with exactly: OK"


class CreateWorldRequest(BaseModel):
    prompt: str
    model_id: Optional[str] = None


class RestartGenerationJobRequest(BaseModel):
    model_id: Optional[str] = None


@router.get("/models")
async def list_models():
    return {"models": [model.model_dump() for model in load_model_catalog()]}


@router.get("/models/active")
async def get_active_model():
    return resolve_active_model().model_dump()


@router.put("/models/active")
async def set_active_model(request: ActiveModelRequest):
    model = find_model(request.model_id)
    if not model:
        raise HTTPException(status_code=400, detail="Model is not in models.json.")
    save_active_model_id(model.id)
    return model.model_dump()


@router.post("/models/test")
async def test_models(request: ModelTestRequest):
    results = []
    prompt = request.prompt.strip() or "Reply with exactly: OK"
    for item in request.models:
        started = perf_counter()
        try:
            preview, latency = await chat_completion(
                ConfiguredModel(
                    id=item.id,
                    label=item.label or item.id,
                    provider=item.provider,
                    model_name=item.model_name,
                ),
                [{"role": "user", "content": prompt}],
                temperature=0,
            )
            results.append({
                "id": item.id,
                "label": item.label or item.id,
                "provider": item.provider,
                "model_name": item.model_name,
                "ok": True,
                "latency_ms": latency,
                "response_preview": preview[:200],
                "error": "",
            })
        except Exception as exc:
            results.append({
                "id": item.id,
                "label": item.label or item.id,
                "provider": item.provider,
                "model_name": item.model_name,
                "ok": False,
                "latency_ms": int((perf_counter() - started) * 1000),
                "response_preview": "",
                "error": str(exc),
            })
    return {"prompt": prompt, "results": results}


@router.get("/worlds")
async def api_list_worlds():
    return {"worlds": list_worlds()}


@router.post("/worlds", status_code=202)
async def create_world(request: CreateWorldRequest):
    prompt = request.prompt.strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="World prompt cannot be empty.")
    model = find_model(request.model_id) if request.model_id else resolve_active_model()
    if not model:
        raise HTTPException(status_code=400, detail="Selected model is not configured.")
    try:
        job = create_generation_job(prompt, model)
        await ensure_generation_tasks()
        return {"job": get_generation_job(job["id"]) or job}
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"World generation could not start: {exc}")


@router.get("/generation-jobs")
async def api_generation_jobs():
    await ensure_generation_tasks()
    return {"jobs": list_generation_jobs()}


@router.delete("/generation-jobs/finished")
async def api_clear_finished_generation_jobs():
    deleted = await clear_finished_generation_jobs()
    return {"deleted": deleted, "jobs": list_generation_jobs()}


@router.delete("/generation-jobs/active")
async def api_clear_active_generation_jobs():
    deleted = await clear_active_generation_jobs()
    await ensure_generation_tasks()
    return {"deleted": deleted, "jobs": list_generation_jobs()}


@router.get("/generation-jobs/{job_id}")
async def api_generation_job(job_id: str):
    await ensure_generation_tasks()
    job = get_generation_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Generation job not found.")
    return {"job": job}


@router.post("/generation-jobs/{job_id}/restart", status_code=202)
async def api_restart_generation_job(
    job_id: str,
    request: Optional[RestartGenerationJobRequest] = Body(default=None),
    model_id: Optional[str] = None,
):
    selected_model_id = request.model_id if request and request.model_id else model_id
    model = find_model(selected_model_id) if selected_model_id else resolve_active_model()
    if not model:
        raise HTTPException(status_code=400, detail="Selected model is not configured.")
    try:
        job = restart_generation_job(job_id, model)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not job:
        raise HTTPException(status_code=404, detail="Generation job not found.")
    await ensure_generation_tasks()
    return {"job": get_generation_job(job_id) or job}


@router.get("/worlds/{world_id}")
async def api_get_world(world_id: str):
    world = get_world(world_id)
    if not world:
        raise HTTPException(status_code=404, detail="World not found.")
    return {"world": world}


@router.delete("/worlds/{world_id}", status_code=204)
async def api_delete_world(world_id: str):
    if not delete_world(world_id):
        raise HTTPException(status_code=404, detail="World not found.")
    return None


@router.get("/worlds/{world_id}/places")
async def api_places(world_id: str):
    return {"places": list_table(world_id, "places")}


@router.get("/worlds/{world_id}/npcs")
async def api_npcs(world_id: str):
    return {"npcs": list_table(world_id, "npcs")}


@router.get("/worlds/{world_id}/factions")
async def api_factions(world_id: str):
    return {"factions": list_table(world_id, "factions")}


@router.get("/worlds/{world_id}/relationships")
async def api_relationships(world_id: str):
    return {"relationships": list_table(world_id, "relationships")}


@router.get("/staple-items")
async def api_staple_items():
    items = [item.model_dump(exclude={"lore_path"}) for item in load_staple_catalog()]
    return {"items": items}


@router.get("/worlds/{world_id}/items")
async def api_items(world_id: str):
    return {"items": list_resolved_items(world_id)}


@router.get("/worlds/{world_id}/world-items")
async def api_world_items(world_id: str):
    return {"items": list_table(world_id, "world_items")}


@router.get("/worlds/{world_id}/npc-inventory")
async def api_npc_inventory(world_id: str):
    return {"inventory": list_npc_inventory_items(world_id)}


@router.get("/worlds/{world_id}/lore/{entity_type}/{entity_id}")
async def api_lore(world_id: str, entity_type: str, entity_id: str):
    try:
        content = read_lore(world_id, entity_type, entity_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if content is None:
        raise HTTPException(status_code=404, detail="Lore not found.")
    return {"world_id": world_id, "entity_type": entity_type, "entity_id": entity_id, "content": content}


def initialize() -> None:
    init_db()
