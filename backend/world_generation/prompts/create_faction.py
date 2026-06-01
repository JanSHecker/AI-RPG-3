from typing import Optional

from pydantic import BaseModel, Field

from providers import ProviderError
from world_generation.agent_framework_compat import step
from world_generation.prompts.common import faction_shape, feedback_block, generation_shape, render_json_block
from world_generation.schemas import FACTION_COUNT, FactionDraft, RegionDraft
from world_generation.step_runtime import run_structured_step


class FactionsStep(BaseModel):
    factions: list[FactionDraft] = Field(min_length=FACTION_COUNT, max_length=FACTION_COUNT)


def build_messages(prompt: str, region: RegionDraft, previous_error: Optional[str] = None, previous_response: Optional[str] = None) -> list[dict[str, str]]:
    retry_feedback = feedback_block(previous_error, previous_response)
    prompt_body = f"""World prompt:
{prompt}

Region:
{render_json_block(region.model_dump())}

Task:
Create factions for the world before places and characters are generated. Return JSON with factions only.

Target count:
{generation_shape()["factions"]}

Required JSON shape:
{render_json_block({"factions": [faction_shape()]})}

Constraints:
- Return exactly the requested number of factions.
- Each faction ref must be unique and use the format faction-kebab-case.
- home_place_ref must always be null because places do not exist yet.
- power_level must be 1-5.
- Each faction must include at least one required place and at least one required character.
- required_places and required_characters are planning notes for later generation, not saved faction database fields.
- requirement_relationships describe named links between required_places and required_characters only.
- requirement_relationships source_kind and target_kind must be place or character.
- requirement_relationships source_name and target_name must exactly match names from that faction's required lists.
- Write useful prose lore in Markdown.
"""
    if retry_feedback:
        prompt_body += f"\nRetry feedback:\n{retry_feedback}\n"
    return [
        {"role": "system", "content": "You are the political factions specialist. Return one valid JSON object only."},
        {"role": "user", "content": prompt_body},
    ]


@step(name="factions")
async def run_step(state):
    if state.region_step is None:
        raise ProviderError("Region step must complete before faction generation.")
    parsed, transcript = await run_structured_step(
        model=state.model,
        step_name="factions",
        schema=FactionsStep,
        build_messages=lambda previous_error, previous_response: build_messages(
            state.prompt,
            state.region_step.region,
            previous_error,
            previous_response,
        ),
        updater=state.updater,
        transcripts=state.step_transcripts,
    )
    state.factions_step = parsed
    state.total_latency_ms += transcript.latency_ms or 0
    return state
