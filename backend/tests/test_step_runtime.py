import json

from pydantic import BaseModel, ValidationError, field_validator

from world_generation.step_runtime import validation_feedback, validation_text


class ModelWithValueErrorContext(BaseModel):
    value: str

    @field_validator("value")
    @classmethod
    def validate_value(cls, value: str) -> str:
        raise ValueError(f"Invalid value: {value}")


def test_validation_text_serializes_pydantic_value_error_context():
    try:
        ModelWithValueErrorContext.model_validate({"value": "bad"})
    except ValidationError as exc:
        text = validation_text(exc)

    errors = json.loads(text)
    assert errors[0]["ctx"]["error"] == "Invalid value: bad"


class NpcWithCatalogPersonality(BaseModel):
    ref: str
    personality: list[str]

    @field_validator("personality")
    @classmethod
    def validate_personality(cls, value: list[str]) -> list[str]:
        invalid = [entry for entry in value if entry == "calculating"]
        if invalid:
            raise ValueError(f"NPC personality values must come from the personality catalog; got {invalid}.")
        return value


class NpcBatchWithCatalogPersonality(BaseModel):
    npcs: list[NpcWithCatalogPersonality]


def test_validation_feedback_adds_location_ref_and_replacement_hint():
    payload = {
        "npcs": [
            {
                "ref": "npc-mill-warden",
                "personality": ["patient", "reserved", "calculating"],
            }
        ]
    }

    try:
        NpcBatchWithCatalogPersonality.model_validate(payload)
    except ValidationError as exc:
        text = validation_feedback(exc, payload)

    assert "Correction summary:" in text
    assert "npcs[0].personality" in text
    assert "npc-mill-warden" in text
    assert "calculating" in text
    assert "exact allowed catalog value" in text
