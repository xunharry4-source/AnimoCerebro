from __future__ import annotations

import logging
from time import perf_counter
from typing import Any

from pydantic import BaseModel, ConfigDict

from plugins.nine_questions.q2_asset_inventory.external.service import run_q2_external_llm_and_save
from plugins.nine_questions.q2_asset_inventory.internal.service import run_q2_internal_llm_and_save
from zentex.common.cognitive_result import CognitiveToolResult
from zentex.common.nine_questions_shared import (
    bind_module_runs,
    fail_module_run,
    finish_module_run,
    run_audit_integration,
    start_module_run,
)
from zentex.common.plugin_ids import NINE_QUESTION_Q2
from zentex.plugins.models import PluginLifecycleStatus

logger = logging.getLogger(__name__)

QUESTION_REF = "我有什么"


class Q2AssetInventoryPlugin(BaseModel):
    """Q2“我有什么”资产盘点认知插件。

    该插件只负责编排内部资产盘点与外部执行资产盘点两个分支，
    具体 LLM 调用、输入构造、结果持久化分别下沉到 internal/external service。
    """

    model_config = ConfigDict(extra="allow")

    plugin_id: str = NINE_QUESTION_Q2
    version: str = "1.0.0"
    feature_code: str = "nine_questions.q2"
    display_name: str = "Q2: 我有什么"
    behavior_key: str = "nine_questions"
    lifecycle_status: str = PluginLifecycleStatus.ACTIVE.value
    health_status: str = "healthy"
    operational_status: str = "enabled"

    def run_tool(self, context: dict[str, Any]) -> CognitiveToolResult:
        # 从运行上下文中提取链路标识，保证日志、审计和 LLM trace 能按同一 trace 串起来。
        session_id = str(context.get("session_id") or "unknown-session")
        trace_id = str(context.get("trace_id") or "q2:no-trace")
        started = perf_counter()
        module_runs = bind_module_runs(context, "q2")
        logger.info("[Q2] plugin execution start session_id=%s trace_id=%s", session_id, trace_id)

        # plugin_service 是内部认知插件和功能插件盘点的权威入口，Q2 不直接绕过服务层读表。
        plugin_service = context.get("plugin_service")
        logger.info(
            "[Q2] plugin context ready has_plugin_service=%s session_id=%s trace_id=%s",
            plugin_service is not None,
            session_id,
            trace_id,
        )

        # 调用内部 LLM 盘点分支：只处理系统内部认知资产、功能插件、长期记忆和策略补丁。
        # 红线：任何地方都禁止再用参数/开关控制是否执行 LLM；LLM 都必须执行并记录输入输出。
        # 永久禁止：任何地方都不能再用 q2_enable_internal_llm 这类参数控制是否执行 LLM。
        # 旧错误写法保留为注释用于防回归，禁止恢复：
        # context["q2_enable_internal_llm"] = True
        internal_run = start_module_run(
            module_runs,
            "q2_internal_asset_inventory",
            source="plugins.nine_questions.q2_asset_inventory",
        )
        try:
            internal_result = run_q2_internal_llm_and_save(
                context,
                plugin_service=plugin_service,
            )
            finish_module_run(internal_run)
        except Exception as exc:
            fail_module_run(
                internal_run,
                error_code="q2_internal_asset_inventory_failed",
                error_message=str(exc),
            )
            logger.exception("[Q2] internal branch failed session_id=%s trace_id=%s", session_id, trace_id)
            raise
        logger.info("[Q2] internal branch completed session_id=%s trace_id=%s", session_id, trace_id)

        # 外部分支只盘点 CLI、MCP、Agent 和外接服务等可能产生外部副作用的执行资产。
        external_run = start_module_run(
            module_runs,
            "q2_external_asset_inventory",
            source="plugins.nine_questions.q2_asset_inventory",
        )
        try:
            external_result = run_q2_external_llm_and_save(
                context,
                cli_service=context.get("cli_service"),
                mcp_service=context.get("mcp_service"),
                agent_service=context.get("agent_service"),
                external_connector_service=context.get("external_connector_service"),
            )
            finish_module_run(external_run)
        except Exception as exc:
            fail_module_run(
                external_run,
                error_code="q2_external_asset_inventory_failed",
                error_message=str(exc),
            )
            logger.exception("[Q2] external branch failed session_id=%s trace_id=%s", session_id, trace_id)
            raise
        logger.info("[Q2] external branch completed session_id=%s trace_id=%s", session_id, trace_id)

        # q2_asset_inventory 是 Q2 对外的汇总入口；scoped 字段保留内外两条 LLM 输出边界。
        result_payload = {
            "q2_internal_tool_asset_inventory": internal_result,
            "q2_external_tool_asset_inventory": external_result,
        }
        llm_output_payload = {
            **result_payload,
            "q2_asset_inventory": result_payload,
        }
        llm_trace_payload = _build_q2_llm_trace_payload(context, trace_id=trace_id)
        audit_provenance = _build_q2_audit_provenance(
            trace_id=trace_id,
            result_payload=result_payload,
            llm_trace_payload=llm_trace_payload,
        )
        run_audit_integration(
            context,
            question_id="q2",
            module_runs=module_runs,
            summary="Q2 内外资产盘点 LLM 输入、输出、模型调用与结果保存链路已记录。",
            payload=audit_provenance,
        )
        q2_execution_diagnosis = {
            "authenticity_status": "completed",
            "diagnosis_code": "completed",
            "diagnosis_message": "Q2 internal/external asset inventory completed with audit provenance.",
            "module_runs": list(module_runs),
            "upstream_dependencies": [],
            "asset_scopes": ["internal_tools", "external_tools"],
        }
        summary = "Q2 资产盘点完成：内部插件、CLI、MCP、Agent、外接服务已分别查询并保存数量。"
        elapsed = perf_counter() - started
        logger.info("[Q2] plugin execution completed session_id=%s trace_id=%s elapsed=%.3fs", session_id, trace_id, elapsed)
        return CognitiveToolResult(
            tool_id=self.plugin_id,
            summary=summary,
            llm_output=llm_output_payload,
            llm_trace_payload=llm_trace_payload,
            proposals=[
                {"kind": "q2_internal_tool_asset_inventory", **internal_result},
                {"kind": "q2_external_tool_asset_inventory", **external_result},
            ],
            context_updates={
                "nine_questions": {QUESTION_REF: summary},
                "q2_asset_inventory": result_payload,
                "q2_internal_tool_asset_inventory": internal_result,
                "q2_external_tool_asset_inventory": external_result,
                "q2_internal_scoped_asset_inventory": {"InternalAssetInventory": internal_result},
                "q2_external_scoped_asset_inventory": {"ExternalAssetInventory": external_result},
                "q2_audit_provenance": audit_provenance,
                "q2_execution_diagnosis": q2_execution_diagnosis,
                "llm_trace_payload": llm_trace_payload,
            },
            confidence=0.75,
        )


