from __future__ import annotations

import hashlib
import json
import random
from math import sqrt

from providers import ProviderError
from world_generation.agent_framework_compat import step
from world_generation.schemas import (
    DUNGEON_LOCATION_COUNT,
    FACTION_LOCATION_COUNT,
    NEUTRAL_VILLAGE_COUNT,
    FactionDraft,
    LocationPlanBatch,
    LocationPlanSlot,
    LocationPlanStep,
    PLACE_COUNT,
    TERRAINS,
    RegionDraft,
)
from world_generation.step_runtime import AttemptRecord, StepTranscript, step_label, update_step


FACTION_SLOT_TYPES = ["town", "fortress", "village", "landmark", "road"]
NEUTRAL_SLOT_TYPES = ["village"]
DANGEROUS_SLOT_TEMPLATES = [
    ("dungeon", "sealed depth", 5, 0),
    ("dungeon", "monster lair", 5, 0),
    ("ruin", "fallen stronghold", 4, 0),
    ("forest", "haunted wild", 3, 0),
    ("landmark", "cursed monument", 4, 0),
]


def _seed(prompt: str, region: RegionDraft, factions: list[FactionDraft]) -> int:
    payload = {
        "prompt": prompt,
        "region": region.model_dump(),
        "factions": [faction.ref for faction in factions],
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def _clamp(value: int, low: int = 0, high: int = 100) -> int:
    return max(low, min(high, value))


def _jittered_point(rng: random.Random, center_x: int, center_y: int, radius: int) -> tuple[int, int]:
    return (
        _clamp(center_x + rng.randint(-radius, radius)),
        _clamp(center_y + rng.randint(-radius, radius)),
    )


def _distance(point: tuple[int, int], other: tuple[int, int]) -> float:
    return sqrt((point[0] - other[0]) ** 2 + (point[1] - other[1]) ** 2)


def _anchor_points(rng: random.Random, count: int) -> list[tuple[int, int]]:
    candidates = [(20, 20), (80, 20), (20, 80), (80, 80), (50, 15), (50, 85), (15, 50), (85, 50)]
    rng.shuffle(candidates)
    return candidates[:count]


def _ref(prefix: str, index: int, suffix: str = "") -> str:
    parts = [prefix, f"{index + 1:02d}"]
    if suffix:
        parts.append(suffix)
    return "-".join(parts)


def _make_faction_batch(
    rng: random.Random,
    faction: FactionDraft,
    faction_index: int,
    center: tuple[int, int],
) -> LocationPlanBatch:
    cluster_id = f"cluster-{faction.ref}"
    slots: list[LocationPlanSlot] = []
    required_places = faction.required_places or []
    for slot_index in range(FACTION_LOCATION_COUNT):
        place_type = FACTION_SLOT_TYPES[slot_index % len(FACTION_SLOT_TYPES)]
        if slot_index == 0:
            place_type = "town"
        x, y = _jittered_point(rng, center[0], center[1], 13)
        required_place = required_places[slot_index % len(required_places)] if required_places else None
        slots.append(
            LocationPlanSlot(
                ref=f"place-{faction.ref.removeprefix('faction-')}-{slot_index + 1:02d}",
                place_type=place_type,
                x=x,
                y=y,
                cluster_id=cluster_id,
                cluster_kind="faction",
                faction_ref=faction.ref,
                terrain_hint=rng.choice(TERRAINS),
                danger_level_hint=_clamp(faction.power_level + rng.choice([-1, 0, 0, 1]), 1, 5),
                population_hint=1200 if place_type == "town" else 350 if place_type == "village" else 80,
                purpose=required_place.description if required_place else f"{faction.name} regional {place_type}",
                theme=required_place.name if required_place else f"{faction.name} influence site",
            )
        )
    return LocationPlanBatch(
        batch_id=f"batch-faction-{faction_index + 1:02d}",
        batch_kind="faction_cluster",
        faction_ref=faction.ref,
        center_x=center[0],
        center_y=center[1],
        slots=slots,
    )


def _make_neutral_batch(rng: random.Random, centers: list[tuple[int, int]]) -> LocationPlanBatch:
    slots: list[LocationPlanSlot] = []
    for slot_index in range(NEUTRAL_VILLAGE_COUNT):
        best = max(
            ((rng.randint(10, 90), rng.randint(10, 90)) for _ in range(12)),
            key=lambda point: min(_distance(point, center) for center in centers) if centers else 100,
        )
        slots.append(
            LocationPlanSlot(
                ref=_ref("place-neutral-village", slot_index),
                place_type=NEUTRAL_SLOT_TYPES[slot_index % len(NEUTRAL_SLOT_TYPES)],
                x=best[0],
                y=best[1],
                cluster_id="cluster-neutral-villages",
                cluster_kind="neutral",
                faction_ref=None,
                terrain_hint=rng.choice(TERRAINS),
                danger_level_hint=rng.choice([1, 1, 2, 2, 3]),
                population_hint=rng.randint(180, 650),
                purpose="Independent settlement outside faction control",
                theme="neutral village",
            )
        )
    center_x = round(sum(slot.x for slot in slots) / len(slots))
    center_y = round(sum(slot.y for slot in slots) / len(slots))
    return LocationPlanBatch(
        batch_id="batch-neutral-villages",
        batch_kind="neutral_villages",
        center_x=center_x,
        center_y=center_y,
        slots=slots,
    )


def _make_dangerous_batch(rng: random.Random, centers: list[tuple[int, int]]) -> LocationPlanBatch:
    slots: list[LocationPlanSlot] = []
    for slot_index in range(DUNGEON_LOCATION_COUNT):
        place_type, theme, danger, population = DANGEROUS_SLOT_TEMPLATES[slot_index % len(DANGEROUS_SLOT_TEMPLATES)]
        base = rng.choice(centers) if centers else (50, 50)
        x, y = _jittered_point(rng, base[0], base[1], 24)
        slots.append(
            LocationPlanSlot(
                ref=_ref("place-danger", slot_index, place_type),
                place_type=place_type,
                x=x,
                y=y,
                cluster_id="cluster-dangerous-sites",
                cluster_kind="dangerous",
                faction_ref=None,
                terrain_hint=rng.choice(TERRAINS),
                danger_level_hint=danger,
                population_hint=population,
                purpose="Adventure site, threat, or exploration landmark",
                theme=theme,
            )
        )
    center_x = round(sum(slot.x for slot in slots) / len(slots))
    center_y = round(sum(slot.y for slot in slots) / len(slots))
    return LocationPlanBatch(
        batch_id="batch-dangerous-sites",
        batch_kind="dangerous_sites",
        center_x=center_x,
        center_y=center_y,
        slots=slots,
    )


def build_location_plan(prompt: str, region: RegionDraft, factions: list[FactionDraft]) -> LocationPlanStep:
    rng = random.Random(_seed(prompt, region, factions))
    centers = _anchor_points(rng, len(factions))
    batches = [
        _make_faction_batch(rng, faction, faction_index, centers[faction_index])
        for faction_index, faction in enumerate(factions)
    ]
    batches.append(_make_neutral_batch(rng, centers))
    batches.append(_make_dangerous_batch(rng, centers))
    slots = [slot for batch in batches for slot in batch.slots]
    if len(slots) != PLACE_COUNT:
        raise ProviderError(f"Location plan produced {len(slots)} slots instead of {PLACE_COUNT}.")
    if len({slot.ref for slot in slots}) != len(slots):
        raise ProviderError("Location plan produced duplicate place refs.")
    return LocationPlanStep(batches=batches, slots=slots)


@step(name="location_plan")
async def run_step(state):
    if state.region_step is None or state.factions_step is None:
        raise ProviderError("Region and factions steps must complete before location planning.")
    await update_step(state.updater, "location_plan", "running", attempts=1, error="")
    try:
        parsed = build_location_plan(state.prompt, state.region_step.region, state.factions_step.factions)
    except Exception as exc:
        await update_step(state.updater, "location_plan", "failed", attempts=1, error=str(exc), raw_response="")
        raise

    payload = parsed.model_dump()
    transcript = StepTranscript(
        name="location_plan",
        label=step_label("location_plan"),
        status="done",
        attempts=[
            AttemptRecord(
                attempt=1,
                status="done",
                raw_response=json.dumps(payload, ensure_ascii=False),
                latency_ms=0,
                parsed_payload=payload,
            )
        ],
        latency_ms=0,
        parsed_payload=payload,
    )
    state.step_transcripts.append(transcript)
    state.location_plan_step = parsed
    await update_step(
        state.updater,
        "location_plan",
        "done",
        attempts=1,
        error="",
        raw_response=json.dumps(payload, ensure_ascii=False),
        parsed_payload=payload,
        latency_ms=0,
    )
    return state
