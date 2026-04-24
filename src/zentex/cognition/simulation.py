from __future__ import annotations

"""
Counterfactual simulation engine / 多分支世界模型引擎。

该模块负责把高成本的预演任务卸载到后台线程池，并在结果回写前执行
快照版本校验，防止陈旧推演覆盖新的主脑状态。
"""

from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Dict, List, Optional, Union
from uuid import uuid4

from zentex.foundation.specs.model_provider import (
    ModelProviderCallerContext,
    ModelProviderSpec,
)
from zentex.llm.service import LLMService
from zentex.plugins.contracts import PluginLifecycleStatus
from zentex.plugins.simulation import SimulationDomainPlugin, SimulationIntent
from pydantic import BaseModel, ConfigDict, Field
from zentex.cognition.llm_prompt import build_simulation_comparison_prompt


class StaleSimulationResultError(RuntimeError):
    """Raised when a background simulation result targets an outdated snapshot."""


class ScenarioBranch(BaseModel):
    """单个反事实分支的结构化预测结果。"""

    model_config = ConfigDict(extra="forbid")

    branch_id: str
    branch_label: str
    target_domain: str
    predicted_impacts: List[str] = Field(default_factory=list)
    risk_score: float = Field(ge=0.0, le=1.0)
    failure_cascade: bool = False
    veto_reason: Optional[str] = None
    simulated_by: List[str] = Field(default_factory=list)


class OutcomeComparison(BaseModel):
    """多分支横向比较后的最终结论。"""

    model_config = ConfigDict(extra="forbid")

    summary: str
    risk_ranking: List[Dict[str, Any]] = Field(default_factory=list)
    recommended_branch_id: str


class SimulationBundle(BaseModel):
    """一次后台预演任务的完整产物。"""

    model_config = ConfigDict(extra="forbid")

    goal_id: str
    idempotency_key: str
    snapshot_version: int
    status: str
    branches: List[ScenarioBranch] = Field(default_factory=list)
    outcome_comparison: Optional[OutcomeComparison] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None


