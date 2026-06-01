from typing import Optional

from model_catalog import ConfiguredModel
from world_generation.agent_workflows import build_world_items_draft as build_world_items_workflow_draft
from world_generation.prompts.create_items import WorldItemsStep
from world_generation.schemas import WorldDraft, WorldItemDraft


async def build_world_items_draft(
    prompt: str,
    model: ConfiguredModel,
    world: WorldDraft,
    scaffold: list[WorldItemDraft],
    previous_error: Optional[str] = None,
    previous_response: Optional[str] = None,
) -> tuple[WorldItemsStep, str, int]:
    return await build_world_items_workflow_draft(
        prompt,
        model,
        world,
        scaffold,
        previous_error=previous_error,
        previous_response=previous_response,
    )
