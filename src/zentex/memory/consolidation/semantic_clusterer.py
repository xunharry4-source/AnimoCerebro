from __future__ import annotations

"""
Semantic clustering plugin for memory consolidation.

RESPONSIBILITY:
  - Build real text vectors from memory fragment summaries/titles.
  - Cluster related fragments with HDBSCAN when available, otherwise DBSCAN.
  - In auto mode only, use token-overlap clustering when vector dependencies
    are unavailable.
  - Emit promotion candidates, pruned refs, and pattern scores.

DOES NOT:
  - Call any LLM
  - Persist results
  - Pretend success when vectorization fails
"""

import logging
import re
import time
from typing import Any, Dict, List, Literal

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None  # type: ignore[assignment]

try:
    from sklearn.cluster import DBSCAN
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_distances
except ImportError:  # pragma: no cover
    DBSCAN = None  # type: ignore[assignment]
    TfidfVectorizer = None  # type: ignore[assignment]
    cosine_distances = None  # type: ignore[assignment]

from zentex.memory.consolidation.consolidation import (
    ConsolidationPluginOutput,
    ForgettableNoiseRule,
    MemoryPromotionCandidate,
    PatternStabilityScore,
)
from zentex.memory.consolidation.stats_pipeline import compute_pattern_scores, refs_to_dataframe
from zentex.plugins.contracts import PluginLifecycleStatus

try:
    from sentence_transformers import SentenceTransformer
except ImportError:  # pragma: no cover
    SentenceTransformer = None  # type: ignore[assignment]

try:
    from hdbscan import HDBSCAN
except ImportError:  # pragma: no cover
    HDBSCAN = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


