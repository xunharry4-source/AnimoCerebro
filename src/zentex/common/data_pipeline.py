from __future__ import annotations

"""
Shared pandas-based data pipeline primitives for auto-organize maintenance flows.

RESPONSIBILITY:
  - Provide common decay and weighted-tag helpers used by memory, reflection,
    and learning maintenance pipelines.
  - Keep all generic dataframe-independent math in one place.

DOES NOT:
  - Call any LLM
  - Read or write databases
  - Make business decisions such as deletion, promotion, or suspect marking
"""

import math
from collections import defaultdict
from typing import Dict, Iterable, Sequence


def exponential_decay(age_days: float, half_life_days: float = 30.0) -> float:
    """Return an exponential decay weight in the inclusive range [0.0, 1.0]."""
    try:
        age = max(0.0, float(age_days))
        half_life = max(1e-6, float(half_life_days))
    except (TypeError, ValueError):
        return 0.0
    decay_lambda = math.log(2.0) / half_life
    return math.exp(-decay_lambda * age)


def compute_weighted_tag_counts(
    tag_lists: Sequence[Iterable[str]],
    weights: Sequence[float],
) -> Dict[str, float]:
    """Return weighted tag counts sorted by descending weight."""
    totals: dict[str, float] = defaultdict(float)
    for tags, weight in zip(tag_lists, weights):
        try:
            safe_weight = max(0.0, float(weight))
        except (TypeError, ValueError):
            safe_weight = 0.0
        if safe_weight <= 0.0:
            continue
        for raw_tag in tags or []:
            tag = str(raw_tag or "").strip()
            if tag:
                totals[tag] += safe_weight
    return dict(sorted(totals.items(), key=lambda item: (-item[1], item[0])))

