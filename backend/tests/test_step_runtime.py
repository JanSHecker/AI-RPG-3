import json

from pydantic import BaseModel, ValidationError, field_validator

from world_generation.step_runtime import validation_text


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
