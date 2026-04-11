from __future__ import annotations

"""
Hybrid retrieval engine with adaptive query routing.

职责:
  - 将查询路由到最合适的检索后端（关键词、语义、图谱、profile 直查）。
  - 合并多后端结果，执行基于分数的融合与去重（RRF — Reciprocal Rank Fusion）。
  - QueryClassifier：自动判断查询类型（事实/时间/流程/身份），选择最优检索链路。
  - 每次查询通过 MemoryAccessTracker 记录，为 lifecycle 分析提供数据。

不负责:
  - 修改任何记忆记录（只读）。
  - LLM 重排序（仅做分数融合；LLM 重排可在上层调用）。
  - 直接连接 Kuzu 数据库（通过 EpisodeGraphMemoryAdapter 代理）。

查询类型 → 路由逻辑:
  FACTUAL    → semantic + keyword
  TEMPORAL   → graph temporal + keyword
  PROCEDURAL → procedural store + keyword
  IDENTITY   → profile direct lookup (fastest)
  GENERAL    → all backends + RRF fusion
"""

import logging
import re
from datetime import datetime
from typing import Any, Protocol
from dataclasses import dataclass, field
from .deep_recall import DeepRecallEngine, build_engine_from_service
from .temporal import TemporalEngine, build_temporal_engine

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Query type classification
# ---------------------------------------------------------------------------

class QueryType(str):
    FACTUAL = "factual"
    TEMPORAL = "temporal"
    PROCEDURAL = "procedural"
    IDENTITY = "identity"
    ANALYTICAL = "analytical"
    COMPARATIVE = "comparative"
    GENERAL = "general"
    DEEP_RECALL = "deep_recall"
    SOCIAL = "social" # Phase 2.3 gap: Interaction and relationship focus


# Keyword signals per query type (fast heuristic routing — no LLM needed)
_TEMPORAL_SIGNALS = re.compile(
    r"\b(when|before|after|during|since|until|at the time|history|was|were|used to|"
    r"back in|as of|point in time|timeline|event)\b",
    re.IGNORECASE,
)
_PROCEDURAL_SIGNALS = re.compile(
    r"\b(how|steps|procedure|workflow|process|way to|guide|tutorial|best practice|"
    r"method|approach|configure|implement|deploy|run|execute)\b",
    re.IGNORECASE,
)
_IDENTITY_SIGNALS = re.compile(
    r"\b(who am I|my goal|current objective|my identity|my role|my constraint|"
    r"my strategy|my preference|about me|profile|identity)\b",
    re.IGNORECASE,
)
_ANALYTICAL_SIGNALS = re.compile(
    r"\b(analyze|statistics|distribute|average|mean|median|correlation|trend|pattern|"
    r"summary of|overview of|performance|metric)\b",
    re.IGNORECASE,
)
_COMPARATIVE_SIGNALS = re.compile(
    r"\b(compare|versus|vs|difference between|similarity|different|same as|better|worse|"
    r"instead of|relative to)\b",
    re.IGNORECASE,
)
_SOCIAL_SIGNALS = re.compile(
    r"\b(friend|colleague|partner|met|introduced|knows|spoke to|talked with|relationship|"
    r"interaction|together|meeting|shared)\b",
    re.IGNORECASE,
)


class QueryClassifier:
    """
    Classifies free-text queries into QueryType using lightweight regex heuristics.

    这是故意不使用 LLM 的：路由决策必须在亚毫秒内完成，且不允许引入不确定性。
    """

    def classify(self, query: str) -> str:
        if _IDENTITY_SIGNALS.search(query):
            return QueryType.IDENTITY
        if _COMPARATIVE_SIGNALS.search(query):
            return QueryType.COMPARATIVE
        if _ANALYTICAL_SIGNALS.search(query):
            return QueryType.ANALYTICAL
        if _TEMPORAL_SIGNALS.search(query):
            return QueryType.TEMPORAL
        if _PROCEDURAL_SIGNALS.search(query):
            return QueryType.PROCEDURAL
        if _SOCIAL_SIGNALS.search(query):
            return QueryType.SOCIAL
        # Default to factual for specific-sounding queries, general otherwise.
        word_count = len(query.split())
        if word_count <= 8:
            return QueryType.FACTUAL
        return QueryType.GENERAL


# ---------------------------------------------------------------------------
# Retrieval result
# ---------------------------------------------------------------------------