def build_q2_asset_inventory_plugin(
    *,
    plugin_id: str = NINE_QUESTION_Q2,
    version: str = "1.0.0",
    lifecycle_status: str | PluginLifecycleStatus = PluginLifecycleStatus.ACTIVE,
) -> Q2AssetInventoryPlugin:
    # 插件系统通过工厂函数实例化 Q2，调用方可覆盖版本和生命周期状态。
    return Q2AssetInventoryPlugin(
        plugin_id=plugin_id,
        version=version,
        feature_code="nine_questions.q2",
        lifecycle_status=getattr(lifecycle_status, "value", lifecycle_status),
        behavior_key="nine_questions",
    )


def _build_q2_llm_trace_payload(context: dict[str, Any], *, trace_id: str) -> dict[str, Any]:
    # 两个分支会把各自的 LLM trace 暂存在 context 中；这里统一聚合成 Q2 总 trace。
    internal_trace = context.get("_q2_internal_tool_llm_trace_payload")
    internal_trace = internal_trace if isinstance(internal_trace, dict) else {}
    external_trace = context.get("_q2_external_tool_llm_trace_payload")
    external_trace = external_trace if isinstance(external_trace, dict) else {}
    # invocations 保留真实调用明细，便于页面和审计层区分 internal_tools / external_tools。
    invocations = [
        item
        for trace in (internal_trace, external_trace)
        for item in (
            trace.get("invocations")
            if isinstance(trace.get("invocations"), list)
            else [trace]
        )
        if isinstance(item, dict) and item
    ]
    # token_usage 使用两个分支的明细求和，避免上层误把某一个分支当成 Q2 总消耗。
    token_usage = {
        "input_tokens": sum(int((item.get("token_usage") or {}).get("input_tokens") or 0) for item in invocations),
        "output_tokens": sum(int((item.get("token_usage") or {}).get("output_tokens") or 0) for item in invocations),
        "total_tokens": sum(int((item.get("token_usage") or {}).get("total_tokens") or 0) for item in invocations),
    }
    return {
        "trace_id": trace_id,
        "question_id": "q2",
        "asset_scopes": ["internal_tools", "external_tools"],
        "internal_tool_llm_trace_payload": internal_trace,
        "external_tool_llm_trace_payload": external_trace,
        "invocations": invocations,
        "token_usage": token_usage,
        "elapsed_ms": sum(int(item.get("elapsed_ms") or 0) for item in invocations),
    }


def _build_q2_audit_provenance(
    *,
    trace_id: str,
    result_payload: dict[str, Any],
    llm_trace_payload: dict[str, Any],
) -> dict[str, Any]:
    invocations = llm_trace_payload.get("invocations")
    invocations = invocations if isinstance(invocations, list) else []
    return {
        "question_id": "q2",
        "trace_id": trace_id,
        "source_module": "plugins.nine_questions.q2_asset_inventory",
        "asset_scopes": ["internal_tools", "external_tools"],
        "source_of_truth": "nine_question_q2_snapshots.llm_output_json",
        "save_flow": [
            "internal LLM output",
            "external LLM output",
            "audit provenance payload",
            "q2 llm_output table payload",
            "service reads q2 table",
            "frontend displays q2 table output",
        ],
        "llm_invocation_count": len(invocations),
        "llm_invocations": invocations,
        "internal_result": result_payload.get("q2_internal_tool_asset_inventory") or {},
        "external_result": result_payload.get("q2_external_tool_asset_inventory") or {},
        "token_usage": llm_trace_payload.get("token_usage") if isinstance(llm_trace_payload.get("token_usage"), dict) else {},
    }
