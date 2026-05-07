from __future__ import annotations

import json
import logging
from time import perf_counter, sleep
from typing import Any
from uuid import uuid4

from plugins.nine_questions.q2_asset_inventory.internal.llm_prompt import (
    build_deterministic_internal_asset_inventory,
    build_q2_internal_llm_request,
)
from zentex.common.nine_questions_shared import (
    build_caller_context,
    json_safe_payload,
    persist_question_module_output,
    record_model_completed,
    record_model_failed,
    record_model_invoked,
    require_model_provider,
    safe_provider_plugin_id,
)
from zentex.plugins.service import query_all_plugins_by_lifecycle

logger = logging.getLogger(__name__)
MAX_Q2_INTERNAL_LLM_ATTEMPTS = 3
Q2_INTERNAL_LLM_RETRY_DELAY_SECONDS = 3


def run_q2_internal_llm_and_save(
    context: dict[str, Any],
    *,
    plugin_service: Any,
    plugin_service_inventory: dict[str, Any] | None = None,
) -> dict[str, Any]:
    session_id = str(context.get("session_id") or "unknown-session")
    trace_id = str(context.get("trace_id") or f"q2-internal:{uuid4().hex}")
    logger.info("[Q2] internal asset inventory start session_id=%s trace_id=%s", session_id, trace_id)
    started = perf_counter()
    provider = require_model_provider(context)
    memory_and_patches_context = build_q2_internal_memory_and_patches_context(context)
    resolved_plugin_service_inventory = plugin_service_inventory or _query_plugin_service_inventory(plugin_service)
    logger.info(
        "[Q2] internal context ready memory_count=%s strategy_patch_count=%s plugin_inventory_count=%s session_id=%s trace_id=%s",
        _count(memory_and_patches_context.get("long_term_memories")),
        _count(memory_and_patches_context.get("strategy_patches")),
        _count(resolved_plugin_service_inventory.get("plugins")),
        session_id,
        trace_id,
    )
    request = build_q2_internal_llm_request(
        plugin_service=plugin_service,
        memory_and_patches_context=memory_and_patches_context,
        plugin_service_inventory=resolved_plugin_service_inventory,
    )
    internal_count = _persist_internal_plugin_count(context, request)
    logger.info(
        "[Q2] internal asset counts saved internal_plugin_count=%s session_id=%s trace_id=%s",
        internal_count,
        session_id,
        trace_id,
    )
    prompt = f"{request['system_prompt']}\n\n{request['prompt']}"
    caller_context = build_caller_context(
        source_module=__name__,
        invocation_phase="q2_internal_asset_inventory",
        question_ref="q2",
        question_driver_refs=["q2"],
        decision_id=f"q2-internal:{uuid4().hex}",
        trace_id=trace_id,
    )
    raw: Any = None
    result: dict[str, Any] = {}
    invocation_payload: dict[str, Any] = {}
    invocation_traces: list[dict[str, Any]] = []
    last_error: Exception | None = None
    # 红线：任何地方都禁止再用参数/开关控制是否执行 LLM；LLM 都必须执行并记录输入输出。
    # 永久禁止：Q2 内部 LLM 不能被参数、开关、配置或上下文静默禁用。
    # internal 和 external 两个 LLM 分支在每次 Q2 执行时都必须进入调用循环，并打印输入与输出日志。
    # 旧错误写法保留为注释用于防回归，禁止恢复：
    # if not _should_call_internal_llm(context):
    #     result = build_deterministic_internal_asset_inventory(request["model_context"])
    #     raw = {"InternalAssetInventory": result}
    for attempt in range(1, MAX_Q2_INTERNAL_LLM_ATTEMPTS + 1):
        attempt_started = perf_counter()
        attempt_prompt = prompt + _retry_hint(attempt, "InternalAssetInventory")
        llm_input = {"prompt": attempt_prompt}
        invocation_payload = {
            "request_id": f"q2-internal-request:{uuid4().hex}",
            "decision_id": caller_context.decision_id,
            "asset_scope": "internal_tools",
            "attempt": attempt,
            "max_attempts": MAX_Q2_INTERNAL_LLM_ATTEMPTS,
            "provider_plugin_id": safe_provider_plugin_id(provider),
            "caller_context": caller_context.model_dump(mode="json"),
            "llm_input": llm_input,
        }
        context["_q2_internal_tool_llm_input"] = llm_input
        _record_invoked(context, session_id=session_id, trace_id=trace_id, payload=invocation_payload)
        _log_llm_input(
            session_id=session_id,
            trace_id=trace_id,
            attempt=attempt,
            max_attempts=MAX_Q2_INTERNAL_LLM_ATTEMPTS,
            llm_input=llm_input,
        )
        logger.info(
            "[Q2] internal LLM request start attempt=%s/%s session_id=%s trace_id=%s",
            attempt,
            MAX_Q2_INTERNAL_LLM_ATTEMPTS,
            session_id,
            trace_id,
        )
        try:
            raw = provider.generate_json(
                prompt=attempt_prompt,
                context={},
                caller_context=caller_context,
                metadata={
                    "question_id": "q2",
                    "asset_scope": "internal_tools",
                    "max_json_repair_attempts": 0,
                    "output_truncation_forbidden": True,
                },
            )
            result = _root_payload(raw, "InternalAssetInventory")
            if not result:
                raise RuntimeError("q2_internal_empty_asset_inventory")
            logger.info(
                "[Q2] internal LLM request completed attempt=%s/%s session_id=%s trace_id=%s",
                attempt,
                MAX_Q2_INTERNAL_LLM_ATTEMPTS,
                session_id,
                trace_id,
            )
            break
        except Exception as exc:
            last_error = exc
            frontend_error_message = (
                "Q2 内部资产盘点 LLM 执行失败，已重试 "
                f"{MAX_Q2_INTERNAL_LLM_ATTEMPTS} 次；请查看后台日志 trace_id={trace_id}"
            )
            failed_payload = {
                **invocation_payload,
                "error_type": exc.__class__.__name__,
                "error_message": str(exc),
                "frontend_error_message": frontend_error_message,
                "backend_error_detail": f"{exc.__class__.__name__}: {exc}",
                "raw_response": json_safe_payload(
                    getattr(exc, "provider_raw_output", None)
                    or getattr(provider, "last_raw_response", None)
                    or raw
                ),
                "token_usage": json_safe_payload(getattr(provider, "last_token_usage", None)),
                "model": json_safe_payload(getattr(provider, "last_model_name", None)),
                "elapsed_ms": int((perf_counter() - attempt_started) * 1000),
            }
            invocation_traces.append(_trace_invocation(invocation_payload, failed_payload=failed_payload))
            _record_failed(context, session_id=session_id, trace_id=trace_id, payload=failed_payload)
            _log_llm_output(
                session_id=session_id,
                trace_id=trace_id,
                payload=failed_payload,
            )
            if attempt >= MAX_Q2_INTERNAL_LLM_ATTEMPTS:
                logger.error(
                    "[Q2] internal LLM request failed after retries; surfacing error to frontend attempt=%s/%s session_id=%s trace_id=%s error_type=%s error_message=%s",
                    attempt,
                    MAX_Q2_INTERNAL_LLM_ATTEMPTS,
                    session_id,
                    trace_id,
                    exc.__class__.__name__,
                    str(exc),
                    exc_info=True,
                )
                # 红线：最后一次失败也禁止伪造成 deterministic 成功；前端必须看到错误。
                # 旧错误写法保留为注释用于防回归，禁止恢复：
                # result = build_deterministic_internal_asset_inventory(request["model_context"])
                # raw = {"InternalAssetInventory": result}
                # invocation_payload = {
                #     **invocation_payload,
                #     "fallback_source": "service_model_context",
                #     "fallback_reason": exc.__class__.__name__,
                # }
                raise RuntimeError(frontend_error_message) from exc
            # 红线：LLM 错误不能首错直接跳过或兜底；必须等待 3 秒后重试，最多 3 次。
            logger.warning(
                "[Q2] internal LLM request retrying after %ss attempt=%s/%s error_type=%s session_id=%s trace_id=%s",
                Q2_INTERNAL_LLM_RETRY_DELAY_SECONDS,
                attempt,
                MAX_Q2_INTERNAL_LLM_ATTEMPTS,
                exc.__class__.__name__,
                session_id,
                trace_id,
            )
            sleep(Q2_INTERNAL_LLM_RETRY_DELAY_SECONDS)
    if not result and last_error is not None:
        raise RuntimeError(
            f"Q2 内部资产盘点 LLM 未产生有效输出；请查看后台日志 trace_id={trace_id}"
        ) from last_error
    completed_payload = {
        **invocation_payload,
        "result": json_safe_payload(result),
        "raw_response": json_safe_payload(getattr(provider, "last_raw_response", None) or raw),
        "token_usage": json_safe_payload(getattr(provider, "last_token_usage", None)),
        "model": json_safe_payload(getattr(provider, "last_model_name", None)),
        "elapsed_ms": int((perf_counter() - started) * 1000),
    }
    _log_llm_output(
        session_id=session_id,
        trace_id=trace_id,
        payload=completed_payload,
    )
    invocation_traces.append(_trace_invocation(invocation_payload, completed_payload=completed_payload))
    context["_q2_internal_tool_llm_trace_payload"] = _branch_trace_payload(
        trace_id=trace_id,
        asset_scope="internal_tools",
        invocations=invocation_traces,
    )
    _record_completed(context, session_id=session_id, trace_id=trace_id, payload=completed_payload)
    persist_question_module_output(
        context,
        question_id="q2",
        module_id="q2_internal_asset_inventory_output",
        payload=result,
        status="completed",
        output_kind="inference",
    )
    logger.info(
        "[Q2] internal asset inventory output saved session_id=%s trace_id=%s elapsed=%.3fs",
        session_id,
        trace_id,
        perf_counter() - started,
    )
    return result


