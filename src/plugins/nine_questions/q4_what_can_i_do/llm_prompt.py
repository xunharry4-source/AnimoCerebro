from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from zentex.common.nine_questions_prompts import (
    assemble_prompt_sections,
    build_prompt_section,
)


_TEMPLATE_DIR = Path(__file__).resolve().with_name("prompt_templates")
_PLACEHOLDER_RE = re.compile(r"{{\s*([A-Z0-9_]+)\s*}}")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def _read_template(name: str) -> str:
    path = _TEMPLATE_DIR / name
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise RuntimeError(f"q4_prompt_template_missing:{path}") from exc


def _render_template(name: str, values: dict[str, str]) -> str:
    template = _read_template(name)

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in values:
            raise RuntimeError(f"q4_prompt_template_placeholder_missing:{name}:{key}")
        return values[key]

    return _PLACEHOLDER_RE.sub(replace, template).strip()


def build_q4_llm_request(
    *,
    capability_baseline: dict[str, Any],
    permission_profile: dict[str, Any],
    verification_probe_evidence: str,
    q2_internal_asset_inventory_evidence: str,
    q2_external_asset_inventory_evidence: str,
    q3_role_mission_evidence: str,
    snapshot_version: Any,
    q1_scene_model: Any,
    q1_uncertainty_profile: Any,
    q3_role_profile: Any,
    q3_mission_boundary: Any,
    q2_internal_tool_asset_inventory: dict[str, Any],
    q2_external_tool_asset_inventory: dict[str, Any],
    q2_unified_asset_inventory: dict[str, Any],
    q2_resource_evaluation: Any,
    q2_workspaces_and_permissions: Any,
    q2_memory_and_strategy: Any,
    active_execution_domains: list[str],
    functional_capabilities: list[dict[str, Any]],
    preprocessed_evidence: dict[str, Any],
) -> dict[str, Any]:
    q1_environment_json = _json(
        {
            "Q1_ENVIRONMENT": {
                "q1_scene_model": q1_scene_model,
                "q1_uncertainty_profile": q1_uncertainty_profile,
            }
        }
    )
    q2_assets_json = _json(
        {
            "Q2_ASSETS": {
                "internal_tool_inventory": q2_internal_tool_asset_inventory,
                "external_tool_inventory": q2_external_tool_asset_inventory,
                "unified_asset_inventory": q2_unified_asset_inventory,
            }
        }
    )
    q3_role_json = _json(
        {
            "q3_role_profile": q3_role_profile,
            "q3_mission_boundary": q3_mission_boundary,
        }
    )
    capability_context_json = _json(
        {
            "capability_baseline": capability_baseline,
            "permission_profile": permission_profile,
            "active_execution_domains": active_execution_domains[:24],
            "functional_capabilities": functional_capabilities[:12],
            "q2_resource_evaluation": q2_resource_evaluation,
            "q2_workspaces_and_permissions": q2_workspaces_and_permissions,
            "q2_memory_and_strategy": q2_memory_and_strategy,
            "preprocessed_evidence": preprocessed_evidence,
        }
    )
    template_values = {
        "Q1_ENVIRONMENT_JSON": q1_environment_json,
        "Q2_ASSETS_JSON": q2_assets_json,
        "Q3_ROLE_JSON": q3_role_json,
        "CAPABILITY_CONTEXT_JSON": capability_context_json,
        "Q2_INTERNAL_TOOL_ASSET_INVENTORY_EVIDENCE": q2_internal_asset_inventory_evidence,
        "Q2_EXTERNAL_TOOL_ASSET_INVENTORY_EVIDENCE": q2_external_asset_inventory_evidence,
        "Q3_ROLE_MISSION_EVIDENCE": q3_role_mission_evidence,
        "VERIFICATION_PROBE_EVIDENCE": verification_probe_evidence,
    }

    system_prompt_sections = [
        build_prompt_section(
            key="role",
            title="Role",
            intent="Define the Q4 capability-boundary task from file template.",
            purpose="Anchor the model on real internal and external capability boundaries.",
            content=_render_template("role.md", template_values),
        )
    ]
    prompt_sections = [
        build_prompt_section(
            key="input_spec",
            title="Inputs",
            intent="Define required Q1/Q2/Q3 inputs for Q4 from file template.",
            purpose="Make Q4 consume concrete upstream evidence through template placeholders.",
            content=_render_template("input_spec.md", template_values),
        ),
        build_prompt_section(
            key="internal_sop",
            title="Mandatory Capability SOP",
            intent="Force separate internal and external boundary reasoning before output.",
            purpose="Prevent generic or analysis-only output and prevent internal/external mixing.",
            content=_render_template("mandatory_sop.md", template_values),
        ),
        build_prompt_section(
            key="output_contract",
            title="Output Contract",
            intent="Define the exact CapabilityAssessment schema.",
            purpose="Forbid extra keys and force inference linkage fields.",
            content=_render_template("output_contract.md", template_values),
        ),
        build_prompt_section(
            key="q1_environment",
            title="Q1 Environment Situation",
            intent="Provide Q1 environmental evidence.",
            purpose="Align capability inference to concrete upstream signals.",
            content=_render_template("q1_environment.md", template_values),
        ),
        build_prompt_section(
            key="q2_internal_assets_tools",
            title="Q2 Internal Assets And Tools",
            intent="Provide Q2 internal cognitive assets and tool outputs.",
            purpose="Bind internal capability claims to Q2 internal LLM output.",
            content=_render_template("q2_internal_assets_tools.md", template_values),
        ),
        build_prompt_section(
            key="q2_external_assets_tools",
            title="Q2 External Assets And Tools",
            intent="Provide Q2 external assets and tool outputs.",
            purpose="Bind external capability claims to Q2 external LLM output.",
            content=_render_template("q2_external_assets_tools.md", template_values),
        ),
        build_prompt_section(
            key="verification_probes",
            title="Verification Probes",
            intent="Provide current-session probe and permission evidence.",
            purpose="Keep inference anchored in real execution boundary context.",
            content=_render_template("verification_probes.md", template_values),
        ),
        build_prompt_section(
            key="q3_role_profile",
            title="Q3 Role Profile",
            intent="Provide Q3 role profile and mission boundary evidence.",
            purpose="Constrain capability combinations to the active role.",
            content=_render_template("q3_role_profile.md", template_values),
        ),
    ]
    system_prompt = assemble_prompt_sections(system_prompt_sections)
    prompt = assemble_prompt_sections(prompt_sections)
    model_context = {
        "snapshot_version": snapshot_version,
        "q1_scene_model": q1_scene_model,
        "q1_uncertainty_profile": q1_uncertainty_profile,
        "q2_internal_tool_asset_inventory": q2_internal_tool_asset_inventory,
        "q2_external_tool_asset_inventory": q2_external_tool_asset_inventory,
        "q2_unified_asset_inventory": q2_unified_asset_inventory,
        "q2_resource_evaluation": q2_resource_evaluation,
        "q2_workspaces_and_permissions": q2_workspaces_and_permissions,
        "q2_memory_and_strategy": q2_memory_and_strategy,
        "q3_role_profile": q3_role_profile,
        "q3_mission_boundary": q3_mission_boundary,
        "active_execution_domains": active_execution_domains[:24],
        "permission_profile": permission_profile,
        "capability_baseline": capability_baseline,
        "functional_capabilities": functional_capabilities[:12],
        "preprocessed_evidence": preprocessed_evidence,
        "template_files": {
            "system": str(_TEMPLATE_DIR / "role.md"),
            "prompt_sections": [str(_TEMPLATE_DIR / path) for path in (
                "input_spec.md",
                "mandatory_sop.md",
                "output_contract.md",
                "q1_environment.md",
                "q2_internal_assets_tools.md",
                "q2_external_assets_tools.md",
                "verification_probes.md",
                "q3_role_profile.md",
            )],
        },
    }
    return {
        "system_prompt": system_prompt,
        "prompt": prompt,
        "system_prompt_sections": system_prompt_sections,
        "prompt_sections": prompt_sections,
        "model_context": model_context,
    }
