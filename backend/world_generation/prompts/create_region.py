from typing import Optional

from pydantic import BaseModel

from world_generation.agent_framework_compat import step
from world_generation.prompts.common import feedback_block, generation_shape, region_shape, render_json_block
from world_generation.schemas import RegionDraft
from world_generation.step_runtime import run_structured_step


class RegionStep(BaseModel):
    title: str
    region: RegionDraft


def build_messages(prompt: str, previous_error: Optional[str] = None, previous_response: Optional[str] = None) -> list[dict[str, str]]:
    retry_feedback = feedback_block(previous_error, previous_response)
    prompt_body = f"""World prompt:
{prompt}

Task:
Create the region identity for a text RPG world. Return JSON with title and region only.

Target counts for follow-up steps:
{render_json_block(generation_shape())}

Required JSON shape:
{render_json_block({"title": "string", "region": region_shape()})}

Constraints:
- Keep the region concise: just a name and a description.
- Do not add quest hooks.
"""
    if retry_feedback:
        prompt_body += f"\nRetry feedback:\n{retry_feedback}\n"
    return [
        {"role": "system", "content": "You are the regional worldbuilding specialist. Return one valid JSON object only."},
        {"role": "user", "content": prompt_body},
    ]


@step(name="region")
async def run_step(state):
    parsed, transcript = await run_structured_step(
        model=state.model,
        step_name="region",
        schema=RegionStep,
        build_messages=lambda previous_error, previous_response: build_messages(
            state.prompt,
            previous_error,
            previous_response,
        ),
        updater=state.updater,
        transcripts=state.step_transcripts,
    )
    state.region_step = parsed
    state.total_latency_ms += transcript.latency_ms or 0
    return state
