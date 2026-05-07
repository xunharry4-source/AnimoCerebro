"""
反思数据访问对象 (DAO) - 使用 SQLite 数据库代替 JSON 文件

这个模块提供反思数据的数据库操作，替代 JSON 文件存储。

特点：
- ✅ 事务支持
- ✅ 并发安全  
- ✅ 高效查询
- ✅ 自动索引
- ✅ 备份和恢复
"""

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from zentex.common.database import BaseDAO, DatabaseConnection, LRUCache
from zentex.reflection.models import (
    ReflectionRecord, ReflectionTemplate, ReflectionInsight,
    ReflectionPattern, ReflectionMetrics, ReflectionType, ReflectionTrigger,
    ReflectionOverallRecord, ReflectionQuality,
)

logger = logging.getLogger(__name__)


class ReflectionDAO(BaseDAO):
    """反思记录数据访问对象"""
    
    def __init__(self, db: DatabaseConnection, cache: Optional[LRUCache] = None):
        super().__init__(db, cache)
        self._init_tables()
    
    def _init_tables(self):
        """初始化数据库表"""
        # 反思记录表
        self.db.execute_update("""
            CREATE TABLE IF NOT EXISTS reflections (
                reflection_id TEXT PRIMARY KEY,
                trace_id TEXT,
                audit_id TEXT,
                session_id TEXT,
                reflection_type TEXT NOT NULL,
                depth TEXT NOT NULL,
                quality TEXT NOT NULL,
                trigger TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                reflection_timestamp TEXT NOT NULL,
                subject TEXT NOT NULL,
                context TEXT,
                summary TEXT NOT NULL,
                confidence REAL DEFAULT 0.7,
                impact_score REAL DEFAULT 0.5,
                actionability REAL DEFAULT 0.5,
                related_decisions TEXT,
                related_actions TEXT,
                related_outcomes TEXT,
                tags TEXT,
                metadata TEXT,
                governance_status TEXT DEFAULT 'active',
                suspect_reason TEXT,
                verified_at TEXT,
                verified_by TEXT,
                reflection_list TEXT,
                created_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 模板表
        self.db.execute_update("""
            CREATE TABLE IF NOT EXISTS reflection_templates (
                template_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                reflection_type TEXT,
                content TEXT,
                created_at TEXT NOT NULL,
                modified_at TEXT
            )
        """)
        
        # 洞察表
        self.db.execute_update("""
            CREATE TABLE IF NOT EXISTS reflection_insights (
                insight_id TEXT PRIMARY KEY,
                reflection_id TEXT,
                category TEXT,
                content TEXT NOT NULL,
                confidence REAL,
                related_insights TEXT,
                created_at TEXT NOT NULL
            )
        """)
        
        # 模式表
        self.db.execute_update("""
            CREATE TABLE IF NOT EXISTS reflection_patterns (
                pattern_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                occurrences INTEGER DEFAULT 0,
                last_seen TEXT,
                related_reflections TEXT,
                created_at TEXT NOT NULL
            )
        """)
        
        # 指标表
        self.db.execute_update("""
            CREATE TABLE IF NOT EXISTS reflection_metrics (
                metrics_id TEXT PRIMARY KEY,
                total_reflections INTEGER DEFAULT 0,
                average_quality REAL DEFAULT 0.0,
                average_confidence REAL DEFAULT 0.0,
                average_impact REAL DEFAULT 0.0,
                top_patterns TEXT,
                calculated_at TEXT NOT NULL
            )
        """)

        self.db.execute_update("""
            CREATE TABLE IF NOT EXISTS reflection_overall_records (
                overall_id TEXT PRIMARY KEY,
                reflection_id TEXT NOT NULL,
                trace_id TEXT,
                audit_id TEXT,
                session_id TEXT,
                reflection_type TEXT NOT NULL,
                subject TEXT NOT NULL,
                summary TEXT NOT NULL,
                quality TEXT NOT NULL,
                confidence REAL DEFAULT 0.7,
                impact_score REAL DEFAULT 0.5,
                actionability REAL DEFAULT 0.5,
                tags TEXT,
                metadata TEXT,
                created_at TEXT NOT NULL,
                created_timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 创建索引
        self.db.execute_update("CREATE INDEX IF NOT EXISTS idx_reflections_created_at ON reflections(created_at)")
        self.db.execute_update("CREATE INDEX IF NOT EXISTS idx_reflections_type ON reflections(reflection_type)")
        self.db.execute_update("CREATE INDEX IF NOT EXISTS idx_reflections_status ON reflections(governance_status)")
        self.db.execute_update("CREATE INDEX IF NOT EXISTS idx_insights_reflection ON reflection_insights(reflection_id)")
        self.db.execute_update("CREATE INDEX IF NOT EXISTS idx_reflection_overall_reflection_id ON reflection_overall_records(reflection_id)")
        self.db.execute_update("CREATE INDEX IF NOT EXISTS idx_reflection_overall_trace_id ON reflection_overall_records(trace_id)")
        self.db.execute_update("CREATE INDEX IF NOT EXISTS idx_reflection_overall_created_at ON reflection_overall_records(created_at DESC)")

        # 迁移旧库：补 audit_id 列（新建库已包含此列，旧库需 ALTER TABLE）
        existing_columns = {
            str(row["name"])
            for row in self.db.execute_query("PRAGMA table_info(reflections)")
        }
        if "audit_id" not in existing_columns:
            try:
                self.db.execute_update("ALTER TABLE reflections ADD COLUMN audit_id TEXT DEFAULT ''")
            except Exception:
                logger.exception("Failed to migrate reflections.audit_id column")
                raise
        if "suspect_reason" not in existing_columns:
            try:
                self.db.execute_update("ALTER TABLE reflections ADD COLUMN suspect_reason TEXT")
            except Exception:
                logger.exception("Failed to migrate reflections.suspect_reason column")
                raise
        self.db.execute_update("CREATE INDEX IF NOT EXISTS idx_reflections_audit_id ON reflections(audit_id)")

        logger.info("Reflection database tables initialized")
    
    # ===== 反思操作 =====
    
    def save_reflection(self, reflection: ReflectionRecord) -> bool:
        """保存单个反思记录"""
        try:
            query = """
                INSERT OR REPLACE INTO reflections (
                    reflection_id, trace_id, audit_id, session_id, reflection_type, depth, quality, trigger,
                    created_at, updated_at, reflection_timestamp, subject, context, summary,
                    confidence, impact_score, actionability,
                    related_decisions, related_actions, related_outcomes, tags, metadata,
                    governance_status, suspect_reason, verified_at, verified_by, reflection_list
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """

            # Derive audit_id: prefer explicit field, fall back to context["audit_id"].
            audit_id = reflection.audit_id or (
                reflection.context.get("audit_id") if isinstance(reflection.context, dict) else None
            ) or ""

            params = (
                reflection.reflection_id,
                reflection.trace_id,
                audit_id,
                reflection.session_id,
                reflection.reflection_type.value,
                reflection.depth.value,
                reflection.quality.value,
                reflection.trigger.value,
                reflection.created_at.isoformat(),
                reflection.updated_at.isoformat(),
                reflection.reflection_timestamp.isoformat(),
                reflection.subject,
                json.dumps(reflection.context) if reflection.context else None,
                reflection.summary,
                reflection.confidence,
                reflection.impact_score,
                reflection.actionability,
                json.dumps(reflection.related_decisions) if reflection.related_decisions else None,
                json.dumps(reflection.related_actions) if reflection.related_actions else None,
                json.dumps(reflection.related_outcomes) if reflection.related_outcomes else None,
                json.dumps(reflection.tags) if reflection.tags else None,
                json.dumps(reflection.metadata) if reflection.metadata else None,
                reflection.governance_status.value,
                reflection.suspect_reason,
                reflection.verified_at.isoformat() if reflection.verified_at else None,
                reflection.verified_by,
                json.dumps([item.model_dump(mode='json') for item in reflection.reflection_list]) if reflection.reflection_list else None
            )
            
            self.db.execute_update(query, params)
            self.save_overall_record(self._to_overall_record(reflection))
            
            # 更新缓存
            if self.cache:
                self.cache.set(f"reflection:{reflection.reflection_id}", reflection)
            
            logger.debug(f"Successfully saved reflection: {reflection.reflection_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save reflection: {e}")
            return False

    @staticmethod
    def _append_reflection_filters(
        query: str,
        params: List[Any],
        filters: Dict[str, Any],
    ) -> tuple[str, List[Any]]:
        if "reflection_type" in filters:
            query += " AND reflection_type = ?"
            value = filters["reflection_type"]
            params.append(value.value if hasattr(value, "value") else value)

        if "governance_status" in filters:
            query += " AND governance_status = ?"
            value = filters["governance_status"]
            params.append(value.value if hasattr(value, "value") else value)

        if "start_time" in filters:
            query += " AND created_at >= ?"
            value = filters["start_time"]
            params.append(value.isoformat() if hasattr(value, "isoformat") else str(value))

        if "end_time" in filters:
            query += " AND created_at <= ?"
            value = filters["end_time"]
            params.append(value.isoformat() if hasattr(value, "isoformat") else str(value))

        if "date" in filters:
            query += " AND substr(created_at, 1, 10) = ?"
            params.append(str(filters["date"]))

        if "audit_id" in filters:
            query += " AND audit_id = ?"
            params.append(str(filters["audit_id"]))

        if "trace_id" in filters:
            query += " AND trace_id = ?"
            params.append(str(filters["trace_id"]))

        if "question_id" in filters:
            query += " AND json_extract(context, '$.question_id') = ?"
            params.append(str(filters["question_id"]))

        if filters.get("question_scope") == "nine_questions":
            query += " AND json_extract(context, '$.question_id') LIKE 'q%'"

        if str(filters.get("source") or "").strip().lower() == "plugin":
            query += """
                AND (
                    LOWER(COALESCE(json_extract(metadata, '$.source'), '')) LIKE '%plugin%'
                    OR LOWER(COALESCE(json_extract(context, '$.source'), '')) LIKE '%plugin%'
                    OR LOWER(COALESCE(json_extract(context, '$.source_module'), '')) LIKE '%plugin%'
                    OR LOWER(COALESCE(json_extract(metadata, '$.module_id'), '')) LIKE '%plugin%'
                    OR LOWER(COALESCE(subject, '')) LIKE '%plugin%'
                )
            """

        return query, params

    def count_reflections(self, filters: Dict[str, Any]) -> int:
        query = "SELECT COUNT(*) AS count FROM reflections WHERE 1=1"
        query, params = self._append_reflection_filters(query, [], filters)
        rows = self.db.execute_query(query, tuple(params))
        if not rows:
            return 0
        row = rows[0] if isinstance(rows, list) else rows
        return int(row["count"] or 0)

    def query_reflections_page(
        self,
        filters: Dict[str, Any],
        *,
        limit: int,
        offset: int,
    ) -> List[ReflectionRecord]:
        query = "SELECT * FROM reflections WHERE 1=1"
        query, params = self._append_reflection_filters(query, [], filters)
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([max(1, int(limit)), max(0, int(offset))])
        rows = self.db.execute_query(query, tuple(params))
        return [self._row_to_reflection(row) for row in rows]

    def save_overall_record(self, overall: ReflectionOverallRecord) -> bool:
        try:
            query = """
                INSERT OR REPLACE INTO reflection_overall_records (
                    overall_id, reflection_id, trace_id, audit_id, session_id, reflection_type,
                    subject, summary, quality, confidence, impact_score, actionability,
                    tags, metadata, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            params = (
                overall.overall_id,
                overall.reflection_id,
                overall.trace_id,
                overall.audit_id,
                overall.session_id,
                overall.reflection_type.value,
                overall.subject,
                overall.summary,
                overall.quality.value,
                overall.confidence,
                overall.impact_score,
                overall.actionability,
                json.dumps(overall.tags) if overall.tags else None,
                json.dumps(overall.metadata) if overall.metadata else None,
                overall.created_at.isoformat(),
            )
            self.db.execute_update(query, params)
            return True
        except Exception as e:
            logger.error(f"Failed to save reflection overall record: {e}")
            return False

    def list_overall_records(
        self,
        *,
        limit: int = 100,
        trace_id: Optional[str] = None,
        reflection_type: Optional[ReflectionType] = None,
    ) -> List[ReflectionOverallRecord]:
        try:
            conditions = []
            params: List[Any] = []
            if trace_id:
                conditions.append("trace_id = ?")
                params.append(trace_id)
            if reflection_type:
                conditions.append("reflection_type = ?")
                params.append(reflection_type.value if isinstance(reflection_type, ReflectionType) else str(reflection_type))
            where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""
            rows = self.db.execute_query(
                f"""
                SELECT * FROM reflection_overall_records
                {where_sql}
                ORDER BY created_at DESC
                LIMIT ?
                """,
                tuple([*params, limit]),
            )
            return [self._row_to_overall_record(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to list reflection overall records: {e}")
            return []
    
    def get_reflection(self, reflection_id: str) -> Optional[ReflectionRecord]:
        """获取单个反思记录"""
        # 尝试从缓存获取
        if self.cache:
            cached = self.cache.get(f"reflection:{reflection_id}")
            if cached:
                return cached
        
        try:
            query = "SELECT * FROM reflections WHERE reflection_id = ?"
            rows = self.db.execute_query(query, (reflection_id,))
            
            if not rows:
                return None

            row = rows[0]
            reflection = self._row_to_reflection(row)
            
            # 保存到缓存
            if self.cache:
                self.cache.set(f"reflection:{reflection_id}", reflection)
            
            return reflection
            
        except Exception as e:
            logger.error(f"Failed to get reflection: {e}")
            return None

    def _to_overall_record(self, reflection: ReflectionRecord) -> ReflectionOverallRecord:
        audit_id = reflection.audit_id or (
            reflection.context.get("audit_id") if isinstance(reflection.context, dict) else None
        )
        context_summary = ""
        if isinstance(reflection.context, dict):
            context_summary = str(reflection.context.get("summary") or "").strip()
        overall_summary = str(reflection.summary or "").strip()
        if context_summary and context_summary not in overall_summary:
            overall_summary = (
                f"{overall_summary} | {context_summary}"
                if overall_summary
                else context_summary
            )
        metadata = {
            "source_reflection_id": reflection.reflection_id,
            "governance_status": reflection.governance_status.value,
        }
        if isinstance(reflection.metadata, dict):
            for key in ("module_id", "question_id", "source"):
                if key in reflection.metadata:
                    metadata[key] = reflection.metadata[key]
        return ReflectionOverallRecord(
            overall_id=f"overall_{reflection.reflection_id}",
            reflection_id=reflection.reflection_id,
            trace_id=reflection.trace_id,
            audit_id=str(audit_id) if audit_id else None,
            session_id=reflection.session_id,
            reflection_type=reflection.reflection_type,
            subject=reflection.subject,
            summary=overall_summary,
            quality=reflection.quality if isinstance(reflection.quality, ReflectionQuality) else ReflectionQuality(str(reflection.quality)),
            confidence=reflection.confidence,
            impact_score=reflection.impact_score,
            actionability=reflection.actionability,
            tags=list(reflection.tags or []),
            metadata=metadata,
            created_at=reflection.created_at,
        )

    def _row_to_overall_record(self, row: Dict[str, Any]) -> ReflectionOverallRecord:
        return ReflectionOverallRecord(
            overall_id=row["overall_id"],
            reflection_id=row["reflection_id"],
            trace_id=row["trace_id"],
            audit_id=row["audit_id"],
            session_id=row["session_id"],
            reflection_type=ReflectionType(row["reflection_type"]),
            subject=row["subject"],
            summary=row["summary"],
            quality=ReflectionQuality(row["quality"]),
            confidence=float(row["confidence"] or 0.7),
            impact_score=float(row["impact_score"] or 0.5),
            actionability=float(row["actionability"] or 0.5),
            tags=json.loads(row["tags"]) if row["tags"] else [],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            created_at=datetime.fromisoformat(row["created_at"]),
        )
    
    def load_all_reflections(self) -> Dict[str, ReflectionRecord]:
        """加载所有反思记录"""
        try:
            query = "SELECT * FROM reflections ORDER BY created_at DESC"
            rows = self.db.execute_query(query)
            
            reflections = {}
            for row in rows:
                reflection = self._row_to_reflection(row)
                reflections[reflection.reflection_id] = reflection
            
            logger.debug(f"Loaded {len(reflections)} reflections from database")
            return reflections
            
        except Exception as e:
            logger.error(f"Failed to load reflections: {e}")
            return {}
    
    def delete_reflection(self, reflection_id: str) -> bool:
        """删除反思记录"""
        try:
            self.db.execute_update(
                "DELETE FROM reflection_overall_records WHERE reflection_id = ?",
                (reflection_id,),
            )
            affected = self.db.execute_update(
                "DELETE FROM reflections WHERE reflection_id = ?",
                (reflection_id,),
            )
            
            # 清除缓存
            if self.cache:
                self.cache.invalidate(f"reflection:{reflection_id}")
            
            logger.debug(f"Deleted reflection: {reflection_id}")
            return affected > 0
            
        except Exception as e:
            logger.error(f"Failed to delete reflection: {e}")
            return False
    
    def query_reflections(self, filters: Dict[str, Any]) -> List[ReflectionRecord]:
        """查询反思记录"""
        try:
            query = "SELECT * FROM reflections WHERE 1=1"
            params = []
            query, params = self._append_reflection_filters(query, params, filters)

            limit = int(filters.get("limit", 1000))
            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)

            rows = self.db.execute_query(query, tuple(params))

            reflections = [self._row_to_reflection(row) for row in rows]
            logger.debug(f"Queried {len(reflections)} reflections with filters: {filters}")

            return reflections

        except Exception as e:
            logger.error(f"Failed to query reflections: {e}")
            return []

    def get_by_audit_id(self, audit_id: str) -> List[ReflectionRecord]:
        """返回属于同一 FlowAudit 流程的所有反思记录，按创建时间升序排列。"""
        if not audit_id:
            return []
        try:
            rows = self.db.execute_query(
                "SELECT * FROM reflections WHERE audit_id = ? ORDER BY created_at ASC",
                (audit_id,),
            )
            return [self._row_to_reflection(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to get reflections by audit_id: {e}")
            return []

    def query_system_problem_improvement_findings(
        self,
        *,
        limit: int = 10,
        max_source_records: int = 1000,
        problem_scope: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Query persisted reflection evidence for current system problems and improvements."""
        effective_limit = max(1, int(limit))
        source_limit = max(effective_limit, int(max_source_records))
        requested_scope = self._normalize_problem_scope(problem_scope)
        rows = self.db.execute_query(
            """
            SELECT
                reflection_id,
                trace_id,
                audit_id,
                subject,
                reflection_type,
                quality,
                governance_status,
                suspect_reason,
                context,
                summary,
                reflection_list,
                tags,
                metadata,
                created_at
            FROM reflections
            WHERE governance_status NOT IN ('archived', 'deprecated', 'hidden')
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (source_limit,),
        )

        problems: List[Dict[str, Any]] = []
        improvements: List[Dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()

        for row in rows:
            base = {
                "reflection_id": row["reflection_id"],
                "trace_id": row["trace_id"],
                "audit_id": row["audit_id"],
                "subject": row["subject"],
                "reflection_type": row["reflection_type"],
                "quality": row["quality"],
                "governance_status": row["governance_status"],
                "created_at": row["created_at"],
                "tags": self._loads_json(row["tags"], []),
                "metadata": self._loads_json(row["metadata"], {}),
            }
            context = self._loads_json(row["context"], {})
            reflection_items = self._loads_json(row["reflection_list"], [])
            base["reflection_target"] = self._infer_reflection_target(
                context=context,
                metadata=base["metadata"],
                subject=row["subject"],
            )
            base_scope = self._infer_problem_scope(
                context=context,
                metadata=base["metadata"],
                tags=base["tags"],
                subject=row["subject"],
                reflection_type=row["reflection_type"],
                source_field="reflection",
                content=row["summary"],
            )

            def add_finding(
                bucket: List[Dict[str, Any]],
                finding_type: str,
                content: Any,
                *,
                source_field: str,
                priority: Optional[int] = None,
                scope_hint: Optional[str] = None,
                structured_source: Optional[Dict[str, Any]] = None,
            ) -> None:
                text = str(content or "").strip()
                if not text:
                    return
                finding_scope = self._infer_problem_scope(
                    context=context,
                    metadata=base["metadata"],
                    tags=base["tags"],
                    subject=row["subject"],
                    reflection_type=row["reflection_type"],
                    source_field=source_field,
                    content=text,
                    explicit_scope=scope_hint or base_scope,
                )
                if requested_scope is not None and finding_scope != requested_scope:
                    return
                if not self._is_system_problem_improvement_text(text, finding_type=finding_type):
                    return
                dedup_text = self._normalized_finding_text(text)
                if not dedup_text:
                    return
                key = (finding_type, finding_scope, dedup_text)
                if key in seen:
                    return
                seen.add(key)
                structured_fields = self._structured_reflection_problem_fields(
                    source=structured_source or {},
                    context=context,
                    metadata=base["metadata"],
                    subject=row["subject"],
                    fallback_reflection_object=base["reflection_target"],
                    fallback_failure_fact=text,
                )
                if requested_scope == "external" and self._is_internal_reflection_object(
                    structured_fields.get("reflection_object")
                ):
                    return
                bucket.append(
                    {
                        **base,
                        "finding_id": (
                            f"{finding_type}:{base['reflection_id']}:"
                            f"{source_field}:{len(bucket) + 1}"
                        ),
                        "finding_type": finding_type,
                        "problem_scope": finding_scope,
                        "content": text,
                        "source_field": source_field,
                        "priority": priority,
                        **structured_fields,
                    }
                )

            for index, item in enumerate(reflection_items if isinstance(reflection_items, list) else []):
                if not isinstance(item, dict):
                    continue
                category = str(item.get("category") or "").strip().lower()
                priority = item.get("priority")
                priority_value = int(priority) if isinstance(priority, int) else None
                if category in {"risk", "problem", "issue"}:
                    add_finding(
                        problems,
                        "problem",
                        item.get("content"),
                        source_field=f"reflection_list[{index}].{category}",
                        priority=priority_value,
                        scope_hint=item.get("problem_scope") or item.get("scope") or item.get("lane"),
                        structured_source=item,
                    )
                elif category in {"improvement", "meta"}:
                    add_finding(
                        improvements,
                        "improvement",
                        item.get("content"),
                        source_field=f"reflection_list[{index}].{category}",
                        priority=priority_value,
                        scope_hint=item.get("problem_scope") or item.get("scope") or item.get("lane"),
                        structured_source=item,
                    )

            for source_field in ("risks", "problems", "issues"):
                for value in self._iter_text_values(context.get(source_field)):
                    add_finding(problems, "problem", value, source_field=f"context.{source_field}")

            for source_field in (
                "improvements",
                "improvement_suggestions",
                "recommended_improvements",
                "actionable_adjustment",
            ):
                for value in self._iter_text_values(context.get(source_field)):
                    add_finding(improvements, "improvement", value, source_field=f"context.{source_field}")

            if row["governance_status"] == "suspect":
                add_finding(
                    problems,
                    "problem",
                    row["suspect_reason"] or row["summary"],
                    source_field="governance_status.suspect",
                )
            if row["reflection_type"] == ReflectionType.ERROR_REFLECTION.value:
                add_finding(
                    problems,
                    "problem",
                    row["summary"],
                    source_field="reflection_type.error_reflection",
                )
        all_findings = [*problems, *improvements]
        totals_by_scope: Dict[str, int] = {"internal": 0, "external": 0, "unknown": 0}
        for finding in all_findings:
            scope = str(finding.get("problem_scope") or "unknown")
            totals_by_scope[scope] = int(totals_by_scope.get(scope, 0)) + 1

        return {
            "database_backed": True,
            "source_table": "reflections",
            "problem_scope_filter": requested_scope,
            "total_problems": len(problems),
            "total_improvements": len(improvements),
            "totals_by_scope": totals_by_scope,
            "current_problems": problems[:effective_limit],
            "improvement_opportunities": improvements[:effective_limit],
            "queried_source_records": len(rows),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def query_current_problem_contents(
        self,
        *,
        limit: int = 10,
        max_source_records: int = 1000,
        problem_scope: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Return only current problem content for prompt consumers that need compact reflection input."""
        result = self.query_system_problem_improvement_findings(
            limit=limit,
            max_source_records=max_source_records,
            problem_scope=problem_scope,
        )
        current_problems = result.get("current_problems")
        contents: List[Dict[str, str]] = []
        for item in (current_problems if isinstance(current_problems, list) else []):
            if not isinstance(item, dict):
                continue
            projected = {
                "reflection_object": str(item.get("reflection_object") or "").strip(),
                "failure_fact": str(item.get("failure_fact") or "").strip(),
                "root_cause": str(item.get("root_cause") or "").strip(),
                "improvement_direction": str(item.get("improvement_direction") or "").strip(),
            }
            if problem_scope == "external" and self._is_internal_reflection_object(
                projected["reflection_object"]
            ):
                continue
            if all(projected.values()) and all(
                self._is_prompt_safe_reflection_field(value) for value in projected.values()
            ):
                contents.append(projected)
        return {"current_problems": contents}

    @staticmethod
    def _loads_json(value: Any, default: Any) -> Any:
        if not value:
            return default
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return default

    @classmethod
    def _structured_reflection_problem_fields(
        cls,
        *,
        source: Dict[str, Any],
        context: Dict[str, Any],
        metadata: Dict[str, Any],
        subject: Any,
        fallback_reflection_object: str,
        fallback_failure_fact: str,
    ) -> Dict[str, str]:
        item_metadata = source.get("metadata") if isinstance(source.get("metadata"), dict) else {}
        reflection_object = cls._first_text(
            source.get("reflection_object"),
            source.get("reflected_object"),
            source.get("target_object"),
            item_metadata.get("reflection_object"),
            context.get("reflection_object"),
            context.get("reflection_target"),
            metadata.get("reflection_object"),
            fallback_reflection_object,
        )
        reflection_object = (
            cls._normalize_reflection_target(reflection_object, source_key="reflection_object")
            or cls._infer_reflection_target(context=context, metadata=metadata, subject=subject)
        )
        failure_fact = cls._first_text(
            source.get("failure_fact"),
            source.get("problem_fact"),
            source.get("fact"),
            item_metadata.get("failure_fact"),
            item_metadata.get("problem_fact"),
            context.get("failure_fact"),
            context.get("problem_fact"),
            fallback_failure_fact,
        )
        root_cause = cls._first_text(
            source.get("root_cause"),
            source.get("cause"),
            source.get("reason"),
            item_metadata.get("root_cause"),
            item_metadata.get("cause"),
            context.get("root_cause"),
            context.get("cause"),
            context.get("reason"),
        )
        improvement_direction = cls._first_text(
            source.get("improvement_direction"),
            source.get("improvement"),
            source.get("next_improvement"),
            item_metadata.get("improvement_direction"),
            item_metadata.get("improvement"),
            context.get("improvement_direction"),
            context.get("next_improvement"),
            context.get("improvement"),
        )
        return {
            "reflection_object": reflection_object,
            "failure_fact": failure_fact,
            "root_cause": root_cause,
            "improvement_direction": improvement_direction,
        }

    @staticmethod
    def _first_text(*values: Any) -> str:
        for value in values:
            if value is None:
                continue
            if isinstance(value, dict):
                for key in (
                    "reflection_object",
                    "failure_fact",
                    "root_cause",
                    "improvement_direction",
                    "content",
                    "summary",
                    "description",
                    "text",
                    "message",
                    "name",
                ):
                    text = str(value.get(key) or "").strip()
                    if text:
                        return text
                continue
            if isinstance(value, list):
                for item in value:
                    text = ReflectionDAO._first_text(item)
                    if text:
                        return text
                continue
            text = str(value or "").strip()
            if text:
                return text
        return ""

    @staticmethod
    def _is_prompt_safe_reflection_field(value: Any) -> bool:
        text = str(value or "").strip()
        if not text:
            return False
        return not re.fullmatch(r"[a-z0-9_.:-]+", text.lower())

    @staticmethod
    def _is_internal_reflection_object(value: Any) -> bool:
        text = str(value or "").strip()
        if not text:
            return False
        lower = text.lower()
        if re.fullmatch(r"q[1-9]", lower):
            return True
        internal_object_markers = (
            "九问第",
            "模块「九问",
            "nine questions",
            "internal cognition",
            "internal cognitive",
            "memory governance",
            "learning service",
            "reflection service",
            "内部认知",
            "记忆治理",
            "学习服务",
            "反思服务",
            "自我演化",
        )
        return any(marker in lower or marker in text for marker in internal_object_markers)

    @staticmethod
    def _iter_text_values(value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        if isinstance(value, dict):
            for key in ("content", "summary", "description", "text", "message"):
                if value.get(key):
                    return [str(value[key])]
            return [json.dumps(value, ensure_ascii=False, sort_keys=True)]
        if isinstance(value, list):
            values: List[str] = []
            for item in value:
                values.extend(ReflectionDAO._iter_text_values(item))
            return values
        return [str(value)]

    @staticmethod
    def _normalize_problem_scope(value: Any) -> Optional[str]:
        text = str(value or "").strip().lower()
        if not text or text == "all":
            return None
        if text in {"internal", "inside", "inner", "cognitive", "内部", "内"}:
            return "internal"
        if text in {"external", "outside", "outer", "execution", "外部", "外"}:
            return "external"
        if text in {"unknown", "unclear", "未知"}:
            return "unknown"
        raise ValueError(f"invalid_problem_scope:{value}")

    @staticmethod
    def _normalized_finding_text(value: Any) -> str:
        text = str(value or "").strip().lower()
        if not text:
            return ""
        text = re.sub(r"\s+", " ", text)
        text = re.sub(r"[\u200b-\u200d\ufeff]", "", text)
        text = re.sub(r"[\"'`*_~#>\[\](){}<>，。！？、；：,.!?;:]+", "", text)
        return text.strip()

    @staticmethod
    def _current_problem_content_for_prompt(
        content: str,
        problem_scope: Optional[str],
        reflection_target: str = "",
    ) -> str:
        target_text = reflection_target.strip()
        if problem_scope == "internal":
            return f"内部认知轨反思对象：{target_text}；问题内容：{content}"
        if problem_scope == "external":
            return f"外部执行轨反思对象：{target_text}；问题内容：{content}"
        return f"反思对象：{target_text}；问题内容：{content}"

    @classmethod
    def _infer_reflection_target(
        cls,
        *,
        context: Dict[str, Any],
        metadata: Dict[str, Any],
        subject: Any,
    ) -> str:
        for source in (context, metadata):
            if not isinstance(source, dict):
                continue
            for key in (
                "reflection_target",
                "target_subject",
                "target_object",
                "target_id",
                "task_id",
                "module_id",
                "plugin_id",
                "question_id",
                "source_module",
            ):
                target = cls._normalize_reflection_target(source.get(key), source_key=key)
                if target:
                    return target
        subject_target = cls._normalize_reflection_subject(subject)
        return subject_target

    @classmethod
    def _normalize_reflection_target(cls, value: Any, *, source_key: str = "") -> str:
        if isinstance(value, dict):
            for key in ("reflection_target", "target_subject", "target_id", "task_id", "module_id", "plugin_id", "question_id", "name", "id"):
                nested = cls._normalize_reflection_target(value.get(key), source_key=key)
                if nested:
                    return nested
            return ""
        if isinstance(value, list):
            for item in value:
                nested = cls._normalize_reflection_target(item, source_key=source_key)
                if nested:
                    return nested
            return ""
        text = str(value or "").strip()
        if not text or text.lower() in {"none", "null", "unknown", "n/a"}:
            return ""
        key = source_key.strip().lower()
        lower = text.lower()
        if key == "question_id" and re.fullmatch(r"q[1-9]", lower):
            return cls._question_reflection_target_name(lower)
        if key == "module_id":
            return cls._known_component_reflection_target(text)
        if key == "plugin_id":
            return cls._known_component_reflection_target(text)
        if key == "task_id":
            return cls._human_readable_target_name(text, prefix="任务")
        if key == "target_id":
            return cls._human_readable_target_name(text, prefix="目标")
        if key == "source_module":
            return cls._known_component_reflection_target(text)
        return cls._normalize_reflection_subject(text)

    @staticmethod
    def _normalize_reflection_subject(value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        lower = text.lower()
        generic_subjects = {
            "ci-reflect",
            "ci_reflect",
            "reflect",
            "reflection",
            "internal-reflect",
            "external-reflect",
            "auto-reflect",
            "scheduled-reflect",
            "nine-question-reflect",
        }
        if lower in generic_subjects or lower.endswith("-reflect") or lower.endswith("_reflect"):
            return ""
        if re.fullmatch(r"[a-z0-9_.:-]+", lower):
            return ""
        return text

    @staticmethod
    def _question_reflection_target_name(question_id: str) -> str:
        names = {
            "q1": "模块「九问第一问：环境定位（我在哪里）」",
            "q2": "模块「九问第二问：资产盘点（我有什么）」",
            "q3": "模块「九问第三问：身份推断（我是谁）」",
            "q4": "模块「九问第四问：目标候选生成（我能做什么）」",
            "q5": "模块「九问第五问：授权边界判断（我可以做什么）」",
            "q6": "模块「九问第六问：后果约束与禁区识别（我不应该做什么）」",
            "q7": "模块「九问第七问：替代可能性探索（我还能做什么）」",
            "q8": "模块「九问第八问：即时目标综合（我现在应该做什么）」",
            "q9": "模块「九问第九问：行动方案设计（我应该怎么做）」",
        }
        return names.get(question_id.lower(), "")

    @classmethod
    def _known_component_reflection_target(cls, value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        lower = text.lower()
        for question_id in ("q1", "q2", "q3", "q4", "q5", "q6", "q7", "q8", "q9"):
            if re.search(rf"(?:^|[-_.]){question_id}(?:[-_.]|$)", lower):
                return cls._question_reflection_target_name(question_id)
        known = {
            "memory_extractor": "功能「记忆候选提取：从运行时事件中提取可治理记忆」",
            "reflection_generator": "功能「反思生成：生成反思与学习导向总结」",
            "learning_service": "模块「学习服务：维护学习记录、策略补丁与学习任务」",
            "zentex.learning.service": "模块「学习服务：维护学习记录、策略补丁与学习任务」",
            "zentex.memory.service": "模块「记忆服务：维护长期记忆、检索与治理」",
            "memory.consolidation": "模块「记忆合并：归并重复记忆并降低记忆噪音」",
            "reflection_clusterer": "功能「反思聚类：归并相似反思记录」",
            "semantic_clusterer": "功能「语义记忆聚类：按语义归并记忆记录」",
        }
        if lower in known:
            return known[lower]
        return ""

    @staticmethod
    def _human_readable_target_name(value: Any, *, prefix: str) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        lower = text.lower()
        if re.fullmatch(r"[a-z0-9_.:-]+", lower):
            return ""
        return f"{prefix}「{text}」"

    @staticmethod
    def _is_system_problem_improvement_text(value: Any, *, finding_type: str) -> bool:
        text = str(value or "").strip().lower()
        if len(text) < 8:
            return False
        if re.fullmatch(r"[a-z0-9_.:-]+", text):
            return False
        if "self-audit" in text or "no significant drift detected" in text:
            return False
        non_reflection_seed_patterns = (
            "reflection storage missing the real reflected object",
            "reflection storage lost the real reflected object",
            "internal reflection evidence missing owner attribution causes q4 input ambiguity",
            "external execution reflection missing owner attribution causes q4 business gap ambiguity",
            "internal system query seed",
            "ci reflection channel seed",
        )
        if any(pattern in text for pattern in non_reflection_seed_patterns):
            return False
        generic_noise_patterns = (
            r"^(?:internal cognitive|external connector|system)\s+problem\s+requires\s+attention\s+[0-9a-f]{8,}$",
            r"^(?:internal reflection|external execution|system)\s+improvement\s+should\s+be\s+prioritized\s+[0-9a-f]{8,}$",
        )
        if any(re.search(pattern, text) for pattern in generic_noise_patterns):
            return False
        if "反思已记录" in text:
            return False
        problem_markers = (
            "problem",
            "issue",
            "risk",
            "error",
            "failure",
            "failed",
            "missing",
            "gap",
            "defect",
            "bug",
            "regression",
            "timeout",
            "permission",
            "denied",
            "unavailable",
            "invalid",
            "inconsistent",
            "stale",
            "drift",
            "duplicate",
            "noise",
            "violation",
            "缺陷",
            "缺失",
            "缺少",
            "缺口",
            "问题",
            "风险",
            "错误",
            "异常",
            "失败",
            "故障",
            "不可用",
            "无效",
            "超时",
            "权限",
            "拒绝",
            "不一致",
            "重复",
            "噪音",
            "漂移",
            "膨胀",
            "违规",
            "无法",
            "不能",
        )
        improvement_markers = (
            "improvement",
            "improve",
            "should",
            "prioritized",
            "recommend",
            "optimize",
            "repair",
            "fix",
            "reduce",
            "upgrade",
            "governance",
            "补齐",
            "补充",
            "修复",
            "改进",
            "优化",
            "治理",
            "降低",
            "压缩",
            "提炼",
            "增强",
            "升级",
            "防御",
            "策略",
            "需要",
            "应当",
            "必须",
        )
        if finding_type == "problem":
            return any(marker in text for marker in problem_markers)
        if finding_type == "improvement":
            return any(marker in text for marker in (*problem_markers, *improvement_markers))
        return False

    @classmethod
    def _infer_problem_scope(
        cls,
        *,
        context: Dict[str, Any],
        metadata: Dict[str, Any],
        tags: List[Any],
        subject: Any,
        reflection_type: Any,
        source_field: str,
        content: Any,
        explicit_scope: Optional[Any] = None,
    ) -> str:
        for candidate in (
            explicit_scope,
            context.get("problem_scope"),
            context.get("issue_scope"),
            context.get("task_scope"),
            context.get("lane"),
            context.get("source_chain"),
            context.get("source_scope"),
            metadata.get("problem_scope"),
            metadata.get("issue_scope"),
            metadata.get("task_scope"),
            metadata.get("lane"),
            metadata.get("source_chain"),
            metadata.get("source_scope"),
        ):
            normalized = cls._scope_from_text(candidate)
            if normalized:
                return normalized

        haystack = " ".join(
            str(value or "")
            for value in (
                source_field,
                content,
                subject,
                reflection_type,
                json.dumps(tags, ensure_ascii=False),
                json.dumps(metadata, ensure_ascii=False, default=str),
                json.dumps(context, ensure_ascii=False, default=str),
            )
        ).lower()
        external_markers = (
            "external",
            "外部",
            "cli",
            "mcp",
            "agent",
            "connector",
            "browser",
            "http",
            "api",
            "network",
            "execution",
            "shell",
            "terminal",
            "filesystem",
            "file write",
            "github",
            "notion",
            "reddit",
        )
        internal_markers = (
            "internal",
            "内部",
            "cognitive",
            "认知",
            "memory",
            "记忆",
            "reflection",
            "反思",
            "learning",
            "学习",
            "strategy_patch",
            "策略补丁",
            "self_evolution",
            "pure_cognitive",
        )
        if any(marker in haystack for marker in external_markers):
            return "external"
        if any(marker in haystack for marker in internal_markers):
            return "internal"
        return "unknown"

    @staticmethod
    def _scope_from_text(value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip().lower()
        if not text:
            return None
        if any(marker in text for marker in ("external", "外部", "execution", "external_q", "external_")):
            return "external"
        if any(marker in text for marker in ("internal", "内部", "cognitive", "internal_q", "internal_")):
            return "internal"
        return None
    
    # ===== 辅助方法 =====
    
    def _row_to_reflection(self, row: Any) -> ReflectionRecord:
        """将数据库行转换为 ReflectionRecord 对象"""
        return ReflectionRecord(
            reflection_id=row['reflection_id'],
            trace_id=row['trace_id'],
            audit_id=row['audit_id'] or None,
            session_id=row['session_id'],
            reflection_type=ReflectionType(row['reflection_type']),
            depth=row['depth'],  # 已是枚举字符串
            quality=row['quality'],
            trigger=ReflectionTrigger(row['trigger']),
            created_at=datetime.fromisoformat(row['created_at']),
            updated_at=datetime.fromisoformat(row['updated_at']),
            reflection_timestamp=datetime.fromisoformat(row['reflection_timestamp']),
            subject=row['subject'],
            context=json.loads(row['context']) if row['context'] else {},
            summary=row['summary'],
            confidence=row['confidence'],
            impact_score=row['impact_score'],
            actionability=row['actionability'],
            related_decisions=json.loads(row['related_decisions']) if row['related_decisions'] else [],
            related_actions=json.loads(row['related_actions']) if row['related_actions'] else [],
            related_outcomes=json.loads(row['related_outcomes']) if row['related_outcomes'] else [],
            tags=json.loads(row['tags']) if row['tags'] else [],
            metadata=json.loads(row['metadata']) if row['metadata'] else {},
            governance_status=row['governance_status'],
            suspect_reason=row["suspect_reason"] if "suspect_reason" in row.keys() else None,
            verified_at=datetime.fromisoformat(row['verified_at']) if row['verified_at'] else None,
            verified_by=row['verified_by'],
            reflection_list=[]  # TODO: 反序列化 reflection_list
        )
    
    # ===== 统计信息 =====
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取反思统计信息"""
        try:
            count_query = "SELECT COUNT(*) as count FROM reflections"
            count_row = self.db.execute_query(count_query)
            total = count_row['count'] if count_row else 0
            
            avg_quality_query = "SELECT AVG(CAST(quality AS REAL)) as avg_quality FROM reflections"
            avg_quality_row = self.db.execute_query(avg_quality_query)
            avg_quality = avg_quality_row['avg_quality'] if avg_quality_row else 0.0
            
            return {
                'total_reflections': total,
                'average_quality': avg_quality,
                'last_updated': datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to calculate statistics: {e}")
            return {}


def get_reflection_dao(db_path: Optional[str] = None) -> ReflectionDAO:
    """获取反思 DAO 实例"""
    if db_path is None:
        from zentex.common.storage_paths import get_storage_paths

        db_path = str(get_storage_paths().core_db)
    db = DatabaseConnection(db_path)
    cache = LRUCache(max_size=500, ttl_seconds=300)
    return ReflectionDAO(db, cache)
