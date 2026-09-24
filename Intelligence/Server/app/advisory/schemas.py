"""Public advisory response schema."""

from pydantic import BaseModel, Field


class AdvisoryResult(BaseModel):
    """Only user-facing advisory fields are serialized."""

    severity: str
    advice: str
    actions: list[str] = Field(default_factory=list)
    weather_advice: str
