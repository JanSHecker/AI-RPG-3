from typing import Optional

from pydantic import BaseModel, Field

from providers import ProviderError
from world_generation.agent_framework_compat import step
from world_generation.prompts.common import feedback_block, generation_shape, relationship_shape, render_json_block
from world_generation.schemas import RELATIONSHIP_COUNT, FactionDraft, NpcDraft, PlaceDraft, RegionDraft, RelationshipDraft
from world_generation.step_runtime import run_structured_step


class RelationshipsStep(BaseModel):
    relationships: list[RelationshipDraft] = Field(min_length=RELATIONSHIP_COUNT, max_length=RELATIONSHIP_COUNT)


def build_messages(prompt: str, region: RegionDraft, places: list[PlaceDraft], factions: list[FactionDraft], npcs: list[NpcDraft], previous_error: Optional[str] = None, previous_response: Optional[str] = None) -> list[dict[str, str]]:
    retry_feedback = feedback_block(previous_error, previous_response)
    prompt_body = f"""World prompt:
{prompt}

Region:
{render_json_block(region.model_dump())}

Places:
{render_json_block([place.model_dump() for place in places])}

Factions:
{render_json_block([faction.model_dump() for faction in factions])}

NPCs:
{render_json_block([npc.model_dump() for npc in npcs])}

Task:
Create relationships between existing entities. Return JSON with relationships only.

Target count:
{generation_shape()["relationships"]}

Required JSON shape:
{render_json_block({"relationships": [relationship_shape()]})}

Constraints:
- Return exactly the requested number of relationships.
- Each relationship ref must be unique and use the format rel-kebab-case.
- source_type and target_type must be place, faction, or npc.
- source_ref and target_ref must reference provided refs of the matching types.
"""
    if retry_feedback:
        prompt_body += f"\nRetry feedback:\n{retry_feedback}\n"
    return [
        {"role": "system", "content": "You are the relationship graph specialist. Return one valid JSON object only."},
        {"role": "user", "content": prompt_body},
    ]


@step(name="relationships")
async def run_step(state):
    if (
        state.region_step is None
        or state.places_step is None
        or state.factions_step is None
        or state.npc_step is None
    ):
        raise ProviderError("Region, places, factions, and NPC steps must complete before relationship generation.")
    parsed, transcript = await run_structured_step(
        model=state.model,
        step_name="relationships",
        schema=RelationshipsStep,
        build_messages=lambda previous_error, previous_response: build_messages(
            state.prompt,
            state.region_step.region,
            state.places_step.places,
            state.factions_step.factions,
            state.npc_step.npcs,
            previous_error,
            previous_response,
        ),
        updater=state.updater,
        transcripts=state.step_transcripts,
    )
    state.relationships_step = parsed
    state.total_latency_ms += transcript.latency_ms or 0
    return state