# 永久禁止恢复这个开关函数。Q2 的内部 LLM 必须无条件执行。
# def _should_call_internal_llm(context: dict[str, Any]) -> bool:
#     return bool(context.get("q2_enable_internal_llm"))
#
#
def _should_use_deterministic_fallback(exc: Exception) -> bool:
    # 旧错误写法保留为注释级红线：禁止在首次 JSON/解析错误时绕过重试直接兜底。
    # Q2 LLM 错误必须先重试，前两次错误每次等待 Q2_INTERNAL_LLM_RETRY_DELAY_SECONDS。
    error_name = exc.__class__.__name__.lower()
    message = str(exc).lower()
    return (
        "parse" in error_name
        or "json" in error_name
        or "non-json" in message
        or "non json" in message
        or "json" in message
    )


def build_q2_internal_memory_and_patches_context(context: dict[str, Any]) -> dict[str, Any]:
    memory_service = context.get("memory_service")
    learning_service = context.get("learning_service")
    memory_rows = _call_context_query(memory_service, "query_q2_memory_context")
    strategy_rows = _call_context_query(learning_service, "query_q2_strategy_patches_context")
    return {
        "long_term_memories": memory_rows,
        "strategy_patches": strategy_rows,
    }


def _query_plugin_service_inventory(plugin_service: Any) -> dict[str, Any]:
    if plugin_service is None:
        return {"plugins": []}
    try:
        rows = query_all_plugins_by_lifecycle(plugin_service, limit=500)
    except Exception:
        logger.exception("[Q2] internal plugin service inventory query failed")
        raise
    return {"plugins": rows if isinstance(rows, list) else []}


