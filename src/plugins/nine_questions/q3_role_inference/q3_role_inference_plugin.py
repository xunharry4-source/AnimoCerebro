from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, ConfigDict

from plugins.nine_questions.q2_asset_inventory.service import (
    load_public_audit_id,
)
from plugins.nine_questions.q3_role_inference.external.service import (
    run_q3_external_llm_and_save,
)
from zentex.common.cognitive_result import CognitiveToolResult
from zentex.common.nine_questions_shared import bind_module_runs, run_audit_integration
from zentex.common.plugin_ids import NINE_QUESTION_Q3
from zentex.plugins.models import PluginLifecycleStatus

logger = logging.getLogger(__name__)


class Q3RoleInferencePlugin(BaseModel):
    model_config = ConfigDict(extra="allow")

    plugin_id: str = NINE_QUESTION_Q3
    version: str = "1.0.0"
    feature_code: str = "nine_questions.q3"
    display_name: str = "Q3: 我是谁"
    behavior_key: str = "nine_questions"
    lifecycle_status: str = PluginLifecycleStatus.ACTIVE.value
    health_status: str = "healthy"
    operational_status: str = "enabled"

    def run_tool(self, context: dict[str, Any]) -> CognitiveToolResult:
        module_runs = bind_module_runs(context, "q3")
        session_id = str(context.get("session_id") or "nq-baseline")
        q2_audit_id = _extract_q2_audit_id(context, session_id=session_id)
        if _has_real_audit_service(context) and not q2_audit_id:
            raise RuntimeError("q3_q2_audit_id_missing")

        external = run_q3_external_llm_and_save(context)
        llm_output = {
            "q3_external_llm_input": external["llm_input"],
            "q3_external_llm_output": external["llm_output"],
        }
        audit_provenance = _build_q3_audit_provenance(
            q2_audit_id=q2_audit_id,
            llm_input=external["llm_input"],
            llm_output=external["llm_output"],
        )
        audit_run = run_audit_integration(
            context,
            question_id="q3",
            module_runs=module_runs,
            summary="Q3 角色推断 LLM 调用记录已追加到 Q2 审计链。",
            payload=audit_provenance,
            audit_id=q2_audit_id,
        )
        q3_audit_id = str(((audit_run.get("data") or {}).get("audit_id") or "")).strip()
        if q3_audit_id != q2_audit_id:
            raise RuntimeError("q3_audit_chain_mismatch")
        if q3_audit_id:
            audit_provenance["audit_id"] = q3_audit_id
        return CognitiveToolResult(
            tool_id=self.plugin_id,
            summary="Q3 external role LLM input and output saved.",
            llm_output=llm_output,
            context_updates={
                **llm_output,
                "q3_external_role_posture": external["result"],
                "q3_audit_id": q3_audit_id,
                "q3_audit_provenance": audit_provenance,
            },
            confidence=0.75,
        )


def build_q3_role_inference_plugin(
    *,
    plugin_id: str = NINE_QUESTION_Q3,
    version: str = "1.0.0",
    lifecycle_status: str | PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE,
) -> Q3RoleInferencePlugin:
    return Q3RoleInferencePlugin(
        plugin_id=plugin_id,
        version=version,
        lifecycle_status=getattr(lifecycle_status, "value", lifecycle_status),
    )


def _has_real_audit_service(context: dict[str, Any]) -> bool:
    audit_service = context.get("audit_service")
    return audit_service is not None and not bool(getattr(audit_service, "_is_stub", False))


def _extract_q2_audit_id(context: dict[str, Any], *, session_id: str) -> str:
    db_path = context.get("nine_question_state_db_path")
    try:
        return load_public_audit_id(db_path=db_path, session_id=session_id)
    except RuntimeError as exc:
        raise RuntimeError("q3_q2_audit_id_missing") from exc


def _build_q3_audit_provenance(
    *,
    q2_audit_id: str,
    llm_input: dict[str, Any],
    llm_output: dict[str, Any],
) -> dict[str, Any]:
    return {
        "question_id": "q3",
        "q2_audit_id": q2_audit_id,
        "source_module": "plugins.nine_questions.q3_role_inference",
        "source_of_truth": "nine_question_q3_snapshots.llm_output_json",
        "audit_chain_rule": "reuse_q2_audit_id",
        "save_flow": [
            "read q2 audit_id through q2 public service accessor",
            "run q3 external role LLM",
            "save q3 llm input and output",
            "append q3 audit entry with q2 audit_id",
        ],
        "q3_llm_input": llm_input,
        "q3_llm_output": llm_output,
    }