class SemanticClusteringPlugin:
    plugin_id = "semantic_clusterer"
    behavior_key = "memory_consolidation"
    status = PluginLifecycleStatus.ACTIVE
    supports_multi_active = True

    def __init__(
        self,
        *,
        model_name: str = "all-MiniLM-L6-v2",
        cluster_backend: Literal["auto", "hdbscan", "dbscan"] = "auto",
        eps: float = 0.35,
        min_samples: int = 2,
        min_cluster_size: int = 2,
        noise_prune_threshold: float = 0.4,
    ) -> None:
        self._model_name = model_name
        self._cluster_backend = cluster_backend
        self._eps = float(eps)
        self._min_samples = int(min_samples)
        self._min_cluster_size = int(min_cluster_size)
        self._noise_prune_threshold = float(noise_prune_threshold)
        self._model: Any = None
        self._vectorizer: Any = None
        self._last_backend_used: str | None = None
        self._last_encoder_used: str | None = None

    @property
    def last_backend_used(self) -> str | None:
        return self._last_backend_used

    @property
    def last_encoder_used(self) -> str | None:
        return self._last_encoder_used

    def _text_for_ref(self, ref: Dict[str, Any]) -> str:
        summary = str(ref.get("summary") or "").strip()
        title = str(ref.get("title") or "").strip()
        text = " ".join(part for part in [title, summary] if part).strip()
        return text or str(ref.get("ref_id") or ref.get("id") or "")

    def _encode_texts(self, texts: List[str]) -> Any:
        if SentenceTransformer is not None and np is not None:
            try:
                if self._model is None:
                    self._model = SentenceTransformer(self._model_name)
                embeddings = self._model.encode(texts)
                self._last_encoder_used = "sentence_transformer"
                return np.asarray(embeddings, dtype=np.float32)
            except Exception:
                logger.warning(
                    "SemanticClusteringPlugin: failed to load or use sentence-transformers model %s; "
                    "falling back to TF-IDF vectors",
                    self._model_name,
                    exc_info=True,
                )
        if TfidfVectorizer is not None and np is not None:
            if self._vectorizer is None:
                self._vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4))
            matrix = self._vectorizer.fit_transform(texts)
            self._last_encoder_used = "tfidf"
            return matrix.toarray().astype(np.float32)
        self._last_encoder_used = "token_overlap"
        return [_token_set(text) for text in texts]

    def _encode_with_tfidf(self, texts: List[str]) -> Any:
        if TfidfVectorizer is None or np is None:
            raise ImportError("sklearn and numpy are required for TF-IDF vector clustering")
        if self._vectorizer is None:
            self._vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4))
        matrix = self._vectorizer.fit_transform(texts)
        self._last_encoder_used = "tfidf"
        return matrix.toarray().astype(np.float32)

    def _cluster_with_hdbscan(self, vectors: Any) -> Any:
        if HDBSCAN is None or np is None or cosine_distances is None:
            raise ImportError(
                "hdbscan is required for SemanticClusteringPlugin(cluster_backend='hdbscan'). "
                "Install hdbscan>=0.8.33."
            )
        distance_matrix = np.asarray(cosine_distances(vectors), dtype=np.float64)
        clusterer = HDBSCAN(
            min_cluster_size=max(2, self._min_cluster_size),
            min_samples=max(1, self._min_samples - 1),
            metric="precomputed",
            cluster_selection_epsilon=max(0.0, self._eps),
            cluster_selection_method="eom",
        )
        self._last_backend_used = "hdbscan"
        return np.asarray(clusterer.fit_predict(distance_matrix), dtype=int)

    def _cluster_with_dbscan(self, vectors: Any) -> Any:
        if DBSCAN is None or np is None:
            raise ImportError("sklearn and numpy are required for DBSCAN vector clustering")
        clustering = DBSCAN(metric="cosine", eps=self._eps, min_samples=self._min_samples)
        self._last_backend_used = "dbscan"
        return np.asarray(clustering.fit_predict(vectors), dtype=int)

    def _cluster_with_token_overlap(self, token_sets: list[set[str]]) -> list[int]:
        labels = [-1 for _ in token_sets]
        next_label = 0
        for idx, tokens in enumerate(token_sets):
            if labels[idx] != -1:
                continue
            cluster = [idx]
            threshold = max(0.05, min(1.0, self._eps))
            for other_idx in range(idx + 1, len(token_sets)):
                if _jaccard(tokens, token_sets[other_idx]) >= threshold:
                    cluster.append(other_idx)
            if len(cluster) >= self._min_samples:
                for member in cluster:
                    labels[member] = next_label
                next_label += 1
        self._last_backend_used = "token_overlap"
        return labels

    def _cluster_vectors(self, vectors: Any) -> Any:
        if self._cluster_backend == "hdbscan":
            if isinstance(vectors, list):
                raise ImportError(
                    "hdbscan clustering requires sentence-transformers or sklearn/numpy vector encoding; "
                    "token-overlap fallback is only allowed in auto mode."
                )
            return self._cluster_with_hdbscan(vectors)
        if self._cluster_backend == "dbscan":
            if isinstance(vectors, list):
                raise ImportError(
                    "dbscan clustering requires sklearn/numpy vector encoding; "
                    "token-overlap fallback is only allowed in auto mode."
                )
            return self._cluster_with_dbscan(vectors)
        if isinstance(vectors, list):
            return self._cluster_with_token_overlap(vectors)
        if HDBSCAN is not None:
            try:
                labels = self._cluster_with_hdbscan(vectors)
                if any(int(label) != -1 for label in labels):
                    return labels
                logger.info(
                    "SemanticClusteringPlugin: HDBSCAN returned only noise in auto mode; falling back to DBSCAN"
                )
            except Exception:
                logger.warning(
                    "SemanticClusteringPlugin: HDBSCAN failed in auto mode; falling back to DBSCAN",
                    exc_info=True,
                )
        try:
            return self._cluster_with_dbscan(vectors)
        except ImportError:
            if isinstance(vectors, list):
                return self._cluster_with_token_overlap(vectors)
            raise

    def analyze_memory(
        self,
        *,
        context: Dict[str, Any],
        noise_rules: List[ForgettableNoiseRule],
    ) -> ConsolidationPluginOutput:
        input_refs = list(context.get("input_memory_refs", []) or [])
        if len(input_refs) < 2:
            logger.info("SemanticClusteringPlugin: fewer than 2 refs; skipping clustering")
            return ConsolidationPluginOutput(plugin_id=self.plugin_id)

        texts = [self._text_for_ref(ref) for ref in input_refs]
        vectors = self._encode_texts(texts)
        labels = self._cluster_vectors(vectors)

        promotion_candidates: list[MemoryPromotionCandidate] = []
        pruned_refs: list[str] = []
        pattern_scores: list[PatternStabilityScore] = []
        grouped: dict[int, list[Dict[str, Any]]] = {}
        for ref, label in zip(input_refs, labels):
            grouped.setdefault(int(label), []).append(ref)

        for label, refs in grouped.items():
            if label == -1:
                for ref in refs:
                    try:
                        reuse_value = float(ref.get("reuse_value", 0.0) or 0.0)
                    except (TypeError, ValueError):
                        reuse_value = 0.0
                    threshold = self._noise_prune_threshold
                    for rule in noise_rules:
                        threshold = min(threshold, float(rule.reuse_threshold))
                    if reuse_value < threshold:
                        pruned_refs.append(str(ref.get("ref_id") or ref.get("id") or ""))
                continue

            cluster_scores = compute_pattern_scores(refs_to_dataframe(refs, now_ts=time.time()))
            best_score = cluster_scores[0] if cluster_scores else None
            pattern_scores.extend(cluster_scores)
            promotion_candidates.append(
                MemoryPromotionCandidate(
                    source_ref=f"cluster:{label}",
                    candidate_type="pattern",
                    stability_score=best_score.stability_score if best_score is not None else 0.0,
                    reuse_value=best_score.cross_context_reuse if best_score is not None else 0.0,
                    promotion_reason=f"Semantic cluster {label} groups {len(refs)} related memory fragments.",
                )
            )

        return ConsolidationPluginOutput(
            plugin_id=self.plugin_id,
            promotion_candidates=promotion_candidates,
            pruned_refs=[ref_id for ref_id in pruned_refs if ref_id],
            pattern_scores=pattern_scores,
        )


def _token_set(text: str) -> set[str]:
    return {token for token in re.findall(r"[A-Za-z0-9_\u4e00-\u9fff]+", text.lower()) if token}


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / float(len(left | right))