def _call_context_query(service: Any, method_name: str) -> list[Any]:
    method = getattr(service, method_name, None)
    if not callable(method):
        return []
    try:
        result = method(limit=50)
    except TypeError:
        result = method()
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        for key in (
            "long_term_memories",
            "reusable_strategy_patches",
            "items",
            "records",
            "memories",
            "strategy_patches",
        ):
            value = result.get(key)
            if isinstance(value, list):
                return value
    return []


def _count(value: Any) -> int:
    return len(value) if isinstance(value, list) else 0


def _persist_internal_plugin_count(context: dict[str, Any], request: dict[str, Any]) -> int:
    model_context = request.get("model_context") if isinstance(request.get("model_context"), dict) else {}
    cognitive_plugins = model_context.get("Internal_Cognitive_Tools")
    functional_plugins = model_context.get("Internal_Functional_Plugins")
    cognitive_count = len(cognitive_plugins) if isinstance(cognitive_plugins, list) else 0
    functional_count = len(functional_plugins) if isinstance(functional_plugins, list) else 0
    internal_count = cognitive_count + functional_count
    persist_question_module_output(
        context,
        question_id="q2",
        module_id="q2_internal_asset_counts",
        payload={
            "internal_plugin_count": internal_count,
            "internal_cognitive_plugin_count": cognitive_count,
            "internal_functional_plugin_count": functional_count,
        },
        status="completed",
        output_kind="evidence",
    )
    return internal_count


