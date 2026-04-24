from __future__ import annotations
"""Public concrete cognitive-tool plugin spec owned by zentex.plugins."""


from pydantic import ConfigDict, Field, model_validator

from zentex.plugins.contracts import BasePluginSpec


class CognitiveToolSpec(BasePluginSpec):
    model_config = ConfigDict(extra="allow", frozen=True, str_strip_whitespace=True)

    tool_type: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    input_schema: dict = Field(default_factory=dict)
    output_schema: dict = Field(default_factory=dict)
    required_context: list[str] = Field(default_factory=list)
    trigger_conditions: list[str] = Field(default_factory=list)
    do_not_use_when: list[str] = Field(default_factory=list)
    read_only: bool = True
    side_effect_free: bool = True

    @model_validator(mode="after")
    def validate_cognitive_tool_contract(self) -> "CognitiveToolSpec":
        if not self.read_only or not self.side_effect_free:
            raise ValueError("Cognitive tools must be strictly read_only=True and side_effect_free=True")
        if not self.trigger_conditions:
            raise ValueError("Cognitive tools must declare trigger_conditions")
        return self
