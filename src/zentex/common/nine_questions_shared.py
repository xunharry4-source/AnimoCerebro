from __future__ import annotations

"""Shared utilities for nine-questions cognitive plugins.

These helpers are used across Q1-Q9 plugin implementations.
Kept in zentex/common to avoid polluting the nine_questions plugin group
directory with non-plugin code.
"""

from datetime import datetime, timezone
import json
from typing import Any, Dict, List, Optional
from uuid import uuid4

from zentex.core.model_provider_spec import ModelProviderCallerContext, ModelProviderSpec
from zentex.runtime.transcript import BrainTranscriptEntryType, BrainTranscriptStore


def require_model_provider(context: Dict[str, Any]) -> ModelProviderSpec:
    provider = context.get("model_provider")
    if provider is None or not hasattr(provider, "generate_json"):
        registry = context.get("plugin_registry")
        if registry is not None and callable(getattr(registry, "get_bound_plugin", None)):
            try:
                provider = registry.get_bound_plugin(ModelProviderSpec)
            except Exception as exc:
                raise RuntimeError(
                    "LLM MANDATORY: missing active ModelProvider in context['model_provider'] "
                    "and plugin_registry binding failed"
                ) from exc
        else:
            raise RuntimeError(
                "LLM MANDATORY: missing active ModelProvider in context['model_provider']"
            )
    return provider


def require_transcript_store(context: Dict[str, Any]) -> BrainTranscriptStore:
    store = context.get("transcript_store")
    if not isinstance(store, BrainTranscriptStore):
        raise RuntimeError("transcript_store is required for auditable replay")
    return store


def build_caller_context(
    *,
    source_module: str,
    invocation_phase: str,
    question_ref: str,
    question_driver_refs: List[str] | None = None,
    decision_id: Optional[str] = None,
    trace_id: Optional[str] = None,
) -> ModelProviderCallerContext:
    driver_refs: List[str]
    if question_driver_refs and any(str(item).strip() for item in question_driver_refs):
        driver_refs = [str(item) for item in question_driver_refs if str(item).strip()]
        if question_ref not in driver_refs:
            driver_refs.append(question_ref)
    else:
        driver_refs = [question_ref]
    return ModelProviderCallerContext(
        source_module=source_module,
        invocation_phase=invocation_phase,
        question_driver_refs=driver_refs,
        decision_id=decision_id,
        trace_id=trace_id,
    )


def build_model_context(context: Dict[str, Any]) -> Dict[str, Any]:
    # Ensure we never leak non-serializable runtime objects into the model prompt.
    stripped: Dict[str, Any] = {}
    for key, value in context.items():
        if key in {"model_provider", "transcript_store", "nine_question_state", "plugin_registry"}:
            continue
        stripped[key] = value
    return stripped


def safe_provider_plugin_id(provider: Any) -> str | None:
    candidate = getattr(provider, "plugin_id", None) or getattr(provider, "provider_name", None)
    if isinstance(candidate, str):
        text = candidate.strip()
        return text or None
    return None


