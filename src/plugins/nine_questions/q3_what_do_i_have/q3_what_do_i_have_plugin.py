from __future__ import annotations

import logging
from time import perf_counter
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from plugins.nine_questions.q3_what_do_i_have.llm_prompt import build_q3_llm_request
from plugins.nine_questions.q3_what_do_i_have.models import Q3WhatDoIHaveInference
from plugins.nine_questions.q3_what_do_i_have.modules import (
    build_q3_runtime_inventory_context,
    build_resource_status_humanized,
    describe_agent,
    describe_tool,
    json_safe_payload,
    safe_provider_plugin_id,
)
from zentex.common.cognitive_result import CognitiveToolResult
from zentex.common.nine_questions_shared import (
    build_nine_question_partial_failure,
    bind_module_runs,
    fail_module_run,
    finish_module_run,
    start_module_run,
    run_audit_integration,
    run_learning_integration,
    run_memory_integration,
    run_reflection_integration,
    build_caller_context,
    build_recovery_action,
    build_recovery_plan,
    persist_question_module_output,
    record_model_completed,
    record_model_failed,
    record_model_invoked,
    require_model_provider,
    require_transcript_store,
)
from zentex.common.plugin_ids import NINE_QUESTION_Q3
from zentex.plugins.models import PluginLifecycleStatus
from zentex.plugins.service import execute_enabled_cognitive_plugin_functionals

logger = logging.getLogger(__name__)

QUESTION_REF = "我有什么"


def _normalize_q3_raw_output(raw: object) -> object:
    if not isinstance(raw, dict):
        return raw
    normalized = dict(raw)
    resource_evaluation = normalized.get("resource_evaluation")
    if isinstance(resource_evaluation, dict):
        normalized_eval = dict(resource_evaluation)
        bottleneck = normalized_eval.get("bottleneck_node")
        if bottleneck is None:
            normalized_eval["bottleneck_node"] = "none"
        else:
            text = str(bottleneck).strip()
            normalized_eval["bottleneck_node"] = text or "none"
        normalized["resource_evaluation"] = normalized_eval
    return normalized


