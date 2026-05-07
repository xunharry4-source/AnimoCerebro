from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, ConfigDict

from plugins.nine_questions.q2_asset_inventory.llm_output_table import (
    load_q2_audit_id_from_table,
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
    for candidate in _iter_q2_audit_id_candidates(context):
        value = str(candidate or "").strip()
        if value:
            return value
    try:
        return load_q2_audit_id_from_table(session_id=session_id)
    except RuntimeError as exc:
        raise RuntimeError("q3_q2_audit_id_missing") from exc


def _iter_q2_audit_id_candidates(context: dict[str, Any]):
    yield context.get("q2_audit_id")

    q2_audit_provenance = context.get("q2_audit_provenance")
    if isinstance(q2_audit_provenance, dict):
        yield q2_audit_provenance.get("audit_id")

    yield from _iter_module_run_audit_ids(context.get("q2_execution_diagnosis"))

    snapshots = context.get("question_snapshots")
    q2_snapshot = snapshots.get("q2") if isinstance(snapshots, dict) else None
    if isinstance(q2_snapshot, dict):
        for key in ("context_updates", "result", "execution_result"):
            payload = q2_snapshot.get(key)
            if not isinstance(payload, dict):
                continue
            yield payload.get("q2_audit_id")
            provenance = payload.get("q2_audit_provenance")
            if isinstance(provenance, dict):
                yield provenance.get("audit_id")
            yield from _iter_module_run_audit_ids(payload.get("q2_execution_diagnosis"))
            nested_updates = payload.get("context_updates")
            if isinstance(nested_updates, dict):
                yield nested_updates.get("q2_audit_id")
                nested_provenance = nested_updates.get("q2_audit_provenance")
                if isinstance(nested_provenance, dict):
                    yield nested_provenance.get("audit_id")
                yield from _iter_module_run_audit_ids(nested_updates.get("q2_execution_diagnosis"))


def _iter_module_run_audit_ids(diagnosis: Any):
    if not isinstance(diagnosis, dict):
        return
    module_runs = diagnosis.get("module_runs")
    if not isinstance(module_runs, list):
        return
    for module in module_runs:
        if not isinstance(module, dict):
            continue
        data = module.get("data")
        if isinstance(data, dict):
            yield data.get("audit_id")


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
            "read q2 audit_id from upstream context or nine_question_q2_snapshots.context_updates_json",
            "run q3 external role LLM",
            "save q3 llm input and output",
            "append q3 audit entry with q2 audit_id",
        ],
        "q3_llm_input": llm_input,
        "q3_llm_output": llm_output,
    }