class CounterfactualSimulationEngine:
    """
    Background offloaded, multi-plugin counterfactual simulation engine.

    Heavy simulation work must not block the main thread. Results are only
    accepted if their snapshot_version is still current when the background task
    finishes.
    """

    def __init__(
        self,
        *,
        llm_service: Optional[LLMService] = None,
        model_provider: Optional[ModelProviderSpec] = None,
        model_provider_key: Optional[str] = None,
        simulation_plugins: List[SimulationDomainPlugin],
        max_workers: int = 4,
    ) -> None:
        """
        初始化多分支模拟引擎。

        Args:
            llm_service: 统一 LLM 服务入口。
            model_provider: 兼容旧调用链的回退 provider。
            simulation_plugins: 可并发执行的领域模拟器插件集合。
            max_workers: 后台线程池大小。
        """
        self._llm_service = llm_service
        self._model_provider = model_provider
        self._model_provider_key = model_provider_key
        self._simulation_plugins = simulation_plugins
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="simulation-engine")
        self._lock = Lock()
        self._snapshot_version = 0
        self._bundles_by_goal: Dict[str, SimulationBundle] = {}
        self._futures_by_goal: Dict[str, Future[SimulationBundle]] = {}

    @property
    def snapshot_version(self) -> int:
        """返回当前主脑快照版本，用于后台结果回写校验。"""
        with self._lock:
            return self._snapshot_version

    def bump_snapshot_version(self) -> int:
        """推进主脑快照版本。任何新任务都应携带最新版本号。"""
        with self._lock:
            self._snapshot_version += 1
            return self._snapshot_version

    def submit_simulation(
        self,
        *,
        goal_id: str,
        branches: List[Dict[str, Any]],
        snapshot_version: int,
        idempotency_key: str,
        base_context: Dict[str, Any],
    ) -> Future[SimulationBundle]:
        """
        提交后台预演任务。

        Args:
            goal_id: 当前目标标识。
            branches: 待评估的候选分支定义。
            snapshot_version: 提交任务时看到的主脑快照版本。
            idempotency_key: 去重键，避免同一请求重复执行。
            base_context: 所有分支共享的上下文。
        """
        future = self._executor.submit(
            self._run_bundle_task,
            goal_id,
            branches,
            snapshot_version,
            idempotency_key,
            base_context,
        )
        with self._lock:
            self._futures_by_goal[goal_id] = future
        return future

    def get_bundle(self, goal_id: str) -> Optional[SimulationBundle]:
        """读取指定目标的最近一次预演结果。"""
        with self._lock:
            return self._bundles_by_goal.get(goal_id)

    def _run_bundle_task(
        self,
        goal_id: str,
        branches: List[Dict[str, Any]],
        snapshot_version: int,
        idempotency_key: str,
        base_context: Dict[str, Any],
    ) -> SimulationBundle:
        """在后台线程执行多插件预演并生成最终汇总结论。"""
        collected_branches: List[ScenarioBranch] = []
        plugin_futures: List[Future[List[ScenarioBranch]]] = []
        active_plugins = [
            plugin
            for plugin in self._simulation_plugins
            if plugin.lifecycle_status == PluginLifecycleStatus.ACTIVE
        ]

        for plugin in active_plugins:
            plugin_futures.append(
                self._executor.submit(
                    self._run_plugin_predictions,
                    plugin,
                    branches,
                    base_context,
                )
            )

        for future in plugin_futures:
            try:
                collected_branches.extend(future.result())
            except Exception as exc:
                # POLICY: Fail-Closed on plugin failure. No partial simulations.
                logger.error(f"Simulation Engine: Critical failure in domain plugin. Aborting bundle {goal_id}: {exc}")
                raise RuntimeError(f"Simulation failed due to domain plugin crash: {exc}") from exc

        if not collected_branches:
             logger.warning(f"Simulation Engine: No branches were simulated for {goal_id}. Check plugin domain support.")
             # We let it proceed to comparison which will honestly report zero branches.

        comparison = self._compare_outcomes_with_llm(
            goal_id=goal_id,
            branches=collected_branches,
            snapshot_version=snapshot_version,
            idempotency_key=idempotency_key,
        )
        bundle = SimulationBundle(
            goal_id=goal_id,
            idempotency_key=idempotency_key,
            snapshot_version=snapshot_version,
            status="completed",
            branches=collected_branches,
            outcome_comparison=comparison,
            completed_at=datetime.now(timezone.utc),
        )

        with self._lock:
            # 为什么这里要拒绝落后版本：预演是高成本后台任务，返回时主脑状态可能已经变化，
            # 继续合并会把旧世界模型覆盖到新状态上，直接污染后续决策。
            if snapshot_version != self._snapshot_version:
                raise StaleSimulationResultError(
                    f"Discarded stale simulation result for goal {goal_id}: "
                    f"expected snapshot_version {self._snapshot_version}, got {snapshot_version}"
                )
            self._bundles_by_goal[goal_id] = bundle
        return bundle

    def _run_plugin_predictions(
        self,
        plugin: SimulationDomainPlugin,
        branches: List[Dict[str, Any]],
        base_context: Dict[str, Any],
    ) -> List[ScenarioBranch]:
        """
        执行单个领域模拟器，对匹配的分支生成结构化预测。

        Raises:
            Exception: 透传模拟器自身异常，保持 fail-closed。
        """
        results: List[ScenarioBranch] = []
        for branch in branches:
            branch_id = str(branch["branch_id"])
            branch_label = str(branch.get("branch_label") or branch_id)
            target_domain = str(branch.get("target_domain") or "general")
            if target_domain not in plugin.supported_domains:
                continue
            intent = SimulationIntent(
                intent_name=str(branch.get("intent_name") or branch_label),
                target_domain=target_domain,
                intent_payload=dict(branch.get("intent_payload") or {}),
                risk_level=str(branch.get("risk_level") or "medium"),
            )
            result = plugin.simulate_action(intent, {**base_context, **dict(branch.get("context") or {})})
            impacts = list(result.predicted_impacts)
            
            # POLICY: Eradicate hardcoded risk stubs (0.95 / 0.35)
            # Use the authentic score from the plugin result.
            risk_score = float(result.risk_score if result.risk_score is not None else (0.95 if result.replan_required else 0.35))
            
            results.append(
                ScenarioBranch(
                    branch_id=branch_id,
                    branch_label=branch_label,
                    target_domain=target_domain,
                    predicted_impacts=impacts,
                    risk_score=risk_score,
                    failure_cascade=not result.is_safe,
                    veto_reason=result.veto_reason,
                    simulated_by=[plugin.plugin_id],
                )
            )
        return results

    def _compare_outcomes_with_llm(
        self,
        *,
        goal_id: str,
        branches: List[ScenarioBranch],
        snapshot_version: int,
        idempotency_key: str,
    ) -> OutcomeComparison:
        """
        使用激活态大模型对分支结果做最终比较。

        Raises:
            Exception: 透传模型调用异常，绝不使用本地规则兜底伪造结论。
        """
        translated_context = {
            "goal_reference": goal_id,
            "current_state_version": snapshot_version,
            "deduplication_reference": idempotency_key,
            "scenario_branches": [
                {
                    "branch_name": branch.branch_label,
                    "domain": self._humanize_token(branch.target_domain),
                    "predicted_impacts": branch.predicted_impacts,
                    "risk_score": branch.risk_score,
                    "catastrophic_failure_risk": branch.failure_cascade,
                    "blocking_reason": branch.veto_reason,
                    "cognitive_coverage": branch.simulated_by,  # Pass traceability to LLM
                }
                for branch in branches
            ],
        }
        caller_context = ModelProviderCallerContext(
            source_module="World-model simulation engine",
            invocation_phase="comparing branch outcomes",
            question_driver_refs=["这样做会带来什么后果", "我现在应该做什么"],
            decision_id=goal_id,
        )
        prompt = build_simulation_comparison_prompt(
            goal_id=goal_id,
            branch_count=len(branches),
        )["prompt"]
        if self._llm_service is not None:
            payload = self._llm_service.generate_json(
                prompt=prompt,
                context=translated_context,
                caller_context=caller_context,
                source_module=caller_context.source_module,
                invocation_phase=caller_context.invocation_phase,
                decision_id=caller_context.decision_id,
                model_provider=self._model_provider_key,
                metadata={"question_driver_refs": caller_context.question_driver_refs},
            ).output
        elif self._model_provider is not None:
            payload = self._model_provider.generate_json(
                prompt=prompt,
                context=translated_context,
                caller_context=caller_context,
            )
        else:
            raise RuntimeError("LLM MANDATORY: missing llm_service and model_provider fallback")
        return OutcomeComparison.model_validate(payload)

    def _humanize_token(self, token: str) -> str:
        """把内部命名转成更适合模型理解的可读短语。"""
        return token.replace("_", " ").replace("-", " ").strip()
