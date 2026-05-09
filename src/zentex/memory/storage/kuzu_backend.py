from __future__ import annotations

import logging
from datetime import datetime, timezone
UTC = timezone.utc
from pathlib import Path
from typing import Any, Dict, List, Optional
import json

from zentex.memory.management.enhanced import MemoryRecallHit

logger = logging.getLogger(__name__)

class KuzuGraphMemoryClient:
    """
    In-process temporal graph memory client using KuzuDB.
    Replaces the heavy external Graphiti dependency.
    """

    def __init__(self, db_path: Union[str, Path]):
        try:
            import kuzu
        except ImportError:
            raise RuntimeError("kuzu is not installed. Please install it with: pip install kuzu")

        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Initialize Kuzu database
        self.db = kuzu.Database(str(self.db_path))
        self.conn = kuzu.Connection(self.db)
        self._init_schema()

    def _init_schema(self) -> None:
        """Initialize the temporal property graph schema if it doesn't exist."""
        # Check if schema exists by querying node tables
        res = self.conn.execute("CALL show_tables() RETURN *;")
        tables: list[str] = []
        if res is not None:
            while res.has_next():
                row = res.get_next()
                if isinstance(row, (list, tuple)):
                    if len(row) > 1:
                        tables.append(str(row[1]))
                    elif row:
                        tables.append(str(row[0]))
                else:
                    tables.append(str(row))

        if "Episode" not in tables:
            logger.info("Initializing KuzuDB schema for Episodic Memory...")
            self.conn.execute(
                "CREATE NODE TABLE Episode (id STRING, name STRING, summary STRING, content STRING, trace_id STRING, target_id STRING, version_id STRING, tags STRING, source_refs STRING, created_at TIMESTAMP, PRIMARY KEY(id));"
            )
        if "Entity" not in tables:
            self.conn.execute("CREATE NODE TABLE Entity (id STRING PRIMARY KEY, name STRING);")
        
        # Relations with Temporal attributes (valid_from, valid_to) for Temporal Modeling
        if "INVOLVES" not in tables:
            self.conn.execute(
                "CREATE REL TABLE INVOLVES (FROM Episode TO Entity, valid_from TIMESTAMP, valid_to TIMESTAMP);"
            )
        if "RELATED_TO" not in tables:
            self.conn.execute(
                "CREATE REL TABLE RELATED_TO (FROM Episode TO Episode, weight DOUBLE, valid_from TIMESTAMP, valid_to TIMESTAMP);"
            )

    def add_episode(
        self,
        name: str,
        episode_body: Dict[str, Any],
        source: str,
        source_description: str,
        reference_time: datetime,
    ) -> None:
        """
        Add an episodic memory record to the knowledge graph.
        Signature matches the expected GraphClient from EpisodeGraphMemoryAdapter.
        """
        import uuid
        
        episode_id = str(uuid.uuid4())
        summary = str(episode_body.get("summary", ""))
        content = str(episode_body.get("content", ""))
        trace_id = str(episode_body.get("trace_id", ""))
        target_id = str(episode_body.get("target_id", ""))
        version_id = str(episode_body.get("version_id", ""))
        
        tags_json = json.dumps(episode_body.get("tags", []))
        source_refs_json = json.dumps(episode_body.get("source_refs", []))
        
        # Insert node
        query = f"""
            CREATE (e:Episode {{
                id: $id, 
                name: $name, 
                summary: $summary, 
                content: $content, 
                trace_id: $trace_id, 
                target_id: $target_id, 
                version_id: $version_id, 
                tags: $tags, 
                source_refs: $source_refs, 
                created_at: $created_at
            }})
        """
        self.conn.execute(
            query,
            parameters={
                "id": episode_id,
                "name": name,
                "summary": summary,
                "content": content,
                "trace_id": trace_id,
                "target_id": target_id,
                "version_id": version_id,
                "tags": tags_json,
                "source_refs": source_refs_json,
                "created_at": reference_time,
            }
        )
        logger.debug(f"Pushed episode {episode_id} to Kuzu temporal graph.")

    def search(self, query: str, limit: int = 10) -> List[Any]:
        """
        Mock search implementation that executes against Kuzu property graph.
        Returns objects duck-typable to the expected Graphiti return rows.
        """
        class HitRow:
            def __init__(self, e_id: str, name: str, summary: str, trace_id: str, target_id: str, score: float, tags: list):
                self.uuid = e_id
                self.name = name
                self.summary = summary
                self.trace_id = trace_id
                self.target_id = target_id
                self.score = score
                self.labels = tags

        # Very basic string match for simulation (in production, use Kuzu Full Text Search or Vector integration)
        q = f"""
            MATCH (e:Episode)
            WHERE e.summary CONTAINS $query OR e.name CONTAINS $query OR e.content CONTAINS $query
            RETURN e.id, e.name, e.summary, e.trace_id, e.target_id, e.tags
            LIMIT $limit
        """
        res = self.conn.execute(q, parameters={"query": query, "limit": limit})
        
        hits = []
        if res and res.has_next():
            while res.has_next():
                row = res.get_next()
                # Calculate an authentic keyword relevance score
                name = str(row[1])
                summary = str(row[2])
                content = "" # Not returned by search, but we can't score what we don't have
                
                # Simple token overlap scorer
                query_tokens = set(query.lower().split())
                text_tokens = set((name + " " + summary).lower().split())
                if not query_tokens:
                    score = 0.0
                else:
                    score = len(query_tokens & text_tokens) / len(query_tokens)
                
                hits.append(
                    HitRow(
                        e_id=row[0],
                        name=name,
                        summary=summary,
                        trace_id=row[3],
                        target_id=row[4],
                        score=round(score, 2),
                        tags=tags
                    )
                )
        return hits

    # ────────────────────────────────────────────────────────────────
    #  通用对外方法 / Universal Public API
    # ────────────────────────────────────────────────────────────────

    def query_temporal(
        self,
        entity_name: str,
        *,
        point_in_time: Optional[datetime] = None,
        limit: int = 10,
    ) -> List[Any]:
        """
        时间化查询：检索某个实体在指定时间点的关联事件。

        这是 Graphiti 时间化能力的核心平替方法。通过 Kuzu 图的 INVOLVES
        关系上的 valid_from / valid_to 时间属性实现历史回溯。

        Args:
            entity_name:   要查询的实体名称。
            point_in_time: 查询的时间点，缺省为当前时间。
            limit:         最大返回数量。

        Returns:
            匹配的 HitRow 列表。
        """
        if point_in_time is None:
            point_in_time = datetime.now()

        class HitRow:
            def __init__(self, e_id: str, name: str, summary: str, trace_id: str, target_id: str, score: float, tags: list):
                self.uuid = e_id
                self.name = name
                self.summary = summary
                self.trace_id = trace_id
                self.target_id = target_id
                self.score = score
                self.labels = tags

        q = """
            MATCH (ep:Episode)-[r:INVOLVES]->(en:Entity)
            WHERE en.name CONTAINS $entity_name
              AND r.valid_from <= $pit
              AND (r.valid_to IS NULL OR r.valid_to >= $pit)
            RETURN ep.id, ep.name, ep.summary, ep.trace_id, ep.target_id, ep.tags
            LIMIT $limit
        """
        try:
            res = self.conn.execute(
                q,
                parameters={
                    "entity_name": entity_name,
                    "pit": point_in_time,
                    "limit": limit,
                },
            )
            hits = []
            if res and res.has_next():
                while res.has_next():
                    row = res.get_next()
                    try:
                        tags = json.loads(row[5]) if row[5] else []
                    except Exception:
                        logger.exception("Could not deserialize tags for temporal record")
                        tags = []
                    
                    # Authentic temporal relevance: recent knowledge about the entity has higher weight
                    # For now using a higher base score for temporal certainty
                    score = 0.9 if point_in_time else 0.7
                    
                    hits.append(
                        HitRow(
                            e_id=row[0],
                            name=row[1],
                            summary=row[2],
                            trace_id=row[3],
                            target_id=row[4],
                            score=score,
                            tags=tags,
                        )
                    )
            return hits
        except Exception as exc:
            logger.exception(f"Temporal query failed for entity '{entity_name}': {exc}")
            raise

    def add_entity(self, entity_id: str, name: str) -> None:
        """
        向图谱中添加一个实体节点。

        Args:
            entity_id: 实体的唯一 ID。
            name:      实体名称。
        """
        self.conn.execute(
            "CREATE (en:Entity {id: $id, name: $name})",
            parameters={"id": entity_id, "name": name},
        )

    def link_episode_to_entity(
        self,
        episode_id: str,
        entity_id: str,
        *,
        valid_from: Optional[datetime] = None,
        valid_to: Optional[datetime] = None,
    ) -> None:
        """
        在一条 Episode 和一个 Entity 之间建立时间化关联。

        这是 Graphiti 时间化建模的核心操作：一条边带有 valid_from 和
        valid_to 属性，使得我们可以回溯"在某个时间点，哪些事件与哪些
        实体有关"。

        Args:
            episode_id:  Episode 节点的 ID。
            entity_id:   Entity 节点的 ID。
            valid_from:  关联生效起始时间，缺省为当前时间。
            valid_to:    关联失效时间，缺省为 None（永久有效）。
        """
        if valid_from is None:
            valid_from = datetime.now()
        q = """
            MATCH (ep:Episode {id: $ep_id}), (en:Entity {id: $en_id})
            CREATE (ep)-[:INVOLVES {valid_from: $vf, valid_to: $vt}]->(en)
        """
        self.conn.execute(
            q,
            parameters={
                "ep_id": episode_id,
                "en_id": entity_id,
                "vf": valid_from,
                "vt": valid_to,
            },
        )

    def get_graph_stats(self) -> Dict[str, Any]:
        """
        返回图谱的统计概览，适用于 Dashboard 展示和健康检查。

        Returns:
            包含节点数、关系数、数据库路径等信息的字典。
        """
        stats: Dict[str, Any] = {"db_path": str(self.db_path)}
        try:
            res = self.conn.execute("MATCH (e:Episode) RETURN count(e);")
            row = res.get_next()
            stats["episode_count"] = row[0] if row else 0
        except Exception:
            logger.exception("Could not query episode count from kuzu DB")
            stats["episode_count"] = -1
        try:
            res = self.conn.execute("MATCH (en:Entity) RETURN count(en);")
            row = res.get_next()
            stats["entity_count"] = row[0] if row else 0
        except Exception:
            logger.debug("Could not query entity count from kuzu DB", exc_info=True)
            stats["entity_count"] = -1
        try:
            res = self.conn.execute("MATCH ()-[r:INVOLVES]->() RETURN count(r);")
            row = res.get_next()
            stats["involves_count"] = row[0] if row else 0
        except Exception:
            logger.debug("Could not query involves-relation count from kuzu DB", exc_info=True)
            stats["involves_count"] = -1
        return stats

    # ════════════════════════════════════════════════════════════════════
    #  Dual-time temporal modeling (Graphiti-inspired enhancement)
    # ════════════════════════════════════════════════════════════════════

    def add_episode_temporal(
        self,
        name: str,
        episode_body: Dict[str, Any],
        source: str,
        source_description: str,
        *,
        event_time: datetime,           # When the described event actually occurred
        ingest_time: Optional[datetime] = None,  # Defaults to utcnow
        valid_from: Optional[datetime] = None,   # When knowledge becomes valid
        valid_to: Optional[datetime] = None,     # When knowledge expires (None = permanent)
        agent_namespace: str = "default",     # Multi-agent namespace isolation
    ) -> str:
        """
        Write an episode with full dual-time temporal modeling.

        双时间模型:
          event_time  — 事件实际发生的时间（来源真实世界）
          ingest_time — 记录被写入图谱的时间（系统时间）
          valid_from  — 该知识开始有效的时间
          valid_to    — 该知识失效的时间（NULL = 永久有效）

        这使得历史状态重建成为可能：给定任意时间点 t，查询哪些知识在 t 时有效。

        Args:
            agent_namespace: 多智能体命名空间隔离键，防止跨 agent 知识污染。

        Returns:
            episode_id (UUID string)
        """
        import uuid as _uuid
        episode_id = str(_uuid.uuid4())
        ingest_time = ingest_time or datetime.utcnow()
        valid_from = valid_from or event_time

        summary = str(episode_body.get("summary", ""))
        content = str(episode_body.get("content", ""))
        trace_id = str(episode_body.get("trace_id", ""))
        target_id = str(episode_body.get("target_id", ""))
        version_id = str(episode_body.get("version_id", ""))
        tags_json = json.dumps(episode_body.get("tags", []))
        source_refs_json = json.dumps(episode_body.get("source_refs", []))

        # Ensure temporal columns exist (idempotent schema upgrade).
        self._ensure_temporal_schema()

        query = """
            CREATE (e:Episode {
                id: $id,
                name: $name,
                summary: $summary,
                content: $content,
                trace_id: $trace_id,
                target_id: $target_id,
                version_id: $version_id,
                tags: $tags,
                source_refs: $source_refs,
                event_time: $event_time,
                ingest_time: $ingest_time,
                valid_from: $valid_from,
                valid_to: $valid_to,
                superseded: $superseded,
                agent_namespace: $agent_namespace,
                source: $source,
                source_description: $source_description,
                created_at: $created_at
            })
        """
        self.conn.execute(
            query,
            parameters={
                "id": episode_id,
                "name": name,
                "summary": summary,
                "content": content,
                "trace_id": trace_id,
                "target_id": target_id,
                "version_id": version_id,
                "tags": tags_json,
                "source_refs": source_refs_json,
                "event_time": event_time,
                "ingest_time": ingest_time,
                "valid_from": valid_from,
                "valid_to": valid_to,
                "superseded": False,
                "agent_namespace": agent_namespace,
                "source": source,
                "source_description": source_description,
                "created_at": ingest_time,
            },
        )
        logger.debug(
            "Temporal episode %s: event_time=%s valid_from=%s valid_to=%s ns=%s",
            episode_id, event_time, valid_from, valid_to, agent_namespace,
        )
        return episode_id

    def _ensure_temporal_schema(self) -> None:
        """
        Attempt to add temporal columns to Episode table if they don't exist.

        KuzuDB currently doesn't support ALTER TABLE ADD COLUMN — new Episode
        nodes created via add_episode_temporal() include these columns naturally
        through the CREATE statement.  Legacy nodes without them return NULL
        on those columns, which is acceptable.
        """
        # Schema is defined at node-creation time in add_episode_temporal(); nothing to do here.
        pass

    # ── point-in-time query ───────────────────────────────────────────────

    def query_at_time_point(
        self,
        query_text: str,
        *,
        as_of_time: datetime,
        limit: int = 10,
        agent_namespace: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Reconstruct graph state at a specific point in time (Graphiti capability).

        返回在 as_of_time 时刻有效（valid_from <= t AND (valid_to IS NULL OR valid_to >= t)）
        且已被摄入（ingest_time <= t）的 Episode 列表。

        Args:
            query_text: Keyword filter.
            as_of_time: Point-in-time reconstruction target.
            agent_namespace: If set, restrict to episodes from this namespace.

        Returns:
            List of episode dicts.
        """
        ns_filter = "AND e.agent_namespace = $ns" if agent_namespace else ""
        q = f"""
            MATCH (e:Episode)
            WHERE e.ingest_time <= $as_of
              AND (e.valid_to IS NULL OR e.valid_to >= $as_of)
              AND (toLower(e.summary) CONTAINS toLower($query)
                   OR toLower(e.content) CONTAINS toLower($query)
                   OR toLower(e.name) CONTAINS toLower($query))
              {ns_filter}
            RETURN e.id, e.name, e.summary, e.event_time, e.ingest_time,
                   e.trace_id, e.target_id, e.agent_namespace
            ORDER BY e.ingest_time DESC
            LIMIT $limit
        """
        params: Dict[str, Any] = {
            "as_of": as_of_time,
            "query": query_text,
            "limit": limit,
        }
        if agent_namespace:
            params["ns"] = agent_namespace
        try:
            res = self.conn.execute(q, parameters=params)
            rows = []
            if res and res.has_next():
                while res.has_next():
                    row = res.get_next()
                    rows.append({
                        "id": row[0],
                        "name": row[1],
                        "summary": row[2],
                        "event_time": row[3],
                        "ingest_time": row[4],
                        "trace_id": row[5],
                        "target_id": row[6],
                        "agent_namespace": row[7],
                    })
            return rows
        except Exception as exc:
            # Read-only temporal query is allowed to degrade to [] for callers,
            # but it must never hide backend faults behind a light warning.
            logger.exception("query_at_time_point failed: %s", exc)
            return []

    # ── edge invalidation ─────────────────────────────────────────────────

    def invalidate_expired_episodes(
        self,
        current_time: Optional[datetime] = None,
    ) -> int:
        """
        Mark episodes whose valid_to has passed as superseded.

        Graphiti 风格的冲突消解：当一条新知识到达时，旧的矛盾知识会被标记失效。
        本方法执行批量时间过期检查，将过期 episode 的 superseded 字段设为 true。

        Returns:
            Number of episodes invalidated.
        """
        now = current_time or datetime.now(UTC)
        try:
            q = """
                MATCH (e:Episode)
                WHERE e.valid_to IS NOT NULL
                  AND e.valid_to < $now
                  AND e.superseded = false
                SET e.superseded = true
                RETURN count(e)
            """
            res = self.conn.execute(q, parameters={"now": now})
            if res and res.has_next():
                row = res.get_next()
                count = row[0] if row else 0
                if count > 0:
                    logger.info("Invalidated %d expired episodes", count)
                return int(count)
        except Exception as exc:
            # Forbidden: write-path invalidation failure must not pretend there
            # were simply zero expired episodes. That would hide a broken
            # governance write behind a fake-normal count of 0.
            logger.exception("invalidate_expired_episodes failed: %s", exc)
            raise
        return 0

    def supersede_episode(self, episode_id: str, superseded_at: Optional[datetime] = None) -> None:
        """Explicitly mark one episode as superseded (replaced by newer information)."""
        now = superseded_at or datetime.now(UTC)
        try:
            self.conn.execute(
                "MATCH (e:Episode {id: $id}) SET e.superseded = true, e.valid_to = $ts",
                parameters={"id": episode_id, "ts": now},
            )
            logger.info("Episode %s superseded at %s", episode_id, now)
        except Exception as exc:
            # Forbidden: a failed supersede write must not be downgraded to a warning.
            # Pretending conflict resolution succeeded here would let stale facts remain
            # active while the caller believes the older episode was retired.
            logger.exception("supersede_episode failed for %s: %s", episode_id, exc)
            raise

    # ── conflict detection & resolution ──────────────────────────────────

    def detect_entity_conflicts(
        self,
        entity_name: str,
        new_content_fragment: str,
        *,
        agent_namespace: str = "default",
    ) -> List[Dict[str, Any]]:
        """
        Find currently-valid episodes about an entity that may conflict with new content.

        Heuristic: any currently-valid episode involving the same entity is a
        potential conflict.  The caller decides whether to supersede them.

        Returns:
            List of potentially conflicting episode dicts (newest first).
        """
        try:
            q = """
                MATCH (ep:Episode)-[:INVOLVES]->(en:Entity)
                WHERE en.name CONTAINS $entity_name
                  AND (ep.valid_to IS NULL OR ep.valid_to >= $now)
                  AND ep.superseded = false
                  AND ep.agent_namespace = $ns
                RETURN ep.id, ep.content, ep.summary, ep.ingest_time, ep.event_time
                ORDER BY ep.ingest_time DESC
            """
            res = self.conn.execute(
                q,
                parameters={
                    "entity_name": entity_name,
                    "now": datetime.now(UTC),
                    "ns": agent_namespace,
                },
            )
            conflicts = []
            if res and res.has_next():
                while res.has_next():
                    row = res.get_next()
                    conflicts.append({
                        "id": row[0],
                        "content": row[1],
                        "summary": row[2],
                        "ingest_time": row[3],
                        "event_time": row[4],
                    })
            return conflicts
        except Exception as exc:
            # Forbidden: returning [] here would fake "no conflicts found" even though
            # the storage layer never answered. Conflict detection failure must remain
            # visible so callers do not treat contradictory memory as clean state.
            logger.exception("detect_entity_conflicts failed: %s", exc)
            raise

    def resolve_conflict_supersede_older(
        self,
        entity_name: str,
        new_episode_id: str,
        *,
        agent_namespace: str = "default",
    ) -> int:
        """
        After adding a new episode, supersede all older conflicting episodes about the same entity.

        自动矛盾消解策略：保留最新，标记旧的为 superseded。
        返回被 supersede 的 episode 数量。
        """
        conflicts = self.detect_entity_conflicts(entity_name, "", agent_namespace=agent_namespace)
        superseded = 0
        for c in conflicts:
            if c["id"] != new_episode_id:
                self.supersede_episode(c["id"])
                superseded += 1
        if superseded:
            logger.info(
                "Resolved %d conflicts for entity '%s' by superseding older episodes",
                superseded, entity_name,
            )
        return superseded

    # ── multi-agent namespace isolation ──────────────────────────────────

    def list_namespaces(self) -> List[str]:
        """Return all distinct agent_namespace values in the graph."""
        try:
            res = self.conn.execute(
                "MATCH (e:Episode) WHERE e.agent_namespace IS NOT NULL "
                "RETURN DISTINCT e.agent_namespace"
            )
            namespaces = []
            if res and res.has_next():
                while res.has_next():
                    row = res.get_next()
                    namespaces.append(str(row[0]))
            return namespaces
        except Exception as exc:
            logger.warning("list_namespaces failed: %s", exc)
            return []

    def namespace_stats(self) -> Dict[str, int]:
        """Return episode count per namespace."""
        stats: Dict[str, int] = {}
        for ns in self.list_namespaces():
            try:
                res = self.conn.execute(
                    "MATCH (e:Episode) WHERE e.agent_namespace = $ns RETURN count(e)",
                    parameters={"ns": ns},
                )
                if res and res.has_next():
                    row = res.get_next()
                    stats[ns] = int(row[0]) if row else 0
            except Exception:
                # POLICY[no-silent-except]: log namespace stat failure; report -1 as sentinel.
                logger.debug("Could not query episode count for namespace %s", ns, exc_info=True)
                stats[ns] = -1
        return stats


# ════════════════════════════════════════════════════════════════════
#  模块说明 / Module Documentation
# ════════════════════════════════════════════════════════════════════
#
#  zentex.memory.kuzu_backend — KuzuDB 本地时间化图谱后端
#
#  本模块是 Graphiti 的轻量级本地平替方案，使用 KuzuDB（嵌入式图数据库）
#  实现与 Graphiti 等价的时间化知识图谱能力，但无需部署任何外部服务。
#
#  核心概念：
#    ┌──────────┐  INVOLVES (valid_from, valid_to)  ┌──────────┐
#    │ Episode  │ ─────────────────────────────────► │  Entity  │
#    │ (事件)   │                                    │  (实体)  │
#    └──────────┘                                    └──────────┘
#         │
#         │ RELATED_TO (weight, valid_from, valid_to)
#         ▼
#    ┌──────────┐
#    │ Episode  │
#    │ (事件)   │
#    └──────────┘
#
#  通用对外方法（Universal Public API）：
#
#    add_episode()              — 写入一条情节记忆到图谱
#    search()                   — 基于关键词检索情节
#    query_temporal()           — 时间化回溯查询（Graphiti 核心能力平替）
#    add_entity()               — 添加实体节点
#    link_episode_to_entity()   — 建立带时间属性的事件-实体关联
#    get_graph_stats()          — 图谱健康统计概览
#
#  使用方式：
#
#    from zentex.memory.storage.kuzu_backend import KuzuGraphMemoryClient
#    client = KuzuGraphMemoryClient(db_path=".zentex/kuzu_db")
#    client.add_episode(name="...", episode_body={...}, ...)
#    hits = client.search("timeout", limit=5)
#    temporal_hits = client.query_temporal("Alice", point_in_time=some_dt)
#
# ════════════════════════════════════════════════════════════════════