def _trace_invocation(
    invocation_payload: dict[str, Any],
    *,
    completed_payload: dict[str, Any] | None = None,
    failed_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    completed_payload = completed_payload or {}
    failed_payload = failed_payload or {}
    caller_context = invocation_payload.get("caller_context")
    caller_context = caller_context if isinstance(caller_context, dict) else {}
    token_usage = completed_payload.get("token_usage")
    token_usage = token_usage if isinstance(token_usage, dict) else {}
    return {
        "request_id": invocation_payload.get("request_id"),
        "decision_id": invocation_payload.get("decision_id"),
        "asset_scope": invocation_payload.get("asset_scope"),
        "attempt": invocation_payload.get("attempt"),
        "max_attempts": invocation_payload.get("max_attempts"),
        "provider_name": invocation_payload.get("provider_plugin_id"),
        "model": completed_payload.get("model") or failed_payload.get("model"),
        "prompt": (invocation_payload.get("llm_input") or {}).get("prompt")
        if isinstance(invocation_payload.get("llm_input"), dict)
        else "",
        "source_module": caller_context.get("source_module"),
        "invocation_phase": caller_context.get("invocation_phase"),
        "question_driver_refs": caller_context.get("question_driver_refs") or [],
        "context_data": {},
        "result": completed_payload.get("result") if isinstance(completed_payload.get("result"), dict) else None,
        "raw_response": completed_payload.get("raw_response") if isinstance(completed_payload.get("raw_response"), dict) else None,
        "token_usage": {
            "input_tokens": int(token_usage.get("input_tokens") or 0),
            "output_tokens": int(token_usage.get("output_tokens") or 0),
            "total_tokens": int(token_usage.get("total_tokens") or 0),
        },
        "elapsed_ms": completed_payload.get("elapsed_ms") or failed_payload.get("elapsed_ms") or 0,
        "error_type": failed_payload.get("error_type"),
        "error_message": failed_payload.get("error_message") or failed_payload.get("error"),
    }


def _branch_trace_payload(
    *,
    trace_id: str,
    asset_scope: str,
    invocations: list[dict[str, Any]],
) -> dict[str, Any]:
    material = [
        item
        for item in invocations
        if any(item.get(key) not in (None, "", [], {}) for key in ("provider_name", "model", "prompt", "raw_response", "error_type"))
    ]
    if not material:
        return {}
    primary = dict(material[-1])
    primary["trace_id"] = trace_id
    primary["asset_scope"] = asset_scope
    primary["invocations"] = material
    primary["token_usage"] = {
        "input_tokens": sum(int((item.get("token_usage") or {}).get("input_tokens") or 0) for item in material),
        "output_tokens": sum(int((item.get("token_usage") or {}).get("output_tokens") or 0) for item in material),
        "total_tokens": sum(int((item.get("token_usage") or {}).get("total_tokens") or 0) for item in material),
    }
    primary["elapsed_ms"] = sum(int(item.get("elapsed_ms") or 0) for item in material)
    return json_safe_payload(primary)


def _retry_hint(attempt: int, root_key: str) -> str:
    if attempt <= 1:
        return ""
    return (
        "\n\n<Q2_RETRY_HINT>\n"
        f"上一次输出没有通过 JSON 解析或结构校验。第 {attempt} 次重试必须只输出一个合法 JSON 对象，"
        f"根节点必须是 `{root_key}`。输出前必须在内部完成 JSON 自检，确认 json.loads 可解析、根节点和必需字段正确。"
        "自检过程禁止输出，禁止输出 Markdown、解释、代码块、前后缀文本。\n"
        "</Q2_RETRY_HINT>"
    )


def _log_llm_input(
    *,
    session_id: str,
    trace_id: str,
    attempt: int,
    max_attempts: int,
    llm_input: dict[str, Any],
) -> None:
    logger.warning(
        "[Q2_LLM_INPUT] scope=internal_tools session_id=%s trace_id=%s payload=%s",
        session_id,
        trace_id,
        json.dumps(
            {
                "scope": "internal_tools",
                "attempt": attempt,
                "max_attempts": max_attempts,
                "llm_input": llm_input,
            },
            ensure_ascii=False,
            default=str,
        ),
    )


def _log_llm_output(
    *,
    session_id: str,
    trace_id: str,
    payload: dict[str, Any],
) -> None:
    logger.warning(
        "[Q2_LLM_OUTPUT] scope=internal_tools session_id=%s trace_id=%s payload=%s",
        session_id,
        trace_id,
        json.dumps(
            {
                "scope": "internal_tools",
                "attempt": payload.get("attempt"),
                "max_attempts": payload.get("max_attempts"),
                "result": payload.get("result"),
                "raw_response": payload.get("raw_response"),
                "token_usage": payload.get("token_usage"),
                "model": payload.get("model"),
                "elapsed_ms": payload.get("elapsed_ms"),
                "error_type": payload.get("error_type"),
                "error_message": payload.get("error_message"),
                "frontend_error_message": payload.get("frontend_error_message"),
                "backend_error_detail": payload.get("backend_error_detail"),
                "fallback_source": payload.get("fallback_source"),
                "fallback_reason": payload.get("fallback_reason"),
            },
            ensure_ascii=False,
            default=str,
        ),
    )


def _record_invoked(context: dict[str, Any], *, session_id: str, trace_id: str, payload: dict[str, Any]) -> None:
    store = context.get("transcript_store") or context.get("audit_store")
    if store and hasattr(store, "write_entry"):
        record_model_invoked(
            store,
            session_id=session_id,
            turn_id=str(context.get("turn_id") or "nine-question-q2"),
            trace_id=trace_id,
            source=__name__,
            payload=payload,
        )


def _record_completed(context: dict[str, Any], *, session_id: str, trace_id: str, payload: dict[str, Any]) -> None:
    store = context.get("transcript_store") or context.get("audit_store")
    if store and hasattr(store, "write_entry"):
        record_model_completed(
            store,
            session_id=session_id,
            turn_id=str(context.get("turn_id") or "nine-question-q2"),
            trace_id=trace_id,
            source=__name__,
            payload=payload,
        )


def _record_failed(context: dict[str, Any], *, session_id: str, trace_id: str, payload: dict[str, Any]) -> None:
    store = context.get("transcript_store") or context.get("audit_store")
    if store and hasattr(store, "write_entry"):
        record_model_failed(
            store,
            session_id=session_id,
            turn_id=str(context.get("turn_id") or "nine-question-q2"),
            trace_id=trace_id,
            source=__name__,
            payload=payload,
        )


def _root_payload(output: Any, root_key: str) -> dict[str, Any]:
    if not isinstance(output, dict):
        return {}
    root = output.get(root_key)
    return root if isinstance(root, dict) else output
