from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Protocol, Tuple
from zentex.web_console.contracts.audit import (
    AuditGraphEdge,
    AuditGraphLane,
    AuditGraphNode,
    AuditGraphPayload,
    AuditPagePayload,
    AuditRecordItem,
    TurnAuditItem,
    TurnAuditPagePayload,
    TurnToolSummaryItem,
)
from zentex.web_console.contracts.model_provider import ModelProviderTraceItem
from zentex.web_console.contracts.audit_event import AuditEventPayload


def _format_timestamp(ts: Any) -> str:
    if not ts:
        return ""
    if isinstance(ts, str):
        try:
            ts = datetime.fromisoformat(ts)
        except ValueError:
            return ts
    if hasattr(ts, "astimezone"):
        return ts.astimezone(timezone.utc).isoformat()
    return str(ts)


class _AuditEntryLike(Protocol):
    entry_id: str
    trace_id: str
    session_id: str
    turn_id: str
    entry_type: Any
    timestamp: Any
    source: str
    payload: Any


class _AuditEventSourceLike(Protocol):
    def get_entries_snapshot(self) -> list[_AuditEntryLike]: ...


def _entry_type_value(entry: _AuditEntryLike) -> str:
    entry_type = getattr(entry, "entry_type", None)
    return str(getattr(entry_type, "value", entry_type) or "")


def _resolve_audit_entries(source: Any) -> List[_AuditEntryLike]:
    if hasattr(source, "get_entries_snapshot"):
        return list(source.get_entries_snapshot())
    raise TypeError("Expected event source with get_entries_snapshot access")


def build_model_provider_traces(runtime: Any) -> List[ModelProviderTraceItem]:
    entries = _resolve_audit_entries(runtime)
    entries_by_trace_id: Dict[str, List[_AuditEntryLike]] = {}
    for entry in entries:
        entries_by_trace_id.setdefault(entry.trace_id, []).append(entry)

    traces: Dict[str, ModelProviderTraceItem] = {}
    for entry in entries:
        if _entry_type_value(entry) not in {
            "model_provider_invoked",
            "model_provider_completed",
            "model_provider_failed",
        }:
            continue
        payload: Dict[str, Any] = entry.payload if isinstance(entry.payload, dict) else {}
        request_id = str(payload.get("request_id") or entry.trace_id)
        current = traces.get(
            request_id,
            ModelProviderTraceItem(
                trace_id=entry.trace_id,
                request_id=request_id,
                decision_id=str(payload.get("decision_id") or ""),
                phase_name=str(
                    payload.get("phase_name")
                    or (
                        payload.get("caller_context", {}).get("invocation_phase")
                        if isinstance(payload.get("caller_context"), dict)
                        else ""
                    )
                    or "unknown"
                ),
                session_id=entry.session_id,
                turn_id=entry.turn_id,
                provider_plugin_id=str(payload.get("provider_plugin_id") or "unknown"),
                provider_name=str(payload["provider_name"]) if payload.get("provider_name") is not None else None,
                model=str(payload["model"]) if payload.get("model") is not None else None,
                source_module=str(payload["caller_context"]["source_module"])
                if isinstance(payload.get("caller_context"), dict)
                and payload["caller_context"].get("source_module") is not None
                else None,
                invocation_phase=str(payload["caller_context"]["invocation_phase"])
                if isinstance(payload.get("caller_context"), dict)
                and payload["caller_context"].get("invocation_phase") is not None
                else None,
                question_driver_refs=[
                    str(item)
                    for item in (
                        payload.get("caller_context", {}).get("question_driver_refs", [])
                        if isinstance(payload.get("caller_context"), dict)
                        else []
                    )
                    if item is not None
                ],
                prompt=str(payload.get("prompt") or payload.get("system_prompt") or "") or None,
                context=payload.get("context") if isinstance(payload.get("context"), dict) else {},
                request_driver=payload.get("request_driver") if isinstance(payload.get("request_driver"), dict) else {},
                result=payload.get("result") if isinstance(payload.get("result"), dict) else None,
                related_events=[],
            ),
        )
        invoked_at = current.invoked_at
        completed_at = current.completed_at
        failed_at = current.failed_at
        result_payload = current.result
        error_type = current.error_type
        error_message = current.error_message
        model = current.model
        if _entry_type_value(entry) == "model_provider_invoked":
            invoked_at = _format_timestamp(entry.timestamp)
        elif _entry_type_value(entry) == "model_provider_completed":
            completed_at = _format_timestamp(entry.timestamp)
            result_payload = payload.get("result") if isinstance(payload.get("result"), dict) else None
            model = str(payload["model"]) if payload.get("model") is not None else current.model
        elif _entry_type_value(entry) == "model_provider_failed":
            failed_at = _format_timestamp(entry.timestamp)
            error_type = str(payload.get("error_type") or "") or None
            error_message = str(payload.get("error_message") or "") or None

        traces[request_id] = current.model_copy(
            update={
                "invoked_at": invoked_at,
                "completed_at": completed_at,
                "failed_at": failed_at,
                "result": result_payload,
                "error_type": error_type,
                "error_message": error_message,
                "model": model,
                "related_events": [
                    AuditEventPayload(
                        entry_id=phase_entry.entry_id,
                        session_id=phase_entry.session_id,
                        turn_id=phase_entry.turn_id,
                        entry_type=phase_entry.entry_type.value,
                        timestamp=_format_timestamp(phase_entry.timestamp),
                        source=phase_entry.source,
                        trace_id=phase_entry.trace_id,
                        context_info={},
                        payload=phase_entry.payload if isinstance(phase_entry.payload, dict) else {},
                    )
                    for phase_entry in entries_by_trace_id.get(entry.trace_id, [])
                ],
            }
        )

    result = list(traces.values())
    result.sort(key=lambda item: item.invoked_at or "")
    return result


