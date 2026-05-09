from __future__ import annotations

"""
Reflection label auditor backed by CleanLab.

RESPONSIBILITY:
  - Build text features from real reflection records
  - Generate out-of-sample predicted probabilities
  - Use CleanLab to identify suspicious quality labels

DOES NOT:
  - Delete records
  - Update governance state directly
  - Call any LLM
"""

import logging
from dataclasses import dataclass
from typing import ClassVar, Iterable

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold, cross_val_predict

try:
    from sentence_transformers import SentenceTransformer
except ImportError:  # pragma: no cover
    SentenceTransformer = None  # type: ignore[assignment]

try:
    from cleanlab.filter import find_label_issues
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "cleanlab is required for zentex.reflection.label_auditor. "
        "Add cleanlab>=2.6,<3.0 to requirements.txt and reinstall."
    ) from exc

logger = logging.getLogger(__name__)


@dataclass
class LabelAuditReport:
    suspicious_ids: list[str]
    total_audited: int
    audit_confidence: float
    cleanlab_issue_count: int


def _enum_value(value: object) -> str:
    raw = getattr(value, "value", value)
    return str(raw or "").strip().lower()


class ReflectionLabelAuditor:
    QUALITY_TO_INT: ClassVar[dict[str, int]] = {
        "poor": 0,
        "fair": 1,
        "good": 2,
        "excellent": 3,
    }

    def __init__(self, *, model_name: str = "all-MiniLM-L6-v2") -> None:
        self._model_name = model_name
        self._model: object | None = None

    def _texts(self, records: Iterable[object]) -> list[str]:
        rows: list[str] = []
        for record in records:
            subject = str(getattr(record, "subject", "") or "").strip()
            summary = str(getattr(record, "summary", "") or "").strip()
            rows.append(" ".join(part for part in [subject, summary] if part).strip())
        return rows

    def _build_features(self, texts: list[str]) -> np.ndarray | object:
        if SentenceTransformer is not None:
            try:
                if self._model is None:
                    self._model = SentenceTransformer(self._model_name)
                embeddings = self._model.encode(texts)
                return np.asarray(embeddings, dtype=np.float32)
            except Exception:
                logger.warning(
                    "ReflectionLabelAuditor: failed to load or use sentence-transformers model %s; "
                    "falling back to TF-IDF features",
                    self._model_name,
                    exc_info=True,
                )

        vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), min_df=1)
        return vectorizer.fit_transform(texts)

    def _semantic_rescue_ids(
        self,
        *,
        features: np.ndarray | object,
        labels: list[int],
        record_ids: list[str],
    ) -> set[str]:
        dense = features.toarray() if hasattr(features, "toarray") else np.asarray(features, dtype=np.float32)
        if dense.size == 0:
            return set()

        labels_arr = np.asarray(labels, dtype=int)
        poor_label = self.QUALITY_TO_INT["poor"]
        positive_labels = [
            self.QUALITY_TO_INT["good"],
            self.QUALITY_TO_INT["excellent"],
        ]
        if not np.any(labels_arr == poor_label):
            return set()
        if not any(np.any(labels_arr == label) for label in positive_labels):
            return set()

        poor_centroid = dense[labels_arr == poor_label].mean(axis=0, keepdims=True)
        positive_vectors = [dense[labels_arr == label] for label in positive_labels if np.any(labels_arr == label)]
        positive_centroid = np.vstack(positive_vectors).mean(axis=0, keepdims=True)

        rescue_ids: set[str] = set()
        for index, label in enumerate(labels_arr):
            if int(label) != poor_label:
                continue
            vector = dense[index : index + 1]
            poor_sim = float(cosine_similarity(vector, poor_centroid)[0][0])
            positive_sim = float(cosine_similarity(vector, positive_centroid)[0][0])
            if positive_sim >= poor_sim + 0.02:
                rescue_ids.add(record_ids[index])
        return rescue_ids

    def _semantic_neighbor_issue_ids(
        self,
        *,
        features: np.ndarray | object,
        labels: list[int],
        record_ids: list[str],
        neighbor_count: int = 7,
    ) -> set[str]:
        dense = features.toarray() if hasattr(features, "toarray") else np.asarray(features, dtype=np.float32)
        if dense.shape[0] < 2:
            return set()

        labels_arr = np.asarray(labels, dtype=int)
        poor_label = self.QUALITY_TO_INT["poor"]
        positive_labels = {
            self.QUALITY_TO_INT["good"],
            self.QUALITY_TO_INT["excellent"],
        }
        sims = cosine_similarity(dense)
        issue_ids: set[str] = set()
        k = max(1, min(neighbor_count, dense.shape[0] - 1))
        for index, label in enumerate(labels_arr):
            if int(label) != poor_label:
                continue
            similarities = sims[index].copy()
            similarities[index] = -1.0
            neighbor_indices = np.argsort(similarities)[-k:]
            neighbor_labels = labels_arr[neighbor_indices]
            positive_count = sum(1 for item in neighbor_labels if int(item) in positive_labels)
            poor_count = sum(1 for item in neighbor_labels if int(item) == poor_label)
            if positive_count >= max(3, (k // 2) + 1) and positive_count > poor_count:
                issue_ids.add(record_ids[index])
        return issue_ids

    def audit(self, records: list[object]) -> LabelAuditReport:
        if len(records) < 100:
            raise ValueError("ReflectionLabelAuditor requires at least 100 samples")

        labels: list[int] = []
        record_ids: list[str] = []
        valid_records: list[object] = []
        for record in records:
            quality = _enum_value(getattr(record, "quality", ""))
            if quality not in self.QUALITY_TO_INT:
                continue
            labels.append(self.QUALITY_TO_INT[quality])
            record_ids.append(str(getattr(record, "reflection_id", "") or ""))
            valid_records.append(record)

        if len(valid_records) < 100:
            raise ValueError("ReflectionLabelAuditor requires at least 100 labeled samples")

        label_counts: dict[int, int] = {}
        for label in labels:
            label_counts[label] = label_counts.get(label, 0) + 1
        if any(count < 5 for count in label_counts.values()):
            raise ValueError(
                f"ReflectionLabelAuditor requires at least 5 samples per present class; got {label_counts}"
            )

        texts = self._texts(valid_records)
        features = self._build_features(texts)

        classifier = LogisticRegression(max_iter=1000)
        splitter = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
        pred_probs = cross_val_predict(
            classifier,
            features,
            np.asarray(labels, dtype=int),
            cv=splitter,
            method="predict_proba",
        )
        if pred_probs.shape[0] != len(valid_records):
            logger.error(
                "ReflectionLabelAuditor: pred_probs row mismatch records=%s probs=%s",
                len(valid_records),
                pred_probs.shape[0],
                exc_info=True,
            )
            raise ValueError("pred_probs row count mismatch")

        issue_mask = find_label_issues(
            labels=np.asarray(labels, dtype=int),
            pred_probs=np.asarray(pred_probs, dtype=float),
        )
        suspicious_ids = [
            record_id
            for record_id, is_issue in zip(record_ids, issue_mask)
            if bool(is_issue)
        ]
        suspicious_ids = sorted(
            set(suspicious_ids)
            | self._semantic_rescue_ids(
                features=features,
                labels=labels,
                record_ids=record_ids,
            )
            | self._semantic_neighbor_issue_ids(
                features=features,
                labels=labels,
                record_ids=record_ids,
            )
        )
        confidence = 1.0 - (len(suspicious_ids) / max(1, len(valid_records)))
        return LabelAuditReport(
            suspicious_ids=suspicious_ids,
            total_audited=len(valid_records),
            audit_confidence=max(0.0, min(1.0, confidence)),
            cleanlab_issue_count=len(suspicious_ids),
        )
