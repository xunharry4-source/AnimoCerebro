from __future__ import annotations

from ..objective_profile_contract import build_q8_external_objective_profile_prompt


def build_q8_external_system_prompt() -> str:
    return build_q8_external_objective_profile_prompt()
