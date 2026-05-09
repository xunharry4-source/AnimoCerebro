from __future__ import annotations

"""Decision and memory-context helpers for upgrade planning."""

from typing import Any, Optional

from zentex.upgrade.models import (
    LLMUpgradeIntentRequest,
    PluginEvolutionIntentRequest,
    UpgradeMemoryContext,
)
from zentex.upgrade.plugin.models import PluginEvolutionAction


class UpgradeMemoryContextResolver:
    """Builds reusable memory context for upgrade planning."""

    def __init__(self, memory_service: Optional[Any] = None) -> None:
        self._memory_service = memory_service

    def for_llm_request(
        self,
        request: LLMUpgradeIntentRequest,
    ) -> Optional[UpgradeMemoryContext]:
        return self._recall_memory_context(
            query_parts=[
                request.reason,
                *request.change_signals,
                request.upgrade_request.program_id,
                request.upgrade_request.target_component,
                request.upgrade_request.target_metric,
                request.upgrade_request.objective_summary,
            ],
            target_id=request.upgrade_request.program_id,
            trace_id=request.trace_id,
        )

    def for_plugin_request(
        self,
        request: PluginEvolutionIntentRequest,
    ) -> Optional[UpgradeMemoryContext]:
        if request.upgrade_request is not None:
            return self._recall_memory_context(
                query_parts=[
                    request.reason,
                    *request.change_signals,
                    request.upgrade_request.plugin_id,
                    request.upgrade_request.goal,
                ],
                target_id=request.upgrade_request.plugin_id,
                trace_id=request.trace_id,
            )
        if request.creation_request is not None:
            return self._recall_memory_context(
                query_parts=[
                    request.reason,
                    *request.change_signals,
                    request.creation_request.plugin_id,
                    request.creation_request.goal,
                    *request.creation_request.requested_capabilities,
                ],
                target_id=request.creation_request.plugin_id,
                trace_id=request.trace_id,
            )
        return None

    def _recall_memory_context(
        self,
        *,
        query_parts: list[str],
        target_id: Optional[str],
        trace_id: Optional[str],
    ) -> Optional[UpgradeMemoryContext]:
        if self._memory_service is None:
            return None
        query = " ".join(part.strip() for part in query_parts if part and part.strip())
        query_variants = [
            variant
            for variant in [
                target_id,
                " ".join(part.strip() for part in query_parts[:3] if part and part.strip()),
                query,
            ]
            if variant and variant.strip()
        ]
        if not query_variants:
            return None

        hits = []
        selected_query = query_variants[0]
        for variant in query_variants:
            hits = self._memory_service.recall(
                query=variant,
                limit=8,
                trace_id=trace_id,
                target_id=target_id,
            )
            selected_query = variant
            if hits:
                break
        if not hits:
            return UpgradeMemoryContext(
                query=query,
                summary="No managed memory matched the current upgrade objective.",
            )

        success_patterns: list[str] = []
        failure_patterns: list[str] = []
        suspect_patterns: list[str] = []
        recalled_ids: list[str] = []
        for hit in hits:
            recalled_ids.append(hit.memory_id)
            managed = self._memory_service.get_record(hit.memory_id)
            lowered_tags = {tag.lower() for tag in hit.tags}
            summary = hit.summary.strip()
            if managed is not None:
                status = managed.status.lower()
                trust = managed.trust_level.lower()
                if status in {"rejected", "archived"} or trust in {"suspect", "rejected"}:
                    suspect_patterns.append(summary)
                    continue
            if (
                "success" in lowered_tags
                or "procedure" in lowered_tags
                or "reusable" in summary.lower()
            ):
                success_patterns.append(summary)
            elif (
                "failed" in summary.lower()
                or "failure" in summary.lower()
                or "error" in summary.lower()
                or any(tag.endswith("error") for tag in lowered_tags)
            ):
                failure_patterns.append(summary)
            else:
                success_patterns.append(summary)

        summary_bits: list[str] = []
        if success_patterns:
            summary_bits.append(f"{len(success_patterns)} reusable success memories")
        if failure_patterns:
            summary_bits.append(f"{len(failure_patterns)} failure patterns")
        if suspect_patterns:
            summary_bits.append(f"{len(suspect_patterns)} suspect memories")
        return UpgradeMemoryContext(
            query=selected_query,
            recalled_memory_ids=recalled_ids,
            success_patterns=success_patterns[:3],
            failure_patterns=failure_patterns[:3],
            suspect_patterns=suspect_patterns[:3],
            summary=(
                "Recalled " + ", ".join(summary_bits) + " before planning."
                if summary_bits
                else "Managed memory recall returned context but no reusable pattern classification was derived."
            ),
        )


def resolve_plugin_evolution_action(
    request: PluginEvolutionIntentRequest,
) -> Optional[PluginEvolutionAction]:
    if request.requested_action is not None:
        return request.requested_action
    if request.creation_request is not None and request.upgrade_request is None:
        return PluginEvolutionAction.CREATE
    if request.upgrade_request is not None:
        return PluginEvolutionAction.UPGRADE
    if any(signal.lower() == "create_plugin" for signal in request.change_signals):
        return PluginEvolutionAction.CREATE
    if request.change_signals:
        return PluginEvolutionAction.UPGRADE
    return None
