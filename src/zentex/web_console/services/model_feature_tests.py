from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from fastapi import HTTPException, Request

from zentex.core.model_provider_spec import ModelProviderCallerContext, ModelProviderSpec
from zentex.core.plugin_base import PluginLifecycleStatus
from zentex.runtime.runtime import BrainRuntime
from zentex.runtime.session import BrainSession
from zentex.tasks.llm_decomposer import LLMTaskDecomposerPlugin
from zentex.web_console.contracts.model_feature_tests import (
    ModelFeatureHistoryItem,
    ModelFeatureInvokeRequest,
    ModelFeatureInvokeResponse,
    ModelFeatureRunLogResponse,
    ModelFeatureStatsResponse,
    ModelFeatureTestCatalogItem,
)
from zentex.web_console.dependencies import get_active_session, get_runtime, get_transcript_store
from zentex.web_console.services.llm import enforce_llm_available


MODEL_FEATURE_TEST_LOG_PATH = Path(".zentex/runtime/model_feature_test_logs.jsonl")


def _estimate_token_count(value: Any) -> int:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    if not text:
        return 0
    return max(1, len(text) // 4)


def _extract_usage_tokens(result: Any) -> Tuple[int, int]:
    if isinstance(result, dict):
        usage = result.get("usage")
        if isinstance(usage, dict):
            prompt_tokens = usage.get("prompt_tokens") or usage.get("input_tokens")
            completion_tokens = usage.get("completion_tokens") or usage.get("output_tokens")
            if isinstance(prompt_tokens, int) and isinstance(completion_tokens, int):
                return (max(0, prompt_tokens), max(0, completion_tokens))
        input_tokens = result.get("input_tokens")
        output_tokens = result.get("output_tokens")
        if isinstance(input_tokens, int) and isinstance(output_tokens, int):
            return (max(0, input_tokens), max(0, output_tokens))
    return (0, 0)


def _append_log(record: Dict[str, Any]) -> None:
    MODEL_FEATURE_TEST_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with MODEL_FEATURE_TEST_LOG_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, default=str))
        handle.write("\n")


def _iter_log() -> List[Dict[str, Any]]:
    if not MODEL_FEATURE_TEST_LOG_PATH.exists():
        return []
    records: List[Dict[str, Any]] = []
    with MODEL_FEATURE_TEST_LOG_PATH.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict):
                records.append(record)
    return records


def list_model_feature_tests() -> List[ModelFeatureTestCatalogItem]:
    return [
        ModelFeatureTestCatalogItem(
            feature_id="model_provider.generate_json",
            display_name="ModelProvider JSON",
            description="Calls the active model provider and expects STRICT JSON output.",
            group="provider",
            supports_simulation=False,
            enabled=True,
        ),
        ModelFeatureTestCatalogItem(
            feature_id="tasks.decompose_mission",
            display_name="Task Decompose",
            description="Runs LLMTaskDecomposerPlugin.decompose_mission() using the active model provider.",
            group="tasks",
            supports_simulation=False,
            enabled=True,
        ),
    ]


def _resolve_active_model_provider(request: Request) -> ModelProviderSpec:
    records = getattr(request.app.state, "managed_plugin_records", None)
    if isinstance(records, dict):
        for record in records.values():
            plugin = getattr(record, "plugin", None)
            if isinstance(plugin, ModelProviderSpec) and plugin.status == PluginLifecycleStatus.ACTIVE:
                return plugin
    raise HTTPException(status_code=503, detail="No active model provider plugin is bound.")


def _ensure_session(request: Request, runtime: BrainRuntime) -> BrainSession:
    session = get_active_session(request)
    if session is not None:
        return session
    session = runtime.create_session("web-console-test")
    request.app.state.session = session
    return session


