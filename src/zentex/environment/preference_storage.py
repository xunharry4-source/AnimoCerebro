"""
Alignment - 用户偏好辨析与意图对齐 - 持久化存储层

提供 SQLite 后端存储用户偏好、意图歧义案例、异常候选等数据。
"""

import hashlib
import json
import math
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from zentex.common.storage_paths import get_storage_paths

from .preference_models import (
    AnomalyCandidate,
    AnomalyType,
    AttackSample,
    ConfirmationStatus,
    ExtremeSignalRecord,
    IntentAmbiguityCase,
    PreferenceCandidate,
    PreferenceStatus,
    RiskLevel,
    UserPreference,
)


class PreferenceStore:
    """
    偏好存储管理器
    
    使用 SQLite 存储用户偏好、意图歧义案例、异常候选等数据，
    支持结构化检索和时间衰减计算。
    """

    def __init__(self, db_path: Optional[Path] = None):
        """
        初始化存储
        
        Args:
            db_path: 数据库文件路径，默认为配置文件中的 app_data_dir/preference_store.db
        """
        if db_path is None:
            db_path = get_storage_paths().app_data_dir / "preference_store.db"
        
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()

    def _get_connection(self) -> sqlite3.Connection:
        """获取数据库连接"""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        # 启用外键支持
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_database(self):
        """初始化数据库表结构"""
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # 用户偏好表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_preferences (
                    preference_id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    confirmed_at TIMESTAMP NOT NULL,
                    source TEXT NOT NULL,
                    applicable_scope TEXT NOT NULL,
                    can_override_safety_redline BOOLEAN NOT NULL DEFAULT 0,
                    confidence REAL NOT NULL DEFAULT 1.0,
                    status TEXT NOT NULL DEFAULT 'confirmed',
                    expires_at TIMESTAMP,
                    metadata TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 意图歧义案例表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS intent_ambiguity_cases (
                    case_id TEXT PRIMARY KEY,
                    anomaly_description TEXT NOT NULL,
                    preference_hypothesis TEXT,
                    confirmation_status TEXT NOT NULL DEFAULT 'unconfirmed',
                    created_at TIMESTAMP NOT NULL,
                    resolved_at TIMESTAMP,
                    resolution_action TEXT,
                    evidence_refs TEXT,
                    risk_level TEXT NOT NULL DEFAULT 'medium',
                    related_anomaly_id TEXT,
                    user_feedback TEXT,
                    metadata TEXT,
                    FOREIGN KEY (related_anomaly_id) REFERENCES anomaly_candidates(candidate_id)
                )
            """)

            # 异常候选表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS anomaly_candidates (
                    candidate_id TEXT PRIMARY KEY,
                    detected_state TEXT NOT NULL,
                    anomaly_type TEXT NOT NULL,
                    severity REAL NOT NULL DEFAULT 0.5,
                    detection_source TEXT NOT NULL,
                    timestamp TIMESTAMP NOT NULL,
                    context_snapshot TEXT,
                    suggested_action TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 攻击样本表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS attack_samples (
                    sample_id TEXT PRIMARY KEY,
                    signal_content_hash TEXT NOT NULL,
                    attack_type TEXT NOT NULL,
                    risk_indicators TEXT,
                    confidence REAL NOT NULL,
                    marked_at TIMESTAMP NOT NULL,
                    marked_by TEXT,
                    pattern_signature TEXT,
                    metadata TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 创建索引
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_preferences_scope 
                ON user_preferences(applicable_scope)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_preferences_status 
                ON user_preferences(status)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_preferences_source 
                ON user_preferences(source)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_cases_status 
                ON intent_ambiguity_cases(confirmation_status)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_cases_risk 
                ON intent_ambiguity_cases(risk_level)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_cases_created 
                ON intent_ambiguity_cases(created_at)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_anomalies_type 
                ON anomaly_candidates(anomaly_type)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_anomalies_timestamp 
                ON anomaly_candidates(timestamp)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_attacks_type 
                ON attack_samples(attack_type)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_attacks_marked 
                ON attack_samples(marked_at)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_attacks_signature 
                ON attack_samples(pattern_signature)
            """)

            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    # ===== UserPreference 操作 =====

    async def save_preference(self, preference: UserPreference) -> None:
        """保存偏好"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT OR REPLACE INTO user_preferences 
                (preference_id, content, confirmed_at, source, applicable_scope,
                 can_override_safety_redline, confidence, status, expires_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                preference.preference_id,
                preference.content,
                preference.confirmed_at.isoformat(),
                preference.source,
                json.dumps(preference.applicable_scope),
                preference.can_override_safety_redline,
                preference.confidence,
                preference.status.value,
                preference.expires_at.isoformat() if preference.expires_at else None,
                json.dumps(preference.metadata) if preference.metadata else None
            ))
            
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    async def get_preference(self, preference_id: str) -> Optional[UserPreference]:
        """获取偏好"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT * FROM user_preferences WHERE preference_id = ?
            """, (preference_id,))
            
            row = cursor.fetchone()
            if row:
                return self._row_to_preference(row)
            return None
        finally:
            conn.close()

    async def query_preferences_by_scope(
        self,
        scope_filter: Dict[str, Any]
    ) -> List[UserPreference]:
        """按适用范围查询偏好"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # 简单实现：查询所有活跃偏好，然后在内存中过滤
            # 生产环境应使用 JSON 查询优化
            cursor.execute("""
                SELECT * FROM user_preferences 
                WHERE status = 'confirmed'
                AND (expires_at IS NULL OR expires_at > ?)
            """, (datetime.utcnow().isoformat(),))
            
            rows = cursor.fetchall()
            preferences = [self._row_to_preference(row) for row in rows]
            
            # 内存中过滤（简化实现）
            filtered = []
            for pref in preferences:
                if self._scope_matches(pref.applicable_scope, scope_filter):
                    filtered.append(pref)
            
            return filtered
        finally:
            conn.close()

    def _scope_matches(self, pref_scope: Dict[str, Any], filter_scope: Dict[str, Any]) -> bool:
        """检查偏好适用范围是否匹配过滤器"""
        # 简化实现：检查 domains 和 paths 是否有交集
        pref_domains = set(pref_scope.get("domains", []))
        filter_domains = set(filter_scope.get("domains", []))
        
        if filter_domains and not pref_domains.intersection(filter_domains):
            return False
        
        pref_paths = set(pref_scope.get("paths", []))
        filter_paths = set(filter_scope.get("paths", []))
        
        if filter_paths and not pref_paths.intersection(filter_paths):
            return False
        
        return True

    async def update_preference_status(
        self,
        preference_id: str,
        new_status: PreferenceStatus,
        reason: Optional[str] = None
    ) -> None:
        """更新偏好状态"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            metadata_update = {}
            if reason:
                # 获取现有 metadata
                cursor.execute("SELECT metadata FROM user_preferences WHERE preference_id = ?", (preference_id,))
                row = cursor.fetchone()
                if row and row["metadata"]:
                    metadata_update = json.loads(row["metadata"])
                metadata_update["status_change_reason"] = reason
                metadata_update["status_changed_at"] = datetime.utcnow().isoformat()
            
            cursor.execute("""
                UPDATE user_preferences 
                SET status = ?, metadata = ?, updated_at = CURRENT_TIMESTAMP
                WHERE preference_id = ?
            """, (
                new_status.value,
                json.dumps(metadata_update),
                preference_id
            ))
            
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    # ===== IntentAmbiguityCase 操作 =====

    async def save_ambiguity_case(self, case: IntentAmbiguityCase) -> None:
        """保存意图歧义案例"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT OR REPLACE INTO intent_ambiguity_cases 
                (case_id, anomaly_description, preference_hypothesis, confirmation_status,
                 created_at, resolved_at, resolution_action, evidence_refs, risk_level,
                 related_anomaly_id, user_feedback, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                case.case_id,
                case.anomaly_description,
                case.preference_hypothesis,
                case.confirmation_status.value,
                case.created_at.isoformat(),
                case.resolved_at.isoformat() if case.resolved_at else None,
                case.resolution_action,
                json.dumps(case.evidence_refs),
                case.risk_level.value,
                case.related_anomaly_id,
                case.user_feedback,
                json.dumps(case.metadata) if case.metadata else None
            ))
            
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    async def resolve_ambiguity_case(
        self,
        case_id: str,
        resolution_action: str,
        user_feedback: Optional[str] = None
    ) -> None:
        """解决意图歧义案例"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                UPDATE intent_ambiguity_cases 
                SET confirmation_status = ?, resolved_at = ?, resolution_action = ?, user_feedback = ?
                WHERE case_id = ?
            """, (
                ConfirmationStatus.CONFIRMED_AS_PREFERENCE.value if resolution_action == "confirmed_as_preference"
                else ConfirmationStatus.CONFIRMED_AS_ANOMALY.value,
                datetime.utcnow().isoformat(),
                resolution_action,
                user_feedback,
                case_id
            ))
            
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    async def get_unresolved_cases(
        self,
        risk_level_filter: Optional[RiskLevel] = None,
        limit: int = 50
    ) -> List[IntentAmbiguityCase]:
        """获取未解决的案例"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            if risk_level_filter:
                cursor.execute("""
                    SELECT * FROM intent_ambiguity_cases 
                    WHERE confirmation_status = 'unconfirmed'
                    AND risk_level = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                """, (risk_level_filter.value, limit))
            else:
                cursor.execute("""
                    SELECT * FROM intent_ambiguity_cases 
                    WHERE confirmation_status = 'unconfirmed'
                    ORDER BY created_at DESC
                    LIMIT ?
                """, (limit,))
            
            rows = cursor.fetchall()
            return [self._row_to_ambiguity_case(row) for row in rows]
        finally:
            conn.close()

    # ===== AnomalyCandidate 操作 =====

    async def save_anomaly_candidate(self, anomaly: AnomalyCandidate) -> None:
        """保存异常候选"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT OR REPLACE INTO anomaly_candidates 
                (candidate_id, detected_state, anomaly_type, severity, detection_source,
                 timestamp, context_snapshot, suggested_action)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                anomaly.candidate_id,
                json.dumps(anomaly.detected_state),
                anomaly.anomaly_type.value,
                anomaly.severity,
                anomaly.detection_source,
                anomaly.timestamp.isoformat(),
                json.dumps(anomaly.context_snapshot) if anomaly.context_snapshot else None,
                anomaly.suggested_action
            ))
            
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    # ===== AttackSample 操作 =====

    async def save_attack_sample(self, sample: AttackSample) -> str:
        """保存攻击样本，返回 sample_id"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT OR REPLACE INTO attack_samples 
                (sample_id, signal_content_hash, attack_type, risk_indicators,
                 confidence, marked_at, marked_by, pattern_signature, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                sample.sample_id,
                sample.signal_content_hash,
                sample.attack_type,
                json.dumps(sample.risk_indicators),
                sample.confidence,
                sample.marked_at.isoformat(),
                sample.marked_by,
                sample.pattern_signature,
                json.dumps(sample.metadata) if sample.metadata else None
            ))
            
            conn.commit()
            return sample.sample_id
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    async def find_similar_attack(
        self,
        signal_content: str,
        similarity_threshold: float = 0.85
    ) -> Optional[AttackSample]:
        """查找相似攻击"""
        # 计算信号内容的哈希作为简单签名
        signal_hash = hashlib.sha256(signal_content.encode()).hexdigest()
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        try:
            # 简化实现：精确匹配哈希
            # 生产环境应使用更复杂的模式匹配算法
            cursor.execute("""
                SELECT * FROM attack_samples 
                WHERE pattern_signature = ?
            """, (signal_hash,))
            
            row = cursor.fetchone()
            if row:
                sample = self._row_to_attack_sample(row)
                # 这里应该计算实际相似度，简化为完全匹配时相似度为 1.0
                if 1.0 >= similarity_threshold:
                    return sample
            
            return None
        finally:
            conn.close()

    # ===== 工具方法 =====

    def apply_time_decay(
        self,
        base_confidence: float,
        age_days: int,
        decay_rate: float = 0.05
    ) -> float:
        """
        应用时间衰减
        
        Args:
            base_confidence: 基础置信度
            age_days: 年龄（天）
            decay_rate: 衰减率（每天）
            
        Returns:
            衰减后的置信度
        """
        decay_factor = math.exp(-decay_rate * age_days)
        return base_confidence * decay_factor

    def _row_to_preference(self, row: sqlite3.Row) -> UserPreference:
        """将数据库行转换为 UserPreference 对象"""
        return UserPreference(
            preference_id=row["preference_id"],
            content=row["content"],
            confirmed_at=datetime.fromisoformat(row["confirmed_at"]),
            source=row["source"],
            applicable_scope=json.loads(row["applicable_scope"]),
            can_override_safety_redline=bool(row["can_override_safety_redline"]),
            confidence=row["confidence"],
            status=PreferenceStatus(row["status"]),
            expires_at=datetime.fromisoformat(row["expires_at"]) if row["expires_at"] else None,
            metadata=json.loads(row["metadata"]) if row["metadata"] else {}
        )

    def _row_to_ambiguity_case(self, row: sqlite3.Row) -> IntentAmbiguityCase:
        """将数据库行转换为 IntentAmbiguityCase 对象"""
        return IntentAmbiguityCase(
            case_id=row["case_id"],
            anomaly_description=row["anomaly_description"],
            preference_hypothesis=row["preference_hypothesis"],
            confirmation_status=ConfirmationStatus(row["confirmation_status"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            resolved_at=datetime.fromisoformat(row["resolved_at"]) if row["resolved_at"] else None,
            resolution_action=row["resolution_action"],
            evidence_refs=json.loads(row["evidence_refs"]) if row["evidence_refs"] else [],
            risk_level=RiskLevel(row["risk_level"]),
            related_anomaly_id=row["related_anomaly_id"],
            user_feedback=row["user_feedback"],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {}
        )

    async def list_attack_samples(
        self,
        attack_type_filter: Optional[str] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        limit: int = 50,
    ) -> List[AttackSample]:
        """Query attack samples from the database with optional filters.

        Args:
            attack_type_filter: If given, only return samples of this attack type.
            since:              If given, only return samples marked on or after this time.
            until:              If given, only return samples marked on or before this time.
            limit:              Maximum number of samples to return (most recent first).

        Returns:
            List of AttackSample objects ordered by marked_at DESC.
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            clauses: List[str] = []
            params: List[Any] = []

            if attack_type_filter:
                clauses.append("attack_type = ?")
                params.append(attack_type_filter)
            if since:
                clauses.append("marked_at >= ?")
                params.append(since.isoformat())
            if until:
                clauses.append("marked_at <= ?")
                params.append(until.isoformat())

            where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
            params.append(max(1, limit))
            cursor.execute(
                f"SELECT * FROM attack_samples {where} ORDER BY marked_at DESC LIMIT ?",  # noqa: S608
                params,
            )
            rows = cursor.fetchall()
            return [self._row_to_attack_sample(r) for r in rows]
        finally:
            conn.close()

    async def get_attack_statistics(self) -> Dict[str, Any]:
        """Return aggregate statistics over all stored attack samples."""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT COUNT(*) AS total FROM attack_samples")
            total: int = cursor.fetchone()["total"]

            cursor.execute(
                "SELECT attack_type, COUNT(*) AS cnt FROM attack_samples GROUP BY attack_type"
            )
            by_type = {row["attack_type"]: row["cnt"] for row in cursor.fetchall()}

            # Recent attacks in the last 24 h
            cursor.execute(
                "SELECT COUNT(*) AS cnt FROM attack_samples "
                "WHERE marked_at >= datetime('now', '-1 day')"
            )
            recent_24h: int = cursor.fetchone()["cnt"]

            # High-confidence samples (confidence >= 0.8)
            cursor.execute(
                "SELECT COUNT(*) AS cnt FROM attack_samples WHERE confidence >= 0.8"
            )
            high_confidence: int = cursor.fetchone()["cnt"]

            return {
                "total_samples": total,
                "by_type": by_type,
                "recent_attacks_24h": recent_24h,
                "high_confidence_samples": high_confidence,
            }
        finally:
            conn.close()

    def _row_to_attack_sample(self, row: sqlite3.Row) -> AttackSample:
        """将数据库行转换为 AttackSample 对象"""
        return AttackSample(
            sample_id=row["sample_id"],
            signal_content_hash=row["signal_content_hash"],
            attack_type=row["attack_type"],
            risk_indicators=json.loads(row["risk_indicators"]) if row["risk_indicators"] else [],
            confidence=row["confidence"],
            marked_at=datetime.fromisoformat(row["marked_at"]),
            marked_by=row["marked_by"],
            pattern_signature=row["pattern_signature"],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {}
        )
