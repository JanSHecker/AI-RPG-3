from typing import Optional

from pydantic import BaseModel

from world_generation.agent_framework_compat import step
from world_generation.prompts.common import feedback_block, render_json_block
from world_generation.schemas import WorldDraft, WorldItemDraft
from world_generation.step_runtime import run_structured_step


class WorldItemsStep(BaseModel):
    world_items: list[WorldItemDraft]


def build_messages(prompt: str, world: WorldDraft, scaffold: list[WorldItemDraft], previous_error: Optional[str] = None, previous_response: Optional[str] = None) -> list[dict[str, str]]:
    retry_feedback = feedback_block(previous_error, previous_response)
    prompt_body = f"""World prompt:
{prompt}

World:
{render_json_block(world.model_dump())}

Task:
Create special world-specific items. Return JSON with world_items only.

Required JSON shape:
{render_json_block({"world_items": [item.model_dump() for item in scaffold]})}

Constraints:
- Keep every item ref exactly as provided.
- Return only world_items.
- Write useful prose-oriented summaries.
- Do not return staple items or common gear.
- These are notable items with local story value.
"""
    if retry_feedback:
        prompt_body += f"\nRetry feedback:\n{retry_feedback}\n"
    return [
        {"role": "system", "content": "You are the special items specialist. Return one valid JSON object only."},
        {"role": "user", "content": prompt_body},
    ]


@step(name="world_items")
async def run_step(state):
    parsed, transcript = await run_structured_step(
        model=state.model,
        step_name="world_items",
        schema=WorldItemsStep,
        build_messages=lambda previous_error, previous_response: build_messages(
            state.prompt,
            state.world,
            state.scaffold,
            previous_error,
            previous_response,
        ),
        updater=state.updater,
        transcripts=state.step_transcripts,
        initial_previous_error=state.initial_previous_error,
        initial_previous_response=state.initial_previous_response,
    )
    state.world_items_step = parsed
    state.total_latency_ms += transcript.latency_ms or 0
    return state