def invoke_model_feature_test(request: Request, payload: ModelFeatureInvokeRequest) -> ModelFeatureInvokeResponse:
    enforce_llm_available(request)
    runtime = get_runtime(request)
    session = _ensure_session(request, runtime)
    provider = _resolve_active_model_provider(request)
    transcript_store = get_transcript_store(request)

    started_at = datetime.now(timezone.utc)
    test_run_id = uuid4().hex
    trace_id = str(payload.caller_context.get("trace_id") or f"model-feature:{test_run_id}")

    ok = False
    result: Dict[str, Any] = {}
    summary = ""

    try:
        if payload.feature_id == "model_provider.generate_json":
            caller_context = ModelProviderCallerContext(
                source_module=str(payload.caller_context.get("source_module") or "zentex.web_console.tests"),
                invocation_phase=str(payload.caller_context.get("invocation_phase") or "model_feature_test"),
                question_driver_refs=list(payload.caller_context.get("question_driver_refs") or []),
                decision_id=str(payload.caller_context.get("decision_id") or "") or None,
                trace_id=trace_id,
            )
            result = provider.generate_json(
                prompt=payload.prompt,
                context=payload.context,
                caller_context=caller_context,
            )
        elif payload.feature_id == "tasks.decompose_mission":
            mission_title = str(payload.context.get("mission_title") or "Manual Mission")
            mission_content = str(payload.context.get("mission_content") or payload.prompt)
            decomposer = LLMTaskDecomposerPlugin(
                model_provider=provider,
                transcript_store=transcript_store,
            )
            subtasks = decomposer.decompose_mission(mission_title, mission_content)
            result = {"subtasks": subtasks}
        else:
            raise HTTPException(status_code=404, detail=f"Unknown model feature test: {payload.feature_id}")
        ok = True
        summary = "ok"
    except HTTPException:
        raise
    except Exception as exc:
        ok = False
        summary = f"error: {exc}"
        result = {"error": str(exc)}
    finally:
        finished_at = datetime.now(timezone.utc)
        usage_in, usage_out = _extract_usage_tokens(result)
        if usage_in == 0 and usage_out == 0:
            usage_in = _estimate_token_count(payload.prompt)
        record = {
            "test_run_id": test_run_id,
            "feature_id": payload.feature_id,
            "started_at": started_at.astimezone(timezone.utc).isoformat(),
            "finished_at": finished_at.astimezone(timezone.utc).isoformat(),
            "ok": ok,
            "summary": summary,
            "trace_id": trace_id,
            "prompt": payload.prompt,
            "context": payload.context,
            "caller_context": payload.caller_context,
            "input_tokens": usage_in,
            "output_tokens": usage_out,
            "total_tokens": usage_in + usage_out,
            "result": result,
        }
        _append_log(record)
        session.advance_turn(
            {
                "turn_id": f"model-feature-test-{test_run_id}",
                "trace_id": trace_id,
                "timestamp": finished_at,
                "status": "completed" if ok else "failed",
                "model_feature_test": record,
            }
        )

    return ModelFeatureInvokeResponse(ok=ok, test_run_id=test_run_id, result=result)


def get_model_feature_history(feature_id: str, *, limit: int = 20) -> List[ModelFeatureHistoryItem]:
    records = [record for record in _iter_log() if record.get("feature_id") == feature_id]
    records.sort(key=lambda record: str(record.get("started_at") or ""), reverse=True)
    items: List[ModelFeatureHistoryItem] = []
    for record in records[: max(limit, 1)]:
        items.append(
            ModelFeatureHistoryItem(
                test_run_id=str(record.get("test_run_id") or ""),
                feature_id=str(record.get("feature_id") or ""),
                started_at=str(record.get("started_at") or ""),
                finished_at=str(record.get("finished_at") or ""),
                ok=bool(record.get("ok")),
                summary=str(record.get("summary") or ""),
                input_tokens=int(record.get("input_tokens") or 0),
                output_tokens=int(record.get("output_tokens") or 0),
                total_tokens=int(record.get("total_tokens") or 0),
            )
        )
    return items


def collect_model_feature_stats(*, feature_id: Optional[str] = None) -> ModelFeatureStatsResponse:
    records = _iter_log()
    if feature_id is not None:
        records = [record for record in records if record.get("feature_id") == feature_id]

    total_runs = len(records)
    ok_runs = sum(1 for record in records if record.get("ok"))
    failed_runs = total_runs - ok_runs

    input_tokens = [int(record.get("input_tokens") or 0) for record in records]
    output_tokens = [int(record.get("output_tokens") or 0) for record in records]
    total_tokens = [int(record.get("total_tokens") or 0) for record in records]

    def avg(values: List[int]) -> float:
        return (sum(values) / len(values)) if values else 0.0

    last_run_at = max((str(record.get("started_at")) for record in records if record.get("started_at")), default=None)
    last_ok_at = max(
        (str(record.get("started_at")) for record in records if record.get("ok") and record.get("started_at")),
        default=None,
    )
    last_failed_at = max(
        (str(record.get("started_at")) for record in records if not record.get("ok") and record.get("started_at")),
        default=None,
    )

    return ModelFeatureStatsResponse(
        feature_id=feature_id,
        total_runs=total_runs,
        ok_runs=ok_runs,
        failed_runs=failed_runs,
        avg_input_tokens=avg(input_tokens),
        avg_output_tokens=avg(output_tokens),
        avg_total_tokens=avg(total_tokens),
        last_run_at=last_run_at,
        last_ok_at=last_ok_at,
        last_failed_at=last_failed_at,
    )


def get_model_feature_run_log(test_run_id: str) -> Dict[str, Any] | None:
    for record in reversed(_iter_log()):
        if str(record.get("test_run_id") or "") == test_run_id:
            return record
    return None


def get_model_feature_test_run_log(test_run_id: str) -> ModelFeatureRunLogResponse:
    return ModelFeatureRunLogResponse(test_run_id=test_run_id, record=get_model_feature_run_log(test_run_id))