_AUDIT_CONTEXT_KEYS = frozenset(
    {"audit_id", "flow_type", "source_module", "parent_audit_id", "event", "status"}
)


def summarize_audit_entry(entry: _AuditEntryLike) -> Tuple[str, List[str]]:
    payload = entry.payload if isinstance(entry.payload, dict) else {}
    summary = str(
        payload.get("summary") or payload.get("message") or payload.get("event_type") or _entry_type_value(entry)
    )
    refs = payload.get("question_driver_refs")
    question_driver_refs = [str(item) for item in refs if item is not None] if isinstance(refs, list) else []
    return summary, question_driver_refs


def _extract_audit_context(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Extract FlowAudit metadata from an audit event payload."""
    return {k: v for k, v in payload.items() if k in _AUDIT_CONTEXT_KEYS}


def _resolve_request_id(payload: Dict[str, Any]) -> str:
    return str(payload.get("request_id") or "").strip()


def _resolve_decision_id(payload: Dict[str, Any]) -> str:
    caller_context = payload.get("caller_context")
    caller_context = caller_context if isinstance(caller_context, dict) else {}
    return str(payload.get("decision_id") or caller_context.get("decision_id") or "").strip()


def build_audit_items(
    entries: List[_AuditEntryLike],
    *,
    request_id: Optional[str] = None,
    decision_id: Optional[str] = None,
) -> List[AuditRecordItem]:
    filtered_entries = list(entries)
    if request_id or decision_id:
        filtered_entries = []
        for entry in entries:
            payload = entry.payload if isinstance(entry.payload, dict) else {}
            payload_request_id = _resolve_request_id(payload)
            payload_decision_id = _resolve_decision_id(payload)
            if request_id and payload_request_id != request_id:
                continue
            if decision_id and payload_decision_id != decision_id:
                continue
            filtered_entries.append(entry)

    ordered = list(reversed(filtered_entries))
    items: List[AuditRecordItem] = []
    for entry in ordered:
        payload = entry.payload if isinstance(entry.payload, dict) else {}
        summary, refs = summarize_audit_entry(entry)
        items.append(
            AuditRecordItem(
                entry_id=entry.entry_id,
                trace_id=entry.trace_id,
                session_id=entry.session_id,
                turn_id=entry.turn_id,
                entry_type=_entry_type_value(entry),
                timestamp=_format_timestamp(entry.timestamp),
                source=entry.source,
                summary=summary,
                question_driver_refs=refs,
                context_info=_extract_audit_context(payload),
            )
        )
    return items


def build_audit_page(
    entries: List[_AuditEntryLike],
    *,
    page: int,
    page_size: int,
    request_id: Optional[str] = None,
    decision_id: Optional[str] = None,
) -> AuditPagePayload:
    page = max(page, 1)
    page_size = max(min(page_size, 200), 1)
    items = build_audit_items(entries, request_id=request_id, decision_id=decision_id)
    total_items = len(items)
    total_pages = max((total_items + page_size - 1) // page_size, 1)
    page = min(page, total_pages)
    start = (page - 1) * page_size
    end = start + page_size

    return AuditPagePayload(
        items=items[start:end],
        page=page,
        page_size=page_size,
        total_items=total_items,
        total_pages=total_pages,
    )


def build_turn_audit_items(entries: List[_AuditEntryLike]) -> List[TurnAuditItem]:
    turns: Dict[Tuple[str, str], TurnAuditItem] = {}
    for entry in entries:
        key = (entry.session_id, entry.turn_id)
        current = turns.get(
            key,
            TurnAuditItem(
                turn_id=entry.turn_id,
                session_id=entry.session_id,
                status="unknown",
                goal_titles=[],
                tool_summaries=[],
            ),
        )
        payload = entry.payload if isinstance(entry.payload, dict) else {}
        if _entry_type_value(entry) == "turn_started":
            current = current.model_copy(
                update={
                    "started_at": _format_timestamp(entry.timestamp),
                    "status": "in_progress",
                    "goal_titles": list(payload.get("goal_titles") or []),
                }
            )
        elif _entry_type_value(entry) == "turn_finished":
            current = current.model_copy(
                update={
                    "completed_at": _format_timestamp(entry.timestamp),
                    "status": str(payload.get("status") or "completed"),
                }
            )
        elif _entry_type_value(entry) in {
            "cognitive_tool_invoked",
            "cognitive_tool_completed",
            "cognitive_tool_failed",
        }:
            tool_id = str(payload.get("tool_id") or payload.get("plugin_id") or "")
            behavior_key = str(payload.get("behavior_key") or payload.get("feature_code") or "")
            summary = str(payload.get("summary") or _entry_type_value(entry))
            invocation_id = str(payload.get("invocation_id") or "") or None
            current.tool_summaries.append(
                TurnToolSummaryItem(
                    tool_id=tool_id,
                    behavior_key=behavior_key,
                    invocation_id=invocation_id,
                    trace_id=entry.trace_id,
                    summary=summary,
                )
            )
        turns[key] = current

    ordered = list(reversed(sorted(turns.values(), key=lambda item: item.started_at or "")))
    return ordered


def build_turn_audit_page(
    entries: List[_AuditEntryLike],
    *,
    page: int,
    page_size: int,
) -> TurnAuditPagePayload:
    page = max(page, 1)
    page_size = max(min(page_size, 200), 1)
    ordered = build_turn_audit_items(entries)
    total_items = len(ordered)
    total_pages = max((total_items + page_size - 1) // page_size, 1)
    page = min(page, total_pages)
    start = (page - 1) * page_size
    end = start + page_size
    return TurnAuditPagePayload(
        items=ordered[start:end],
        page=page,
        page_size=page_size,
        total_items=total_items,
        total_pages=total_pages,
    )


_MODULE_FAMILY_META: dict[str, dict[str, str]] = {
    "nine_questions": {"title": "九问", "href": "/console/nine-questions"},
    "reflection": {"title": "反思", "href": "/console/nine-questions/reflections"},
    "learning": {"title": "学习", "href": "/console/learning"},
    "memory": {"title": "Memory", "href": "/console/memory"},
    "mcp": {"title": "MCP", "href": "/console/mcp"},
    "tasks": {"title": "Tasks", "href": "/console/tasks"},
    "plugins": {"title": "Plugins", "href": "/console/plugins"},
    "agents": {"title": "Agents", "href": "/console/agents"},
    "audit": {"title": "Audit", "href": "/console/audit/model-provider"},
    "replay": {"title": "Replay", "href": "/console/audit/model-provider"},
}

_MODULE_KIND_TITLES: dict[str, str] = {
    "audit": "审计",
    "memory": "记忆",
    "reflection": "反思",
    "learning": "学习",
}


def _detect_module_family(
    source: str,
    question_driver_refs: list[str],
    summary: str = "",
) -> str:
    source_lower = source.lower()
    summary_lower = summary.lower()
    if question_driver_refs or "q1" in source_lower or "nine_question" in source_lower or "q2" in source_lower:
        return "nine_questions"
    if "reflection" in source_lower or "reflection" in summary_lower:
        return "reflection"
    if "learning" in source_lower or "learning" in summary_lower:
        return "learning"
    if "memory" in source_lower or "memory" in summary_lower:
        return "memory"
    if "mcp" in source_lower:
        return "mcp"
    if "task" in source_lower:
        return "tasks"
    if "plugin" in source_lower or "provider" in source_lower:
        return "plugins"
    if "agent" in source_lower:
        return "agents"
    if "replay" in source_lower:
        return "replay"
    return "audit"


def _is_item_relevant_for_mode(mode: str, item: AuditRecordItem) -> bool:
    source_lower = item.source.lower()
    summary_lower = item.summary.lower()
    if mode == "nine_questions":
        return bool(item.question_driver_refs) or "nine_question" in source_lower or source_lower.startswith("q")
    if mode == "reflection":
        return "reflection" in source_lower or "reflection" in summary_lower
    if mode == "learning":
        return "learning" in source_lower or "learning" in summary_lower
    return True


def _event_status_from_type(entry_type: str) -> str:
    entry_type_lower = entry_type.lower()
    if "fail" in entry_type_lower or "error" in entry_type_lower:
        return "failed"
    if "complete" in entry_type_lower or "finished" in entry_type_lower or "done" in entry_type_lower:
        return "completed"
    if "start" in entry_type_lower or "invoke" in entry_type_lower or "running" in entry_type_lower:
        return "running"
    return "active"


def _format_question_title(question_id: Any) -> str:
    normalized = str(question_id or "").strip()
    if not normalized:
        return ""
    if len(normalized) >= 2 and normalized[0].lower() == "q" and normalized[1:].isdigit():
        return f"Q{normalized[1:]}"
    return normalized.upper()


def _format_execution_node_title(item: AuditRecordItem) -> str:
    context_info = item.context_info if isinstance(item.context_info, dict) else {}
    question_title = _format_question_title(context_info.get("question_id"))
    module_id = str(context_info.get("module_id") or "").strip()
    module_kind = str(context_info.get("module_kind") or "").strip().lower()
    module_kind_title = _MODULE_KIND_TITLES.get(module_kind, "")

    if question_title and module_kind_title and module_id:
        return f"{question_title} / {module_kind_title} / {module_id}"
    if question_title and module_id:
        return f"{question_title} / {module_id}"
    if module_kind_title and module_id:
        return f"{module_kind_title} / {module_id}"
    if module_id:
        return module_id
    return item.source


def build_audit_graph(
    *,
    mode: str,
    audit_items: list[AuditRecordItem],
    model_provider_traces: list[ModelProviderTraceItem],
) -> AuditGraphPayload:
    mode_meta = {
        "nine_questions": (
            "基于 9 问开始的审计与溯源",
            "从九问出发，追到 reflection、learning、memory、MCP、tasks、plugins、agents 和 trace。 ",
            "九问起点",
            "/console/nine-questions",
        ),
        "reflection": (
            "基于反思开始的审计与溯源",
            "从 reflection 记录出发，追到触发问题、相关 trace 和下游模块。 ",
            "反思起点",
            "/console/nine-questions/reflections",
        ),
        "learning": (
            "基于学习开始的审计与溯源",
            "从 learning run 出发，追到相关问题、trace 和系统影响模块。 ",
            "学习起点",
            "/console/learning",
        ),
    }
    title, subtitle, start_title, start_href = mode_meta.get(
        mode,
        ("审计与溯源", "从数据库里的审计数据构建模块链路图。", "审计起点", "/console/audit"),
    )

    relevant_items = [item for item in audit_items if _is_item_relevant_for_mode(mode, item)]
    relevant_trace_ids = {item.trace_id for item in relevant_items if item.trace_id}
    relevant_request_ids = {trace.request_id for trace in model_provider_traces if trace.trace_id in relevant_trace_ids}
    relevant_traces = [
        trace
        for trace in model_provider_traces
        if trace.trace_id in relevant_trace_ids or trace.request_id in relevant_request_ids
    ]
    driver_refs = sorted(
        {
            ref
            for item in relevant_items
            for ref in item.question_driver_refs
        }
        | {
            ref
            for trace in relevant_traces
            for ref in trace.question_driver_refs
        }
    )

    family_counts: dict[str, dict[str, Any]] = {
        family: {"events": 0, "traces": 0, "refs": set()}
        for family in _MODULE_FAMILY_META
    }
    for item in relevant_items:
        family = _detect_module_family(item.source, item.question_driver_refs, item.summary)
        family_counts[family]["events"] += 1
        family_counts[family]["refs"].update(item.question_driver_refs)
    for trace in relevant_traces:
        family = _detect_module_family(trace.source_module or trace.provider_plugin_id, trace.question_driver_refs)
        family_counts[family]["traces"] += 1
        family_counts[family]["refs"].update(trace.question_driver_refs)

    start_node = AuditGraphNode(
        node_id=f"{mode}-start",
        title=start_title,
        lane="start",
        status="ready" if relevant_items else "degraded",
        description=f"已落库事件 {len(relevant_items)} 条，相关 trace {len(relevant_traces)} 条。",
        href=start_href,
        metrics={
            "audit_events": len(relevant_items),
            "trace_count": len(relevant_traces),
        },
    )

    driver_nodes: list[AuditGraphNode] = [
        AuditGraphNode(
            node_id=f"driver-{ref}",
            title=ref.upper(),
            lane="drivers",
            status="active",
            description=f"问题驱动引用 {ref}。",
            href=f"/console/nine-questions/{ref}",
            metrics={
                "question_ref": ref,
                "workflow_path": f"/console/nine-questions/{ref}/workflow",
            },
        )
        for ref in driver_refs
    ]
    driver_edges: list[AuditGraphEdge] = [
        AuditGraphEdge(
            edge_id=f"edge-start-driver-{ref}",
            source=start_node.node_id,
            target=f"driver-{ref}",
            label="问题驱动",
        )
        for ref in driver_refs
    ]

    family_nodes: list[AuditGraphNode] = []
    family_edges: list[AuditGraphEdge] = []
    for family, meta in _MODULE_FAMILY_META.items():
        counts = family_counts[family]
        status = "active" if counts["events"] or counts["traces"] else "missing"
        family_node = AuditGraphNode(
            node_id=f"family-{family}",
            title=meta["title"],
            lane="modules",
            status=status,
            description=f"事件 {counts['events']} 条，trace {counts['traces']} 条。",
            href=meta["href"],
            metrics={
                "event_count": counts["events"],
                "trace_count": counts["traces"],
                "question_refs": sorted(counts["refs"]),
            },
        )
        family_nodes.append(family_node)
        family_edges.append(
            AuditGraphEdge(
                edge_id=f"edge-start-{family}",
                source=(f"driver-{sorted(counts['refs'])[0]}" if counts["refs"] else start_node.node_id),
                target=family_node.node_id,
                label="关联模块",
            )
        )

    execution_nodes: list[AuditGraphNode] = []
    execution_edges: list[AuditGraphEdge] = []
    seen_execution_keys: set[tuple[str, str, str]] = set()
    for item in relevant_items[:24]:
        family = _detect_module_family(item.source, item.question_driver_refs, item.summary)
        context_info = item.context_info if isinstance(item.context_info, dict) else {}
        execution_identity = str(context_info.get("module_id") or item.source).strip()
        execution_key = (family, execution_identity, item.entry_type)
        if execution_key in seen_execution_keys:
            continue
        seen_execution_keys.add(execution_key)
        execution_node = AuditGraphNode(
            node_id=f"execution-{family}-{len(execution_nodes)}",
            title=_format_execution_node_title(item),
            lane="execution",
            status=_event_status_from_type(item.entry_type),
            description=f"{item.entry_type} | {item.summary} | source={item.source}",
            href=f"/console/audit/transcript-replay/{item.trace_id}" if item.trace_id else None,
            metrics={
                "entry_id": item.entry_id,
                "trace_id": item.trace_id,
                "question_refs": item.question_driver_refs,
                "timestamp": item.timestamp,
            },
        )
        execution_nodes.append(execution_node)
        execution_edges.append(
            AuditGraphEdge(
                edge_id=f"edge-family-execution-{family}-{len(execution_edges)}",
                source=(
                    f"driver-{item.question_driver_refs[0]}"
                    if item.question_driver_refs
                    else f"family-{family}"
                ),
                target=execution_node.node_id,
                label="驱动执行",
            )
        )
        execution_edges.append(
            AuditGraphEdge(
                edge_id=f"edge-family-execution-link-{family}-{len(execution_edges)}",
                source=f"family-{family}",
                target=execution_node.node_id,
                label="最近事件",
            )
        )

    trace_nodes: list[AuditGraphNode] = []
    trace_edges: list[AuditGraphEdge] = []
    for trace in relevant_traces[:8]:
        trace_status = "failed" if trace.failed_at else "completed" if trace.completed_at else "running"
        trace_node = AuditGraphNode(
            node_id=f"trace-{trace.request_id}",
            title=trace.phase_name or trace.request_id,
            lane="traces",
            status=trace_status,
            description=f"{trace.source_module or trace.provider_plugin_id} / {trace.model or 'unknown-model'}",
            href=f"/console/audit/transcript-replay/{trace.trace_id}",
            metrics={
                "request_id": trace.request_id,
                "decision_id": trace.decision_id,
                "question_refs": trace.question_driver_refs,
            },
        )
        trace_nodes.append(trace_node)
        trace_family = _detect_module_family(
            trace.source_module or trace.provider_plugin_id,
            trace.question_driver_refs,
        )
        trace_edges.append(
            AuditGraphEdge(
                edge_id=f"edge-family-{trace_family}-{trace.request_id}",
                source=next(
                    (
                        node.node_id
                        for node in execution_nodes
                        if node.title == (trace.source_module or trace.provider_plugin_id)
                    ),
                    f"family-{trace_family}",
                ),
                target=trace_node.node_id,
                label="调用 trace",
            )
        )

    failed_traces = sum(1 for trace in relevant_traces if trace.failed_at)
    completed_traces = sum(1 for trace in relevant_traces if trace.completed_at)
    outcome_nodes = [
        AuditGraphNode(
            node_id=f"{mode}-outcome-audit-events",
            title="数据库审计结果",
            lane="outcomes",
            status="completed" if relevant_items else "degraded",
            description="审计中心现在优先读数据库，不再只读内存 snapshot。",
            metrics={
                "persisted_audit_events": len(relevant_items),
                "persisted_model_traces": len(relevant_traces),
            },
        ),
        AuditGraphNode(
            node_id=f"{mode}-outcome-trace-status",
            title="Trace 状态汇总",
            lane="outcomes",
            status="failed" if failed_traces else "completed" if completed_traces else "degraded",
            description=f"完成 {completed_traces} 条，失败 {failed_traces} 条。",
            metrics={
                "completed_traces": completed_traces,
                "failed_traces": failed_traces,
            },
        ),
    ]

    outcome_edges = [
        AuditGraphEdge(
            edge_id=f"edge-traces-{mode}-outcomes",
            source=trace_nodes[0].node_id if trace_nodes else start_node.node_id,
            target=outcome_nodes[0].node_id,
            label="落库结果",
        ),
        AuditGraphEdge(
            edge_id=f"edge-events-{mode}-status",
            source=outcome_nodes[0].node_id,
            target=outcome_nodes[1].node_id,
            label="状态统计",
        ),
    ]

    return AuditGraphPayload(
        mode=mode,
        title=title,
        subtitle=subtitle,
        generated_at=datetime.now(timezone.utc).isoformat(),
        summary={
            "audit_event_count": len(relevant_items),
            "model_trace_count": len(relevant_traces),
            "module_families": {
                family: {
                    "event_count": family_counts[family]["events"],
                    "trace_count": family_counts[family]["traces"],
                }
                for family in _MODULE_FAMILY_META
            },
        },
        lanes=[
            AuditGraphLane(
                lane_id="start",
                title="起点层",
                subtitle="只保留起点，不把所有明细塞在首页。",
                nodes=[start_node],
            ),
            AuditGraphLane(
                lane_id="drivers",
                title="驱动层",
                subtitle="这里显示是谁驱动了后续模块和 trace，不再只看模块结果。",
                nodes=driver_nodes,
            ),
            AuditGraphLane(
                lane_id="modules",
                title="模块层",
                subtitle="这里显示整个审计链已经接入的模块族，不是单一表格。",
                nodes=family_nodes,
            ),
            AuditGraphLane(
                lane_id="execution",
                title="执行层",
                subtitle="各模块族最近的真实审计事件节点，防止只剩汇总数字。",
                nodes=execution_nodes,
            ),
            AuditGraphLane(
                lane_id="traces",
                title="Trace 层",
                subtitle="最近相关 trace 和 transcript 回放入口。",
                nodes=trace_nodes,
            ),
            AuditGraphLane(
                lane_id="outcomes",
                title="结果层",
                subtitle="数据库落库结果和执行状态汇总。",
                nodes=outcome_nodes,
            ),
        ],
        edges=[*driver_edges, *family_edges, *execution_edges, *trace_edges, *outcome_edges],
    )