def json_safe_payload(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [json_safe_payload(item) for item in value]
    if isinstance(value, dict):
        return {str(key): json_safe_payload(item) for key, item in value.items()}
    return None


def humanize_identifier(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return "未知项"
    normalized = text.replace("_", " ").replace("-", " ").replace(":", " ").replace(".", " ")
    return " ".join(chunk.capitalize() for chunk in normalized.split())


def _humanize_key(key: object) -> str:
    text = str(key or "").strip()
    if not text:
        return "未命名字段"
    return text.replace("_", " ").replace("-", " ").strip()


def render_human_readable_block(
    value: Any,
    *,
    heading: str | None = None,
    indent: int = 0,
    max_items: int = 12,
) -> str:
    prefix = "  " * indent
    lines: list[str] = []
    if heading:
        lines.append(f"{prefix}{heading}")

    if value is None:
        lines.append(f"{prefix}- 无")
        return "\n".join(lines)

    if isinstance(value, (str, int, float, bool)):
        lines.append(f"{prefix}- {value}")
        return "\n".join(lines)

    if isinstance(value, dict):
        if not value:
            lines.append(f"{prefix}- 无")
            return "\n".join(lines)
        for index, (key, item) in enumerate(value.items()):
            if index >= max_items:
                lines.append(f"{prefix}- 其余字段已省略")
                break
            label = _humanize_key(key)
            if isinstance(item, (dict, list)):
                lines.append(f"{prefix}- {label}:")
                lines.append(render_human_readable_block(item, indent=indent + 1, max_items=max_items))
            else:
                lines.append(f"{prefix}- {label}: {item}")
        return "\n".join(lines)

    if isinstance(value, list):
        if not value:
            lines.append(f"{prefix}- 无")
            return "\n".join(lines)
        for index, item in enumerate(value):
            if index >= max_items:
                lines.append(f"{prefix}- 其余条目已省略")
                break
            if isinstance(item, (dict, list)):
                lines.append(f"{prefix}- 条目 {index + 1}:")
                lines.append(render_human_readable_block(item, indent=indent + 1, max_items=max_items))
            else:
                lines.append(f"{prefix}- {item}")
        return "\n".join(lines)

    lines.append(f"{prefix}- {str(value)}")
    return "\n".join(lines)


def render_plugin_catalog(plugin_ids: list[str], *, heading: str) -> str:
    rows = [
        {
            "名称": humanize_identifier(item),
            "内部标识": item,
            "功能说明": f"{humanize_identifier(item)} 提供与 {item} 对应的运行能力。",
        }
        for item in plugin_ids
    ]
    return render_human_readable_block(rows, heading=heading)


def render_q3_asset_inventory(context: dict[str, Any]) -> str:
    inventory = context.get("q3_humanized_asset_inventory") or context.get("q3_unified_asset_inventory") or {}
    return render_human_readable_block(inventory, heading="Q3 资产清单")


def render_q4_boundary(context: dict[str, Any]) -> str:
    return render_human_readable_block(
        context.get("q4_capability_boundary_profile") or context.get("q4_inference_result") or {},
        heading="Q4 能力边界",
    )


def render_q5_boundary(context: dict[str, Any]) -> str:
    return render_human_readable_block(
        context.get("q5_permission_boundary")
        or context.get("q5_authorization_boundary_profile")
        or context.get("q5_inference_result")
        or {},
        heading="Q5 授权边界",
    )


def render_q6_redlines(context: dict[str, Any]) -> str:
    return render_human_readable_block(
        context.get("q6_forbidden_zone_profile") or {},
        heading="Q6 红线禁区",
    )


def render_identity_kernel(context: dict[str, Any]) -> str:
    return render_human_readable_block(
        context.get("identity_kernel") or context.get("identity_kernel_snapshot") or {},
        heading="身份内核快照",
    )


def render_nine_questions_snapshot(nine_questions: Any) -> str:
    return render_human_readable_block(nine_questions or {}, heading="Q1-Q8 认知快照")


def render_task_state(task_state: Any) -> str:
    return render_human_readable_block(task_state or [], heading="当前任务状态")


def record_model_invoked(
    store: BrainTranscriptStore,
    *,
    session_id: str,
    turn_id: str,
    trace_id: str,
    source: str,
    payload: Dict[str, Any],
):
    store.write_entry(
        session_id=session_id,
        turn_id=turn_id,
        entry_type=BrainTranscriptEntryType.MODEL_PROVIDER_INVOKED,
        timestamp=datetime.now(timezone.utc),
        source=source,
        trace_id=trace_id,
        payload=payload,
    )


def record_model_completed(
    store: BrainTranscriptStore,
    *,
    session_id: str,
    turn_id: str,
    trace_id: str,
    source: str,
    payload: Dict[str, Any],
):
    store.write_entry(
        session_id=session_id,
        turn_id=turn_id,
        entry_type=BrainTranscriptEntryType.MODEL_PROVIDER_COMPLETED,
        timestamp=datetime.now(timezone.utc),
        source=source,
        trace_id=trace_id,
        payload=payload,
    )


def record_model_failed(
    store: BrainTranscriptStore,
    *,
    session_id: str,
    turn_id: str,
    trace_id: str,
    source: str,
    payload: Dict[str, Any],
):
    store.write_entry(
        session_id=session_id,
        turn_id=turn_id,
        entry_type=BrainTranscriptEntryType.MODEL_PROVIDER_FAILED,
        timestamp=datetime.now(timezone.utc),
        source=source,
        trace_id=trace_id,
        payload=payload,
    )