class Q3WhatDoIHavePlugin(BaseModel):
    model_config = ConfigDict(extra="allow")

    plugin_id: str = NINE_QUESTION_Q3
    version: str = "1.0.0"
    feature_code: str = "nine_questions.q3"
    display_name: str = "Q3: What do I have?"
    behavior_key: str = "nine_questions"
    lifecycle_status: str = PluginLifecycleStatus.ACTIVE.value
    health_status: str = "healthy"
    operational_status: str = "enabled"
    """
    Q3: 我有什么 (unified asset inventory + resource evaluation)

    Red lines:
    - Must use Live LLM (fail-closed).
    - Must not scan full repo or read raw bodies; only lightweight metadata.
    - Must write prompt/context/response into BrainTranscriptStore with trace_id.
    """

    def run_tool(self, context: dict[str, Any]) -> CognitiveToolResult:
        provider = require_model_provider(context)
        transcript_store = require_transcript_store(context)
        runtime_inventory_context = build_q3_runtime_inventory_context(context)
        runtime_inventory = runtime_inventory_context["runtime_inventory"]
        cog_tools = runtime_inventory["cog_tools"]
        exec_domains = runtime_inventory["exec_domains"]
        connected_agents = runtime_inventory["connected_agents"]
        cognitive_tool_registry = runtime_inventory["cognitive_tool_registry"]
        execution_domain_registry = runtime_inventory["execution_domain_registry"]
        connected_agent_catalog = runtime_inventory["connected_agent_catalog"]
        accessible_workspace_zones = runtime_inventory["accessible_workspace_zones"]
        tenant_permissions = runtime_inventory["tenant_permissions"]
        execution_tokens = runtime_inventory["execution_tokens"]
        runtime_workspace_assets = runtime_inventory["runtime_workspace_assets"]
        runtime_permissions = runtime_inventory["runtime_permissions"]
        experience_logs = runtime_inventory["experience_logs"]
        activated_strategy_patches = runtime_inventory["activated_strategy_patches"]
        runtime_cli_rows = runtime_inventory["runtime_cli_rows"]
        runtime_mcp_rows = runtime_inventory["runtime_mcp_rows"]
        runtime_cli_payloads = runtime_inventory["runtime_cli_payloads"]
        runtime_mcp_payloads = runtime_inventory["runtime_mcp_payloads"]
        q3_module_results = runtime_inventory_context["module_results"]
        q3_module_runs = runtime_inventory_context["module_runs"]
        q3_persistent_module_runs = bind_module_runs(context, "q3", initial=q3_module_runs)
        plugin_service = context.get("plugin_service")
        functional_assets: list[dict[str, Any]] = []
        if plugin_service is not None:
            try:
                functional_assets = execute_enabled_cognitive_plugin_functionals(
                    plugin_service,
                    self.plugin_id,
                    default_parameters=dict(context),
                    trace_id=str(context.get("trace_id") or "q3"),
                    originator_id=str(context.get("session_id") or "unknown-session"),
                    caller_plugin_id=self.plugin_id,
                )
            except Exception as exc:
                # 严禁吞掉 Q3 functional asset 链异常后继续假装“当前只是没有资产数据”。
                # 这属于功能假实现：后台已经失败，却把页面伪装成正常无数据，严重破坏系统正常运行。
                logger.exception("Q3 functional asset chain failed")
                return build_nine_question_partial_failure(
                    context=context,
                    tool_id=self.plugin_id,
                    question_id="q3",
                    question_ref=QUESTION_REF,
                    error_code="q3_functional_asset_chain_failed",
                    error_message=str(exc),
                    diagnosis_key="q3_execution_diagnosis",
                    module_runs=q3_module_runs or [
                        {
                            "module_id": "q3_execution_tools_inventory",
                            "status": "failed",
                            "error_code": "q3_functional_asset_chain_failed",
                            "error_message": str(exc),
                        }
                    ],
                    plugin_runs=[],
                    upstream_dependencies=[],
                    context_updates={"q3_runtime_inventory": runtime_inventory},
                    required_modules=["q3_execution_tools_inventory"],
                )
            for item in functional_assets:
                if item.get("status") != "done":
                    continue
                plugin_id = str(item.get("plugin_id") or "")
                result = item.get("result")
                execution_domain_registry.append(
                    describe_tool(plugin_id, registry_rows=execution_domain_registry)
                )
                if isinstance(result, dict):
                    connected_agent_catalog.extend(
                        describe_agent(agent)
                        for agent in (result.get("connected_agents") or [])
                        if isinstance(agent, dict)
                    )
        execution_domain_registry = list({row["id"]: row for row in execution_domain_registry if row.get("id")}.values())
        connected_agent_catalog = list({row["id"]: row for row in connected_agent_catalog if row.get("id")}.values())
        exec_domains = list({item: True for item in exec_domains if item}.keys())
        connected_agents = list(
            {
                str(item.get("agent_id") or item.get("id") or item.get("name")).strip(): item
                for item in connected_agents
                if isinstance(item, dict)
                and str(item.get("agent_id") or item.get("id") or item.get("name")).strip()
            }.values()
        )

        llm_request = build_q3_llm_request(
            cognitive_tool_registry=cognitive_tool_registry,
            execution_domain_registry=execution_domain_registry,
            connected_agent_catalog=connected_agent_catalog,
            cog_tools=cog_tools,
            exec_domains=exec_domains,
            connected_agents=connected_agents,
            activated_strategy_patches=activated_strategy_patches,
            accessible_workspace_zones=accessible_workspace_zones,
            workspace_assets=runtime_workspace_assets,
            permissions=runtime_permissions,
            tenant_permissions=tenant_permissions,
            execution_tokens=execution_tokens,
            experience_logs=experience_logs,
            functional_assets=functional_assets,
            cli_tool_registry=runtime_cli_rows,
            mcp_server_registry=runtime_mcp_rows,
        )
        system_prompt = llm_request["system_prompt"]
        prompt = llm_request["prompt"]
        model_context = llm_request["model_context"]

        trace_id = str(context.get("trace_id") or f"q3-what-do-i-have:{uuid4().hex}")
        session_id = str(context.get("session_id") or "unknown-session")
        turn_id = str(context.get("turn_id") or "unknown-turn")
        request_id = str(uuid4())
        decision_id = str(context.get("decision_id") or f"{turn_id}:q3_what_do_i_have")
        resource_reasoning_run = start_module_run(
            q3_persistent_module_runs,
            "q3_resource_sufficiency_inference",
            source="plugins.nine_questions.q3",
        )

        caller_context = build_caller_context(
            source_module="q3_what_do_i_have_plugin",
            invocation_phase="nine_question_q3_what_do_i_have",
            question_ref=QUESTION_REF,
            question_driver_refs=context.get("question_driver_refs"),
            decision_id=decision_id,
            trace_id=trace_id,
        )

        record_model_invoked(
            transcript_store,
            session_id=session_id,
            turn_id=turn_id,
            trace_id=trace_id,
            source="plugins.nine_questions.q3_what_do_i_have",
            payload={
                "request_id": request_id,
                "decision_id": decision_id,
                "question_ref": QUESTION_REF,
                "provider_plugin_id": safe_provider_plugin_id(provider),
                "caller_context": caller_context.model_dump(mode="json"),
                "prompt": prompt,
                "system_prompt": system_prompt,
                "context": model_context,
            },
        )

        try:
            started = perf_counter()
            raw = provider.generate_json(
                prompt=f"{system_prompt}\n\n{prompt}",
                context=model_context,
                caller_context=caller_context,
            )
            elapsed_ms = int((perf_counter() - started) * 1000)
        except Exception as exc:
            # 严禁吞掉 Q3 LLM 调用异常并只返回 partial_failed。
            # 这里必须留下异常堆栈，否则后台资产推理故障会被伪装成普通无数据。
            logger.exception("Q3 LLM invocation failed")
            record_model_failed(
                transcript_store,
                session_id=session_id,
                turn_id=turn_id,
                trace_id=trace_id,
                source="plugins.nine_questions.q3_what_do_i_have",
                payload={
                    "request_id": request_id,
                    "decision_id": decision_id,
                    "question_ref": QUESTION_REF,
                    "caller_context": caller_context.model_dump(mode="json"),
                    "error_type": exc.__class__.__name__,
                    "error_message": str(exc),
                },
            )
            fail_module_run(
                resource_reasoning_run,
                error_code="q3_llm_invocation_failed",
                error_message=str(exc),
            )
            return build_nine_question_partial_failure(
                context=context,
                tool_id=self.plugin_id,
                question_id="q3",
                question_ref=QUESTION_REF,
                error_code="q3_llm_invocation_failed",
                error_message=str(exc),
                diagnosis_key="q3_execution_diagnosis",
                module_runs=list(q3_persistent_module_runs)
                or [{"module_id": "q3_resource_sufficiency_inference", "status": "failed", "error_code": "q3_llm_invocation_failed", "error_message": str(exc)}],
                plugin_runs=[],
                upstream_dependencies=[],
                context_updates={
                    "q3_runtime_inventory": runtime_inventory,
                    "q3_functional_assets": functional_assets,
                },
                required_modules=["q3_resource_sufficiency_inference"],
            )

        try:
            inference = Q3WhatDoIHaveInference.model_validate(_normalize_q3_raw_output(raw))
        except Exception as exc:
            # 严禁吞掉 Q3 输出校验异常并伪装成普通验证失败。
            # 输出结构失真必须留下异常日志，不能让后台问题无声消失。
            logger.exception("Q3 output validation failed")
            record_model_failed(
                transcript_store,
                session_id=session_id,
                turn_id=turn_id,
                trace_id=trace_id,
                source="plugins.nine_questions.q3_what_do_i_have",
                payload={
                    "request_id": request_id,
                    "decision_id": decision_id,
                    "question_ref": QUESTION_REF,
                    "caller_context": caller_context.model_dump(mode="json"),
                    "error_type": exc.__class__.__name__,
                    "error_message": str(exc),
                },
            )
            fail_module_run(
                resource_reasoning_run,
                error_code="q3_output_validation_failed",
                error_message=str(exc),
            )
            return build_nine_question_partial_failure(
                context=context,
                tool_id=self.plugin_id,
                question_id="q3",
                question_ref=QUESTION_REF,
                error_code="q3_output_validation_failed",
                error_message=str(exc),
                diagnosis_key="q3_execution_diagnosis",
                module_runs=list(q3_persistent_module_runs)
                or [{"module_id": "q3_resource_sufficiency_inference", "status": "failed", "error_code": "q3_output_validation_failed", "error_message": str(exc)}],
                plugin_runs=[],
                upstream_dependencies=[],
                context_updates={
                    "q3_runtime_inventory": runtime_inventory,
                    "q3_functional_assets": functional_assets,
                },
                required_modules=["q3_resource_sufficiency_inference"],
            )

        record_model_completed(
            transcript_store,
            session_id=session_id,
            turn_id=turn_id,
            trace_id=trace_id,
            source="plugins.nine_questions.q3_what_do_i_have",
            payload={
                "request_id": request_id,
                "decision_id": decision_id,
                "question_ref": QUESTION_REF,
                "caller_context": caller_context.model_dump(mode="json"),
                "result": inference.model_dump(mode="json"),
                "raw_response": json_safe_payload(getattr(provider, "last_raw_response", None)),
                "token_usage": json_safe_payload(getattr(provider, "last_token_usage", None)),
                "model": json_safe_payload(getattr(provider, "last_model_name", None)),
                "elapsed_ms": elapsed_ms,
            },
        )

        summary = (
            f"resource_status={inference.resource_evaluation.resource_status.value}; "
            f"bottleneck={inference.resource_evaluation.bottleneck_node}"
        )
        finish_module_run(resource_reasoning_run)

        inventory_validation_run = start_module_run(
            q3_persistent_module_runs,
            "q3_service_inventory_validation",
            source="plugins.nine_questions.q3",
        )
        finish_module_run(
            inventory_validation_run,
            status="degraded" if not cog_tools or not exec_domains else "completed",
            error_code="" if cog_tools and exec_domains else "inventory_source_missing",
            error_message="" if cog_tools and exec_domains else "One or more core inventory sources are missing.",
        )

        inventory_summary_run = start_module_run(
            q3_persistent_module_runs,
            "q3_inventory_source_summary",
            source="plugins.nine_questions.q3",
        )
        finish_module_run(inventory_summary_run)

        resource_gate_run = start_module_run(
            q3_persistent_module_runs,
            "q3_resource_reasoning_gate",
            source="plugins.nine_questions.q3",
        )
        finish_module_run(
            resource_gate_run,
            status="degraded" if inference.resource_evaluation.resource_status.value == "sufficient" and (not cog_tools or not exec_domains) else "completed",
            error_code="" if not (inference.resource_evaluation.resource_status.value == "sufficient" and (not cog_tools or not exec_domains)) else "resource_status_overclaimed",
            error_message="" if not (inference.resource_evaluation.resource_status.value == "sufficient" and (not cog_tools or not exec_domains)) else "Resource status may be overstated while core sources are missing.",
        )
        q3_execution_diagnosis = {
            "authenticity_status": "degraded" if not cog_tools or not exec_domains else "completed",
            "diagnosis_code": "inventory_sources_degraded" if not cog_tools or not exec_domains else "completed",
            "diagnosis_message": (
                "Q3 inventory completed with degraded runtime sources."
                if not cog_tools or not exec_domains
                else "Q3 inventory completed with validated runtime sources."
            ),
            "used_fallback": not cog_tools or not exec_domains or plugin_service is None,
            "upstream_degraded": False,
            "module_runs": list(q3_persistent_module_runs),
            "plugin_runs": [],
            "upstream_dependencies": [],
            "recovery_plan": build_recovery_plan(
                question_id="q3",
                retriable=True,
                rollback_available=True,
                partial_retry_available=True,
                partial_replace_available=False,
                actions=[
                    build_recovery_action(
                        "q3-rerun-question",
                        label="重跑 Q3 及下游",
                        kind="retry",
                        executable=True,
                        scope="question_downstream",
                        target="q3",
                        reason="重新执行资源盘点与工具审计。",
                        path="/api/web/nine-questions/q3/run",
                    ),
                    build_recovery_action(
                        "q3-refresh-runtime-inventory",
                        label="刷新 Q3 运行态盘点模块",
                        kind="partial_retry",
                        executable=True,
                        scope="module",
                        target="q3_runtime_inventory",
                        reason="仅刷新 Q3 runtime inventory 相关模块，不重跑 LLM 推理。",
                        path="/api/web/nine-questions/q3/modules/q3_runtime_inventory/retry",
                    ),
                    build_recovery_action(
                        "q3-rollback-previous-success",
                        label="回滚 Q3 到上一份成功快照",
                        kind="rollback",
                        executable=True,
                        scope="question",
                        target="q3",
                        reason="当前 Q3 部分失败时，恢复上一份成功结果。",
                        path="/api/web/nine-questions/q3/rollback",
                    ),
                    build_recovery_action(
                        "q3-rerun-upstream-q1-q2",
                        label="先重跑 Q1/Q2 再重跑 Q3",
                        kind="partial_retry",
                        executable=True,
                        scope="upstream_chain",
                        target="q1,q2->q3",
                        reason="Q3 依赖上游环境和身份态势，先修复上游再重跑盘点。",
                        path="/api/web/nine-questions/q1/run",
                    ),
                ],
            ),
        }
        persist_question_module_output(
            context,
            question_id="q3",
            module_id="resource_sufficiency_inference",
            payload=inference.resource_evaluation.model_dump(mode="json"),
            status=str(resource_reasoning_run.get("status") or "completed"),
            output_kind="inference",
        )
        q3_module_runs = q3_execution_diagnosis.get("module_runs")
        q3_module_runs = q3_module_runs if isinstance(q3_module_runs, list) else []
        run_audit_integration(
            context,
            question_id="q3",
            module_runs=q3_module_runs,
            summary="Q3 资产盘点审计已记录。",
            payload={
                "q3_unified_asset_inventory": inference.unified_asset_inventory.model_dump(mode="json"),
                "q3_resource_evaluation": inference.resource_evaluation.model_dump(mode="json"),
                "q3_humanized_asset_inventory": {
                    "cognitive_tool_rows": cognitive_tool_registry,
                    "execution_tool_rows": execution_domain_registry,
                    "connected_agent_rows": connected_agent_catalog,
                },
            },
        )
        run_memory_integration(
            context,
            question_id="q3",
            module_runs=q3_module_runs,
            title="Q3 Asset Inventory",
            summary="Q3 资产盘点与资源可用性已写入记忆。",
            layer="episodic",
            payload={
                "q3_unified_asset_inventory": inference.unified_asset_inventory.model_dump(mode="json"),
                "q3_resource_evaluation": inference.resource_evaluation.model_dump(mode="json"),
            },
            tags=["nine-questions", "q3", "asset-inventory"],
        )
        run_reflection_integration(
            context,
            question_id="q3",
            module_runs=q3_module_runs,
            subject="Q3 resource evaluation",
            summary="Q3 盘点缺口与资源不足反思已记录。",
            reflection_type="process_reflection",
            payload={
                "q3_resource_evaluation": inference.resource_evaluation.model_dump(mode="json"),
                "q3_humanized_asset_inventory": {
                    "functional_assets": functional_assets,
                    "workspaces": accessible_workspace_zones,
                },
            },
        )
        run_learning_integration(
            context,
            question_id="q3",
            module_runs=q3_module_runs,
            learning_kind="resource_inventory",
            summary="Q3 资产识别与盘点学习记录已登记。",
            payload={
                "q3_unified_asset_inventory": inference.unified_asset_inventory.model_dump(mode="json"),
                "q3_resource_evaluation": inference.resource_evaluation.model_dump(mode="json"),
            },
        )
        q3_execution_diagnosis["module_runs"] = q3_module_runs
        if isinstance(q3_module_results, dict):
            for run in q3_module_runs:
                module_id = str(run.get("module_id") or "")
                if module_id.endswith("_integration"):
                    q3_module_results[module_id] = run

        return CognitiveToolResult(
            tool_id=self.plugin_id,
            summary=summary,
            proposals=[
                {
                    "kind": "unified_asset_inventory",
                    **inference.unified_asset_inventory.model_dump(mode="json"),
                },
                {
                    "kind": "resource_evaluation",
                    **inference.resource_evaluation.model_dump(mode="json"),
                },
            ],
            risks=[
                {
                    "kind": "missing_critical_assets",
                    "items": inference.resource_evaluation.missing_critical_assets,
                }
            ],
            context_updates={
                "nine_questions": {QUESTION_REF: inference.resource_evaluation.resource_status.value},
                "q3_module_results": q3_module_results,
                "q3_unified_asset_inventory": inference.unified_asset_inventory.model_dump(mode="json"),
                "q3_resource_evaluation": inference.resource_evaluation.model_dump(mode="json"),
                "q3_humanized_asset_inventory": {
                    "cognitive_tool_rows": cognitive_tool_registry,
                    "execution_tool_rows": execution_domain_registry,
                    "connected_agent_rows": connected_agent_catalog,
                    "mcp_servers": runtime_mcp_payloads,
                    "cli_tools": runtime_cli_payloads,
                    "cli_tool_rows": runtime_cli_rows,
                    "mcp_server_rows": runtime_mcp_rows,
                    "functional_assets": functional_assets,
                },
                "workspaces_and_permissions": {
                    "available_workspaces": accessible_workspace_zones,
                    "tenant_permissions": tenant_permissions,
                    "execution_tokens": execution_tokens,
                },
                "memory_and_strategy": {
                    "experience_logs": experience_logs,
                    "strategy_patches": activated_strategy_patches,
                },
                "workspace_assets": runtime_workspace_assets,
                "permissions": runtime_permissions,
                "loaded_memories": {
                    "experience_logs": experience_logs,
                    "activated_strategy_patches": activated_strategy_patches,
                },
                "q3_resource_status_humanized": build_resource_status_humanized(
                    inference.resource_evaluation.resource_status.value
                ),
                "q3_execution_diagnosis": q3_execution_diagnosis,
            },
            confidence=0.7,
        )


def build_q3_what_do_i_have_plugin(
    *,
    plugin_id: str = NINE_QUESTION_Q3,
    version: str = "1.0.0",
    lifecycle_status: str | PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE,
) -> Q3WhatDoIHavePlugin:
    return Q3WhatDoIHavePlugin(
        plugin_id=plugin_id,
        version=version,
        feature_code="nine_questions.q3",
        lifecycle_status=getattr(lifecycle_status, "value", lifecycle_status),
        behavior_key="nine_questions",
    )
