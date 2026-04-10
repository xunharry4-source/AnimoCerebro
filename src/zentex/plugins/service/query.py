"""
Query Service: Plugin Information Retrieval

Handles:
- Query plugins by category/status
- Query cognitive plugin's functional plugins
- Get active inventory
- Get execution statistics
- Advanced filtering queries
"""

from __future__ import annotations

import logging
from uuid import uuid4
from typing import List, Dict, Any, Optional

from zentex.plugins.models import PluginLifecycleStatus

logger = logging.getLogger(__name__)


class QueryService:
    """
    Provides comprehensive plugin querying capabilities.
    
    Responsibilities:
    - Query plugins by various filters
    - Retrieve plugin relationships
    - Get inventory and statistics
    """
    
    def __init__(self, storage, plugin_instances, plugin_specs, execution_stats):
        """
        Initialize query service with references to base service resources.
        
        Args:
            storage: PluginStorage instance
            plugin_instances: In-memory plugin registry
            plugin_specs: Plugin spec cache
            execution_stats: Execution statistics cache
        """
        self._storage = storage
        self._plugin_instances = plugin_instances
        self._plugin_specs = plugin_specs
        self._execution_stats = execution_stats

    def query_by_category(
        self,
        category: str,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Query all plugins of a specific category.
        
        Args:
            category: 'cognitive', 'functional', 'sensory', etc.
            status: Optional specific status filter
            
        Returns:
            List of plugins matching the category
            
        Example:
            >>> cognitive_plugins = service.query_by_category('cognitive')
            >>> active_functional = service.query_by_category('functional', 'ACTIVE')
        """
        records = self._storage.list_plugins(category=category)
        results = []
        
        for record in records:
            if status and record.get("status") != status:
                continue
                
            results.append({
                "plugin_id": record.get("plugin_id"),
                "category": record.get("category"),
                "version": record.get("version"),
                "status": record.get("status"),
                "behavior_key": record.get("behavior_key"),
                "feature_code": record.get("feature_code", record.get("plugin_id")),
                "is_instantiated": record.get("plugin_id") in self._plugin_instances,
            })
        
        logger.info(f"[Query] Found {len(results)} plugins in category '{category}'")
        return results

    def query_cognitive_functionals(
        self,
        cognitive_plugin_id: str,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Query all functional plugins associated with a cognitive plugin.
        
        This implements the cognitive → functional relationship lookup.
        
        Args:
            cognitive_plugin_id: The cognitive plugin ID (e.g., 'q1_where_am_i')
            status: Optional status filter (e.g., 'ACTIVE')
            
        Returns:
            List of functional plugins linked to the cognitive plugin
            
        Example:
            >>> q1_functionals = service.query_cognitive_functionals('q1_where_am_i')
            >>> q1_active_only = service.query_cognitive_functionals('q1_where_am_i', 'ACTIVE')
        """
        # Get all relationships for this cognitive plugin
        relations = self._storage.query_relations_by_cognitive(cognitive_plugin_id)
        
        results = []
        for relation in relations:
            functional_id = relation['functional_plugin_id']
            functional_plugin = self._storage.get_plugin(functional_id)
            
            if not functional_plugin:
                continue
            
            # Apply status filter if specified
            if status and functional_plugin.get('status') != status:
                continue
            
            results.append({
                "plugin_id": functional_plugin.get("plugin_id"),
                "category": functional_plugin.get("category"),
                "version": functional_plugin.get("version"),
                "status": functional_plugin.get("status"),
                "behavior_key": functional_plugin.get("behavior_key"),
                "is_instantiated": functional_id in self._plugin_instances,
                "role": relation['role'],
                "priority": relation['priority'],
                "fallback_id": relation['fallback_id'],
            })
        
        logger.info(
            f"[Query] Found {len(results)} functional plugins for cognitive '{cognitive_plugin_id}'"
        )
        
        return results

    def query_with_filters(
        self,
        category: Optional[str] = None,
        status: Optional[str] = None,
        behavior_key: Optional[str] = None,
        version_gte: Optional[str] = None,
        limit: int = 200,
    ) -> Dict[str, Any]:
        """
        Advanced query with multiple filters.
        
        Args:
            category: Plugin category filter
            status: Plugin status filter
            behavior_key: Behavior key filter
            version_gte: Minimum version (semver)
            limit: Maximum results to return
            
        Returns:
            Filtered plugin list with metadata
        """
        target_limit = max(1, min(limit, 500))
        records = self._storage.list_plugins(category=category)
        
        items = []
        for record in records:
            # Apply status filter
            if status and record.get("status") != status:
                continue
                
            # Apply behavior_key filter
            if behavior_key and record.get("behavior_key") != behavior_key:
                continue
                
            # Apply version filter (simple semver comparison)
            if version_gte:
                record_version = record.get("version", "0.0.0")
                if not self._compare_versions(record_version, version_gte):
                    continue
            
            items.append({
                "plugin_id": record.get("plugin_id"),
                "category": record.get("category"),
                "version": record.get("version"),
                "status": record.get("status"),
                "behavior_key": record.get("behavior_key"),
                "is_instantiated": record.get("plugin_id") in self._plugin_instances,
            })
        
        logger.info(f"[Query] Advanced filter returned {len(items[:target_limit])} results")
        
        return {
            "query_id": f"plugin-query-{uuid4()}",
            "filters": {
                "category": category,
                "status": status,
                "behavior_key": behavior_key,
                "version_gte": version_gte,
            },
            "total": len(items),
            "items": items[:target_limit],
            "truncated": len(items) > target_limit,
        }

    def get_active_inventory(self) -> List[Dict[str, Any]]:
        """
        Return list of currently ACTIVE plugins.
        This is the current usable plugins list.
        
        Returns:
            List of active plugins with metadata
        """
        records = self._storage.list_plugins()
        active_plugins = []
        
        for r in records:
            if r["status"] == PluginLifecycleStatus.ACTIVE.value:
                active_plugins.append({
                    "plugin_id": r["plugin_id"],
                    "category": r["category"],
                    "version": r["version"],
                    "status": r["status"],
                    "behavior_key": r["behavior_key"],
                    "feature_code": r.get("feature_code", r["plugin_id"]),
                    "instantiated": r["plugin_id"] in self._plugin_instances,
                })
        
        logger.info(f"[Query] Active inventory: {len(active_plugins)} plugins")
        return active_plugins

    def get_plugin_execution_stats(self, plugin_id: str) -> Dict[str, Any]:
        """
        Get execution statistics for a specific plugin.
        
        Args:
            plugin_id: The plugin identifier
            
        Returns:
            Execution statistics
        """
        if plugin_id not in self._execution_stats:
            db_plugin = self._storage.get_plugin(plugin_id)
            if db_plugin:
                self._execution_stats[plugin_id] = {
                    'usage_count': db_plugin.get('usage_count', 0),
                    'failure_count': db_plugin.get('failure_count', 0),
                    'last_executed_at': None,
                }
            else:
                logger.warning(f"[Query] Plugin {plugin_id} not found")
                return {}
        
        return self._execution_stats[plugin_id]

    def query_plugins(
        self,
        *,
        category: Optional[str] = None,
        status: str = PluginLifecycleStatus.ACTIVE.value,
        behavior_key: Optional[str] = None,
        limit: int = 200,
    ) -> Dict[str, Any]:
        """
        Query available plugins for callers (backward compatible API).

        Note: This method only returns list metadata and an execution contract.
        Caller decides whether to execute sequentially or concurrently.
        
        Args:
            category: Filter by category
            status: Filter by status (default: ACTIVE)
            behavior_key: Filter by behavior key
            limit: Maximum results
            
        Returns:
            Query results with plugins and execution contract
        """
        target_limit = max(1, min(limit, 500))
        records = self._storage.list_plugins(category=category if category in {"cognitive", "functional"} else None)

        items: List[Dict[str, Any]] = []
        for record in records:
            if status and record.get("status") != status:
                continue
            if behavior_key and record.get("behavior_key") != behavior_key:
                continue

            items.append(
                {
                    "plugin_id": record.get("plugin_id"),
                    "category": record.get("category"),
                    "version": record.get("version"),
                    "status": record.get("status"),
                    "behavior_key": record.get("behavior_key"),
                    "execution_contract": {
                        "method": "execute_plugin_once",
                        "required_fields": ["plugin_id", "task_id", "parameters", "trace_id", "originator_id"],
                    },
                }
            )

        return {
            "query_id": f"plugin-query-{uuid4()}",
            "total": len(items),
            "items": items[:target_limit],
            "truncated": len(items) > target_limit,
        }

    @staticmethod
    def _compare_versions(v1: str, v2: str) -> bool:
        """
        Simple semantic versioning comparison: v1 >= v2
        
        Args:
            v1: Version string (e.g., "1.2.3")
            v2: Version string (e.g., "1.0.0")
            
        Returns:
            True if v1 >= v2, False otherwise
        """
        try:
            parts1 = [int(x) for x in v1.split(".")]
            parts2 = [int(x) for x in v2.split(".")]
            
            for p1, p2 in zip(parts1, parts2):
                if p1 > p2:
                    return True
                elif p1 < p2:
                    return False
            
            return len(parts1) >= len(parts2)
        except (ValueError, AttributeError):
            # If parsing fails, assume v1 >= v2 (safe default)
            return True

    def get_all_plugins(self) -> Dict[str, Any]:
        """
        Get all registered plugins with their specs and status.
        
        Returns:
            Dictionary mapping plugin_id to plugin spec dict
            
        ⚠️ ARCHITECTURAL: This is the ONLY way external modules should
        access the complete plugin registry.
        """
        result = {}
        for plugin_id, spec in self._plugin_specs.items():
            result[plugin_id] = {
                'spec': spec,
                'has_instance': plugin_id in self._plugin_instances,
                'status': spec.get('status', 'unknown'),
            }
        return result

    def get_feature_catalog(self) -> list:
        """
        Get the feature catalog for all plugin categories.
        
        Returns:
            List of feature catalog items
            
        ⚠️ ARCHITECTURAL: This provides a standardized view of available
        plugin features for UI display.
        """
        from zentex.web_console.api import PluginFeatureCatalogItem
        
        # Define standard feature catalog based on plugin categories
        catalog = [
            PluginFeatureCatalogItem(
                feature_code="risk_assessment",
                display_name="风险评估",
                plugin_kind="cognitive_tool",
                supports_multiple_plugins=False,
            ),
            PluginFeatureCatalogItem(
                feature_code="evidence_ranking",
                display_name="证据排序",
                plugin_kind="cognitive_tool",
                supports_multiple_plugins=False,
            ),
            PluginFeatureCatalogItem(
                feature_code="decision_summary",
                display_name="决策摘要",
                plugin_kind="cognitive_tool",
                supports_multiple_plugins=False,
            ),
            PluginFeatureCatalogItem(
                feature_code="cognitive_conflict_detection",
                display_name="认知冲突监控",
                plugin_kind="cognitive_tool",
                supports_multiple_plugins=True,
            ),
            PluginFeatureCatalogItem(
                feature_code="memory_consolidation",
                display_name="离线记忆巩固",
                plugin_kind="cognitive_tool",
                supports_multiple_plugins=True,
            ),
            PluginFeatureCatalogItem(
                feature_code="core.model_provider",
                display_name="大模型推理底座",
                plugin_kind="model_provider",
                supports_multiple_plugins=False,
            ),
            PluginFeatureCatalogItem(
                feature_code="sensory.ingest",
                display_name="信号摄取",
                plugin_kind="signal_ingest",
                supports_multiple_plugins=False,
            ),
            PluginFeatureCatalogItem(
                feature_code="sensory.sanitize",
                display_name="信号净化",
                plugin_kind="signal_sanitize",
                supports_multiple_plugins=False,
            ),
            PluginFeatureCatalogItem(
                feature_code="sensory.interpret",
                display_name="信号解释",
                plugin_kind="signal_interpret",
                supports_multiple_plugins=False,
            ),
            PluginFeatureCatalogItem(
                feature_code="host.telemetry",
                display_name="宿主机健康度采集",
                plugin_kind="host_telemetry",
                supports_multiple_plugins=False,
            ),
            PluginFeatureCatalogItem(
                feature_code="execution.system",
                display_name="系统执行域",
                plugin_kind="execution_domain",
                supports_multiple_plugins=False,
            ),
            PluginFeatureCatalogItem(
                feature_code="execution.browser",
                display_name="浏览器执行域",
                plugin_kind="execution_domain",
                supports_multiple_plugins=False,
            ),
            PluginFeatureCatalogItem(
                feature_code="simulation.bundle",
                display_name="通用推演沙箱",
                plugin_kind="simulation_domain",
                supports_multiple_plugins=False,
            ),
            PluginFeatureCatalogItem(
                feature_code="simulation.market",
                display_name="市场推演沙箱",
                plugin_kind="simulation_domain",
                supports_multiple_plugins=False,
            ),
            PluginFeatureCatalogItem(
                feature_code="weights:subjective_preferences",
                display_name="主观权重偏好",
                plugin_kind="subjective_weight",
                supports_multiple_plugins=True,
            ),
            PluginFeatureCatalogItem(
                feature_code="identity:package_loader",
                display_name="身份与经验包",
                plugin_kind="identity_package",
                supports_multiple_plugins=True,
            ),
            PluginFeatureCatalogItem(
                feature_code="redline.core",
                display_name="红线禁区基座",
                plugin_kind="redline",
                supports_multiple_plugins=True,
            ),
            PluginFeatureCatalogItem(
                feature_code="alternative.core",
                display_name="备选策略基座",
                plugin_kind="alternative",
                supports_multiple_plugins=True,
            ),
            PluginFeatureCatalogItem(
                feature_code="objective.core",
                display_name="主目标编排基座",
                plugin_kind="objective",
                supports_multiple_plugins=True,
            ),
            PluginFeatureCatalogItem(
                feature_code="posture.core",
                display_name="行动姿态基座",
                plugin_kind="posture",
                supports_multiple_plugins=True,
            ),
            PluginFeatureCatalogItem(
                feature_code="nine_questions.q1",
                display_name="九问 Q1（LLM 强制）",
                plugin_kind="cognitive_tool",
                supports_multiple_plugins=True,
            ),
            PluginFeatureCatalogItem(
                feature_code="nine_questions.q2",
                display_name="九问 Q2（LLM 强制）",
                plugin_kind="cognitive_tool",
                supports_multiple_plugins=True,
            ),
            PluginFeatureCatalogItem(
                feature_code="nine_questions.q3",
                display_name="九问 Q3（LLM 强制）",
                plugin_kind="cognitive_tool",
                supports_multiple_plugins=True,
            ),
            PluginFeatureCatalogItem(
                feature_code="nine_questions.q4",
                display_name="九问 Q4（LLM 强制）",
                plugin_kind="cognitive_tool",
                supports_multiple_plugins=True,
            ),
            PluginFeatureCatalogItem(
                feature_code="nine_questions.q5",
                display_name="九问 Q5（LLM 强制）",
                plugin_kind="cognitive_tool",
                supports_multiple_plugins=True,
            ),
            PluginFeatureCatalogItem(
                feature_code="nine_questions.q6",
                display_name="九问 Q6（LLM 强制）",
                plugin_kind="cognitive_tool",
                supports_multiple_plugins=True,
            ),
            PluginFeatureCatalogItem(
                feature_code="nine_questions.q7",
                display_name="九问 Q7（LLM 强制）",
                plugin_kind="cognitive_tool",
                supports_multiple_plugins=True,
            ),
            PluginFeatureCatalogItem(
                feature_code="nine_questions.q8",
                display_name="九问 Q8（LLM 强制）",
                plugin_kind="cognitive_tool",
                supports_multiple_plugins=True,
            ),
            PluginFeatureCatalogItem(
                feature_code="nine_questions.q9",
                display_name="九问 Q9（LLM 强制）",
                plugin_kind="cognitive_tool",
                supports_multiple_plugins=True,
            ),
            PluginFeatureCatalogItem(
                feature_code="memory.extract",
                display_name="记忆提取（LLM 强制）",
                plugin_kind="cognitive_tool",
                supports_multiple_plugins=True,
            ),
            PluginFeatureCatalogItem(
                feature_code="reflection.generate",
                display_name="反思生成（LLM 强制）",
                plugin_kind="cognitive_tool",
                supports_multiple_plugins=True,
            ),
        ]
        return catalog
