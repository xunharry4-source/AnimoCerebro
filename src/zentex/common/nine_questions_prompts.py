from __future__ import annotations

import logging
from typing import Any
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt Section Utilities (from prompt_sections.py)
# ---------------------------------------------------------------------------

def build_prompt_section(
    *,
    key: str,
    title: str,
    intent: str,
    purpose: str,
    content: str,
) -> dict[str, str]:
    """Helper to build a standardized prompt section dictionary."""
    return {
        "key": key,
        "title": title,
        "intent": intent,
        "purpose": purpose,
        "content": str(content or "").strip(),
    }


def assemble_prompt_sections(
    sections: list[dict[str, str]],
) -> str:
    """Assemble a list of prompt sections into a single markdown-formatted string."""
    rendered: list[str] = []
    for section in sections:
        title = str(section.get("title") or "").strip()
        intent = str(section.get("intent") or "").strip()
        purpose = str(section.get("purpose") or "").strip()
        content = str(section.get("content") or "").strip()

        lines: list[str] = []
        if title:
            lines.append(f"### {title}")
        if intent:
            lines.append(f"[Intent] {intent}")
        if purpose:
            lines.append(f"[Purpose] {purpose}")
        if content:
            lines.append(content)

        block = "\n".join(line for line in lines if line.strip()).strip()
        if block:
            rendered.append(block)
    return "\n\n".join(rendered).strip()


def trim_section_content(value: Any) -> str:
    return str(value or "(empty)").strip()


# ---------------------------------------------------------------------------
# Prompt Optimization Contracts (from prompt_upgrade_contract.py)
# ---------------------------------------------------------------------------

class PromptSectionChangePolicy(BaseModel):
    """Per-section edit policy for prompt optimization."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    section_key: str = Field(min_length=1)
    mutable: bool = False
    intent: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    allowed_operations: list[str] = Field(default_factory=list)
    forbidden_operations: list[str] = Field(default_factory=list)


class NineQuestionPromptUpgradeContract(BaseModel):
    """Guardrails for prompt-only upgrades of a single nine-question module."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    question_id: str = Field(min_length=1)
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
            "question_id": self.question_id,
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