@dataclass
class RetrievalResult:
    """Unified retrieval hit from any backend."""

    memory_id: str
    score: float
    source: str               # "keyword" | "semantic" | "graph" | "profile"
    memory_layer: str = ""
    source_kind: str = ""
    title: str = ""
    summary: str = ""
    trace_id: str = ""
    tags: list[str] = field(default_factory=list)
    source_refs: list[str] = field(default_factory=list)
    explanation: str = ""


# ---------------------------------------------------------------------------
# Backend protocol
# ---------------------------------------------------------------------------

class KeywordSearchBackend(Protocol):
    """Any store that supports .search(query, limit, trace_id, target_id)."""

    def search(
        self,
        query: str,
        limit: int,
        trace_id: str | None = None,
        target_id: str | None = None,
    ) -> list[Any]: ...


# ---------------------------------------------------------------------------
# Hybrid retrieval engine
# ---------------------------------------------------------------------------

class HybridRetrievalEngine:
    """
    Combines keyword, semantic, and graph retrieval with adaptive routing.

    构造时注入各后端；未配置的后端会被跳过（不报错）。
    所有检索结果通过 RRF（Reciprocal Rank Fusion）融合，确保多来源结果的
    分数可比性。
    """

    def __init__(
        self,
        *,
        index: Any | None = None,                   # MultiModalIndex
        vector_index: Any | None = None,            # VectorSearchEngine
        semantic_store: Any | None = None,         # Has .search(query, limit, ...)
        procedural_store: Any | None = None,        # Has .search(query, limit, ...)
        graph_client: Any | None = None,            # KuzuGraphMemoryClient
        profile_service: Any | None = None,         # Has .get_active_profile(...)
        semantic_recall_client: Any | None = None,  # SemanticMemoryRecallClient
        access_tracker: Any | None = None,          # MemoryAccessTracker
        memory_service: Any | None = None,          # For deep recall
        rrf_k: int = 60,
    ) -> None:
        self._index = index
        self._vector_index = vector_index
        self._semantic_store = semantic_store
        self._procedural_store = procedural_store
        self._graph = graph_client
        self._profile_service = profile_service
        self._semantic_recall = semantic_recall_client
        self._tracker = access_tracker
        self.memory_service = memory_service
        self._classifier = QueryClassifier()
        self._rrf_k = rrf_k
        self._query_cache: dict[str, tuple[datetime, list[RetrievalResult]]] = {}
        self._cache_limit = 500
        self._cache_ttl_sec = 300 # 5 minutes

    # ── main entry point ─────────────────────────────────────────────────

    def search(
        self,
        query: str,
        *,
        limit: int = 10,
        trace_id: str | None = None,
        target_id: str | None = None,
        as_of_time: datetime | None = None,
        query_type: str | None = None,
        boost_recent: bool = False,
    ) -> list[RetrievalResult]:
        """
        Perform adaptive hybrid search.

        Args:
            query: Free-text search query.
            limit: Maximum number of results to return.
            trace_id: Filter results by trace_id.
            target_id: Filter results by target_id.
            as_of_time: For temporal queries — reconstruct state at this time.
            query_type: Override automatic query classification.
            boost_recent: Apply a small score boost to recently created records.

        Returns:
            Reranked list of RetrievalResult, deduplicated by memory_id.
        """
        # Phase 2.3: Query Result Cache lookup
        cache_key = f"{query}:{trace_id}:{target_id}:{query_type}"
        if cache_key in self._query_cache:
            ts, cached_res = self._query_cache[cache_key]
            if (datetime.now() - ts).total_seconds() < self._cache_ttl_sec:
                logger.debug("HybridRetrieval: Cache HIT for %r", query[:30])
                return cached_res

        qtype = query_type or self._classifier.classify(query)
        
        # Existing intent handling code
        if qtype == QueryType.DEEP_RECALL:
            # Build or reuse the graph engine (lazy init)
            if not hasattr(self, "_deep_recall_engine"):
                self._deep_recall_engine = build_engine_from_service(self.memory_service)
            # For simplicity, treat the query as a start node ID; in real use a parser extracts it.
            start_id = query.strip()
            bfs_paths = self._deep_recall_engine.bfs(start_id, max_hops=3)
            # Convert paths to readable results
            results = []
            for path in bfs_paths:
                explanation = self._deep_recall_engine.explain_path(path)
                results.append({"path": path, "explanation": explanation})
            return results

        logger.debug("HybridRetrieval: query=%r type=%s", query[:50], qtype)

        all_results: list[RetrievalResult] = []

        if qtype == QueryType.IDENTITY:
            all_results.extend(self._search_profiles(query, limit=limit))
        elif qtype == QueryType.TEMPORAL:
            # Temporal reconstruction using TemporalEngine if as_of_time is provided
            if as_of_time:
                if not hasattr(self, "_temporal_engine"):
                    self._temporal_engine = build_temporal_engine(self.memory_service)
                temporal_results = self._temporal_engine.snapshot_at(as_of_time, limit=limit)
                all_results.extend(temporal_results)
            # Fallback to normal keyword search
            all_results.extend(self._search_keyword(query, limit=limit, trace_id=trace_id, target_id=target_id))
        elif qtype == QueryType.PROCEDURAL:
            all_results.extend(self._search_procedural(query, limit=limit, trace_id=trace_id, target_id=target_id))
            all_results.extend(self._search_keyword(query, limit=limit, trace_id=trace_id, target_id=target_id))
        elif qtype == QueryType.ANALYTICAL:
            # Analytical prioritizing broad keyword matching and metadata
            all_results.extend(self._search_keyword(query, limit=limit * 2, trace_id=trace_id, target_id=target_id))
        elif qtype == QueryType.COMPARATIVE:
            # Comparative prioritizing vector similarity for nuance
            all_results.extend(self._search_vector(query, limit=limit * 2))
            all_results.extend(self._search_keyword(query, limit=limit, trace_id=trace_id, target_id=target_id))
        elif qtype == QueryType.FACTUAL:
            all_results.extend(self._search_vector(query, limit=limit, trace_id=trace_id, target_id=target_id))
            all_results.extend(self._search_keyword(query, limit=limit, trace_id=trace_id, target_id=target_id))
        elif qtype == QueryType.SOCIAL:
            # Social focuses on people and events — prioritizes keyword for exact names
            all_results.extend(self._search_keyword(query, limit=limit, trace_id=trace_id, target_id=target_id))
            all_results.extend(self._search_vector(query, limit=limit))
        else:  # GENERAL — all backends
            all_results.extend(self._search_keyword(query, limit=limit, trace_id=trace_id, target_id=target_id))
            all_results.extend(self._search_vector(query, limit=limit, trace_id=trace_id, target_id=target_id))
            all_results.extend(self._search_graph_temporal(query, limit=limit, as_of_time=as_of_time))

        # Phase 2.2: Perform 40/60 weighted fusion if both sources are present,
        # otherwise fall back to RRF for multi-backend consistency.
        if any(r.source == "vector" for r in all_results) and any(r.source == "keyword" for r in all_results):
            fused = self._weighted_fuse(all_results, keyword_weight=0.4, vector_weight=0.6)
        else:
            fused = self._rrf_fuse(all_results)

        # Phase 2.3: Update cache
        if len(self._query_cache) >= self._cache_limit:
            self._query_cache.pop(next(iter(self._query_cache)))
        self._query_cache[cache_key] = (datetime.now(), fused[:limit])

        return fused[:limit]

    # ── per-backend search methods ────────────────────────────────────────

    def _search_keyword(
        self,
        query: str,
        limit: int,
        trace_id: str | None = None,
        target_id: str | None = None,
    ) -> list[RetrievalResult]:
        if self._index:
            # Phase 2.1: Use optimized SQLite FTS5 index
            filters = {}
            if trace_id: filters["trace_id"] = trace_id
            if target_id: filters["target_id"] = target_id
            hits = self._index.search(query, filters=filters, limit=limit)
            return [
                RetrievalResult(
                    memory_id=h["memory_id"],
                    score=0.8, # BM25 rank would be better here
                    source="keyword",
                    memory_layer=h["memory_layer"],
                    source_kind=h["source_kind"],
                    title=h["title"],
                    summary=h["summary"],
                    trace_id=h["trace_id"],
                    explanation="FTS5 binary match",
                )
                for h in hits
            ]
        
        # Legacy fallback
        results: list[RetrievalResult] = []
        for store, label in [
            (self._semantic_store, "semantic"),
            (self._procedural_store, "procedural"),
        ]:
            if store is None:
                continue
            try:
                hits = store.search(query, limit, trace_id=trace_id, target_id=target_id)
                for h in hits:
                    results.append(RetrievalResult(
                        memory_id=getattr(h, "memory_id", str(id(h))),
                        score=float(getattr(h, "score", 0.5)),
                        source="keyword",
                        memory_layer=getattr(h, "memory_layer", label),
                        source_kind=getattr(h, "source_kind", ""),
                        title=getattr(h, "title", ""),
                        summary=getattr(h, "summary", ""),
                        trace_id=getattr(h, "trace_id", ""),
                        tags=list(getattr(h, "tags", [])),
                        source_refs=list(getattr(h, "source_refs", [])),
                        explanation="Legacy keyword match",
                    ))
            except Exception as exc:
                logger.warning("Keyword search (%s) failed: %s", label, exc)
        return results

    def _search_vector(
        self,
        query: str,
        limit: int,
        trace_id: str | None = None,
        target_id: str | None = None,
    ) -> list[RetrievalResult]:
        """Phase 2.2: Semantic similarity search using VectorSearchEngine (FAISS)."""
        if not self._vector_index:
            return self._search_semantic(query, limit, trace_id, target_id)
            
        try:
            hits = self._vector_index.search(query, limit=limit)
            results: list[RetrievalResult] = []
            for mid, score in hits:
                # Need metadata for RetrievalResult
                res_meta = self._index.search("", filters={"memory_id": mid}, limit=1) if self._index else []
                if res_meta:
                    m = res_meta[0]
                    results.append(RetrievalResult(
                        memory_id=mid,
                        score=score,
                        source="vector",
                        memory_layer=m["memory_layer"],
                        source_kind=m["source_kind"],
                        title=m["title"],
                        summary=m["summary"],
                        trace_id=m["trace_id"],
                        explanation=f"FAISS Semantic ({score:.2f})",
                    ))
            return results
        except Exception as exc:
            logger.warning("Vector search failed: %s", exc)
            return []

    def _search_semantic(
        self,
        query: str,
        limit: int,
        trace_id: str | None = None,
        target_id: str | None = None,
    ) -> list[RetrievalResult]:
        if not self._semantic_recall:
            return []
        try:
            hits = self._semantic_recall.search_memories(
                query=query, limit=limit, trace_id=trace_id, target_id=target_id
            )
            return [
                RetrievalResult(
                    memory_id=h.memory_id,
                    score=min(1.0, h.score * 1.15),  # Slight boost for semantic
                    source="semantic",
                    memory_layer=h.memory_layer,
                    source_kind=h.source_kind,
                    title=h.title,
                    summary=h.summary,
                    trace_id=h.trace_id,
                    tags=list(h.tags),
                    source_refs=list(h.source_refs),
                    explanation="Semantic similarity",
                )
                for h in hits
            ]
        except Exception as exc:
            logger.warning("Semantic search failed: %s", exc)
            return []

    def _search_graph_temporal(
        self,
        query: str,
        limit: int,
        as_of_time: datetime | None = None,
    ) -> list[RetrievalResult]:
        if not self._graph:
            return []
        try:
            if as_of_time:
                rows = self._graph.query_at_time_point(query, as_of_time=as_of_time, limit=limit)
            else:
                raw_hits = self._graph.search(query, limit=limit)
                rows = [
                    {"id": getattr(h, "uuid", ""), "name": getattr(h, "name", ""),
                     "summary": getattr(h, "summary", "")}
                    for h in raw_hits
                ]
            return [
                RetrievalResult(
                    memory_id=str(row.get("id", "")),
                    score=0.8,
                    source="graph",
                    memory_layer="episodic",
                    source_kind="graph",
                    title=str(row.get("name", "")),
                    summary=str(row.get("summary", "")),
                    explanation="Graph traversal",
                )
                for row in rows if row.get("id")
            ]
        except Exception as exc:
            logger.warning("Graph search failed: %s", exc)
            return []

    def _search_procedural(
        self,
        query: str,
        limit: int,
        trace_id: str | None = None,
        target_id: str | None = None,
    ) -> list[RetrievalResult]:
        if not self._procedural_store:
            return []
        try:
            hits = self._procedural_store.search(query, limit, trace_id=trace_id, target_id=target_id)
            return [
                RetrievalResult(
                    memory_id=getattr(h, "memory_id", str(id(h))),
                    score=float(getattr(h, "score", 0.6)),
                    source="keyword",
                    memory_layer="procedural",
                    source_kind=getattr(h, "source_kind", ""),
                    title=getattr(h, "title", ""),
                    summary=getattr(h, "summary", ""),
                    explanation="Procedural store match",
                )
                for h in hits
            ]
        except Exception as exc:
            logger.warning("Procedural search failed: %s", exc)
            return []

    def _search_profiles(self, query: str, limit: int) -> list[RetrievalResult]:
        """
        For identity-type queries, do a direct profile lookup using keywords
        from the query as profile titles.
        """
        if not self._profile_service:
            return []
        results: list[RetrievalResult] = []
        # Try each word in the query as a potential profile title.
        words = [w for w in query.split() if len(w) > 3][:5]
        for word in words:
            try:
                profile = self._profile_service.get_active_profile(
                    memory_layer="semantic",
                    title=word,
                    source_kind="profile",
                )
                if profile:
                    results.append(RetrievalResult(
                        memory_id=profile.memory_id,
                        score=0.95,
                        source="profile",
                        memory_layer="semantic",
                        title=profile.title,
                        summary=profile.summary,
                        explanation="Direct profile lookup",
                    ))
            except Exception:
                pass
        return results[:limit]

    def _weighted_fuse(self, results: list[RetrievalResult], keyword_weight: float, vector_weight: float) -> list[RetrievalResult]:
        """Phase 2.2: Weighted sum fusion for keyword and vector sources."""
        scores: dict[str, float] = {}
        representative: dict[str, RetrievalResult] = {}
        
        for r in results:
            mid = r.memory_id
            if mid not in representative or r.score > representative[mid].score:
                representative[mid] = r
            
            weight = keyword_weight if r.source == "keyword" else (vector_weight if r.source == "vector" else 0.5)
            scores[mid] = scores.get(mid, 0.0) + (r.score * weight)
            
        fused = []
        max_score = max(scores.values(), default=1.0)
        for mid, total_score in scores.items():
            r = representative[mid]
            fused.append(RetrievalResult(
                memory_id=mid,
                score=(total_score / max_score) if max_score > 0 else 0.0,
                source=r.source,
                memory_layer=r.memory_layer,
                source_kind=r.source_kind,
                title=r.title,
                summary=r.summary,
                trace_id=r.trace_id,
                explanation=f"Weighted({r.source})",
            ))
        fused.sort(key=lambda r: r.score, reverse=True)
        return fused

    # ── RRF score fusion ──────────────────────────────────────────────────

    def _rrf_fuse(self, results: list[RetrievalResult]) -> list[RetrievalResult]:
        """
        Reciprocal Rank Fusion: combine scores from multiple ranked lists.

        RRF score = Σ 1 / (k + rank_i)  for each list i that contains the document.

        Produces a single fused ranking that rewards documents appearing highly
        in multiple independent result lists.
        """
        # Group by source to build per-source rankings.
        source_lists: dict[str, list[RetrievalResult]] = {}
        for r in results:
            source_lists.setdefault(r.source, []).append(r)
        for lst in source_lists.values():
            lst.sort(key=lambda r: r.score, reverse=True)

        # Compute RRF scores.
        rrf_scores: dict[str, float] = {}
        representative: dict[str, RetrievalResult] = {}
        k = self._rrf_k
        for source_list in source_lists.values():
            for rank, result in enumerate(source_list, start=1):
                mid = result.memory_id
                rrf_scores[mid] = rrf_scores.get(mid, 0.0) + 1.0 / (k + rank)
                if mid not in representative or result.score > representative[mid].score:
                    representative[mid] = result

        # Normalise to [0, 1].
        max_rrf = max(rrf_scores.values(), default=1.0)
        fused: list[RetrievalResult] = []
        for mid, rrf_score in rrf_scores.items():
            r = representative[mid]
            fused.append(RetrievalResult(
                memory_id=r.memory_id,
                score=rrf_score / max_rrf,
                source=r.source,
                memory_layer=r.memory_layer,
                source_kind=r.source_kind,
                title=r.title,
                summary=r.summary,
                trace_id=r.trace_id,
                tags=r.tags,
                source_refs=r.source_refs,
                explanation=f"RRF({r.source})",
            ))
        fused.sort(key=lambda r: r.score, reverse=True)
        return fused
