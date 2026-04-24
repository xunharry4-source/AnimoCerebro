from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class PromptSectionChangePolicy(BaseModel):
    """Per-section edit policy for prompt optimization."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    section_key: str = Field(min_length=1)
    mutable: bool = False
    intent: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    allowed_operations: list[str] = Field(default_factory=list)
    forbidden_operations: list[str] = Field(default_factory=list)


class ModulePromptUpgradeContract(BaseModel):
    """Guardrails for prompt-only upgrades of a single non-nine-question module."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    prompt_id: str = Field(min_length=1)
    module_id: str = Field(min_length=1)
    prompt_file_path: str = Field(min_length=1)
    prompt_builder_name: str = Field(min_length=1)
    prompt_builder_symbol: str = Field(min_length=1)
    target_component: str = Field(min_length=1)
    immutable_intent: str = Field(min_length=1)
    expected_output_key: str = Field(min_length=1)
    allowed_prompt_change_scope: list[str] = Field(default_factory=list)
    forbidden_prompt_changes: list[str] = Field(default_factory=list)
    validation_commands: list[str] = Field(default_factory=list)
    editable_prompt_sections: list[str] = Field(default_factory=list)
    immutable_prompt_sections: list[str] = Field(default_factory=list)
    section_change_policy: list[PromptSectionChangePolicy] = Field(default_factory=list)

    def to_prompt_contract(self) -> dict[str, object]:
        return {
            "prompt_id": self.prompt_id,
            "module_id": self.module_id,
            "prompt_builder_name": self.prompt_builder_name,
            "expected_output_key": self.expected_output_key,
            "editable_prompt_sections": list(self.editable_prompt_sections),
            "immutable_prompt_sections": list(self.immutable_prompt_sections),
            "section_change_policy": [
                policy.model_dump(mode="json") for policy in self.section_change_policy
            ],
        }


def build_section_policy(
    *,
    section_key: str,
    mutable: bool,
    intent: str,
    purpose: str,
    allowed_operations: list[Optional[str]] = None,
    forbidden_operations: list[Optional[str]] = None,
) -> PromptSectionChangePolicy:
    return PromptSectionChangePolicy(
        section_key=section_key,
        mutable=mutable,
        intent=intent,
        purpose=purpose,
        allowed_operations=list(allowed_operations or []),
        forbidden_operations=list(forbidden_operations or []),
    )
