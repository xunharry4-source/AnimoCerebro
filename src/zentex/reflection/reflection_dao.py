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
                    governance_status, verified_at, verified_by, reflection_list
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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

            if "reflection_type" in filters:
                query += " AND reflection_type = ?"
                params.append(filters["reflection_type"].value if hasattr(filters["reflection_type"], 'value') else filters["reflection_type"])

            if "governance_status" in filters:
                query += " AND governance_status = ?"
                params.append(filters["governance_status"].value if hasattr(filters["governance_status"], 'value') else filters["governance_status"])

            if "start_time" in filters:
                query += " AND created_at >= ?"
                params.append(filters["start_time"].isoformat())

            if "end_time" in filters:
                query += " AND created_at <= ?"
                params.append(filters["end_time"].isoformat())

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
