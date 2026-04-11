from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class FeatureFamily(BaseModel):
    """
    Strongly-typed feature domain definition for the plugin bus.

    `feature_code` is the only routing key used by runtime components and
    management panels. Plugin implementations are discovered and bound through
    registries by this code (IoC/OCP).
    """

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    feature_code: str = Field(min_length=1)
    supports_multiple_plugins: bool = False

