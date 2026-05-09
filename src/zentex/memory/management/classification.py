from __future__ import annotations

"""
Memory classification layer / 记忆分类与分层。

Defines the two orthogonal classification axes applied to every EnhancedMemoryRecord:

1. MemoryTier  — hot / warm / cold  (生命周期分层)
   Mirrors the hot-zone / warm-zone / cold-zone budget model described in G39.
   Tier controls retention policy, compaction scheduling, and recall cost.

2. EmotionalValence — 8 affect categories  (情感维度分类)
   Captures the affect signal associated with the experience, aligned with the
   "类情绪信号" described in G31A / AutobiographicalMemory / Outcome Binding.
   Valence + intensity drive memory promotion priority and forgetting eligibility.

Uniqueness contract
-------------------
Every EnhancedMemoryRecord must carry a `content_hash` computed from its stable
semantic fields (layer / kind / title / content).  This hash is the external-
facing immutability proof: the same experience ingested twice yields the same
hash, so the local store can reject true duplicates.

From the AI's own perspective, records are mutable through the internal
governance pipeline (G38 nine-gate checks, G39 compaction, B8 consolidation).
The append-only audit trail in MemoryAuditEvent records every such internal
change, preserving full provenance while allowing the brain to evolve.

Key invariants:
  - content_hash is computed once at creation and never recomputed on reload.
  - MemoryTier is assigned at write time; the consolidation engine promotes or
    demotes records by writing a governance state transition, NOT by mutating
    the original record.
  - Emotional valence is inferred heuristically at ingestion time and may be
    corrected by a human operator through update_management_state().
"""

import hashlib
import json
from enum import Enum
from typing import FrozenSet


# ---------------------------------------------------------------------------
# Tier
# ---------------------------------------------------------------------------

class MemoryTier(str, Enum):
    """Three-tier lifecycle model for memory records (G39).

    HOT   — runtime_log zone; < 14 days; freshly ingested experiences.
    WARM  — reflection_record zone; 14–180 days; validated patterns and lessons.
    COLD  — archive zone; > 180 days; compressed strategy patches and anchors.
    """

    HOT = "hot"
    WARM = "warm"
    COLD = "cold"


# ---------------------------------------------------------------------------
# Emotional valence
# ---------------------------------------------------------------------------

class EmotionalValence(str, Enum):
    """Affect taxonomy for memory records (类情绪信号, G31A / AutobiographicalMemory).

    Positive family  — reinforce the behaviour that produced the experience.
    Negative family  — signal that the behaviour should be modified.
    Neutral          — factual record with no strong affect.
    Conflicted       — contradictory signals; requires resolution before acting.
    """

    # ── positive family ──────────────────────────────────────────────────
    TRIUMPH = "triumph"        # 凯旋 – major success, goal achieved
    RELIEF = "relief"          # 如释重负 – risk resolved, constraint lifted
    CURIOSITY = "curiosity"    # 好奇 – novel pattern, interesting discovery

    # ── negative family ──────────────────────────────────────────────────
    CONCERN = "concern"        # 担忧 – potential risk, uncertainty detected
    FRUSTRATION = "frustration"  # 挫败 – repeated failure, blocked progress
    REGRET = "regret"          # 后悔 – missed opportunity, poor decision

    # ── neutral ──────────────────────────────────────────────────────────
    NEUTRAL = "neutral"        # 中性 – factual record, no strong affect

    # ── special ──────────────────────────────────────────────────────────
    CONFLICTED = "conflicted"  # 冲突 – contradictory signals, unresolved tension


# ---------------------------------------------------------------------------
# Transcript event classification
# ---------------------------------------------------------------------------

# Transcript entry types that carry genuine knowledge worth elevating to memory.
# All other entry types are raw runtime log events (low signal / high noise).
MEMORY_WORTHY_EVENTS: FrozenSet[str] = frozenset({
    "decision_synthesized",
    "reflection_persisted",
    "consolidation_completed",
    "consolidation_failed",
    "human_intervention_applied",
    "nine_question_state_updated",
    "learning_engine_event",
    "plugin_audit_event",
})

# Default (valence, affect_intensity) for known transcript entry types.
# Rules are intentionally simple (no LLM needed).  The consolidation engine
# or a human operator may override via update_management_state().
_TRANSCRIPT_VALENCE_MAP: dict[str, tuple[str, float]] = {
    # decisions
    "decision_synthesized": (EmotionalValence.NEUTRAL, 0.45),
    # reflections — outcome unknown at projection time; default neutral mid-weight
    "reflection_persisted": (EmotionalValence.NEUTRAL, 0.40),
    # consolidation
    "consolidation_completed": (EmotionalValence.RELIEF, 0.35),
    "consolidation_failed": (EmotionalValence.CONCERN, 0.55),
    # human oversight — high-weight negative; human intervened for a reason
    "human_intervention_applied": (EmotionalValence.CONCERN, 0.70),
    # nine-question evolution
    "nine_question_state_updated": (EmotionalValence.CURIOSITY, 0.40),
    # learning events
    "learning_engine_event": (EmotionalValence.CURIOSITY, 0.50),
    # provider failures
    "model_provider_failed": (EmotionalValence.FRUSTRATION, 0.45),
    # audit
    "plugin_audit_event": (EmotionalValence.NEUTRAL, 0.30),
}

# Upgrade record outcome → valence mapping.
_UPGRADE_OUTCOME_VALENCE_MAP: dict[str, tuple[str, float]] = {
    "success": (EmotionalValence.TRIUMPH, 0.65),
    "partial_success": (EmotionalValence.RELIEF, 0.45),
    "failure": (EmotionalValence.FRUSTRATION, 0.60),
    "rollback": (EmotionalValence.REGRET, 0.55),
    "reverted": (EmotionalValence.REGRET, 0.50),
    "rejected": (EmotionalValence.CONCERN, 0.40),
    "pending": (EmotionalValence.NEUTRAL, 0.20),
}


def valence_for_transcript_event(
    entry_type: str,
) -> tuple[str, float]:
    """Return (emotional_valence, affect_intensity) for a transcript entry type.

    Falls back to neutral / 0.20 for unknown or low-signal event types.
    """
    return _TRANSCRIPT_VALENCE_MAP.get(entry_type, (EmotionalValence.NEUTRAL, 0.20))


def valence_for_upgrade_outcome(
    status: str,
) -> tuple[str, float]:
    """Return (emotional_valence, affect_intensity) for an upgrade record status."""
    return _UPGRADE_OUTCOME_VALENCE_MAP.get(
        status.lower() if status else "pending",
        (EmotionalValence.NEUTRAL, 0.20),
    )


def tier_for_source(source_kind: str, tags: list[str]) -> str:
    """Infer a sensible initial MemoryTier from the record's source and tags.

    All new records start HOT; the consolidation engine demotes to WARM/COLD.
    Only records loaded from an existing store that already carries a tier field
    should skip this function.
    """
    if "cold" in tags or "archive" in tags:
        return MemoryTier.COLD
    if "warm" in tags or "reflection" in tags or "experience" in tags:
        return MemoryTier.WARM
    return MemoryTier.HOT


# ---------------------------------------------------------------------------
# Content hash (唯一性 / immutability proof)
# ---------------------------------------------------------------------------

def compute_content_hash(
    memory_layer: str,
    source_kind: str,
    title: str,
    content: str,
) -> str:
    """Return a deterministic SHA-256 hex digest over the record's stable semantic fields.

    The hash is computed over the canonical JSON serialisation of the four
    fields that define *what* the memory contains, independent of *when* or
    *where* it was created.

    Two EnhancedMemoryRecord objects with the same (layer, kind, title, content)
    will produce the same hash and are therefore considered identical experiences.
    The local store uses this hash to reject true duplicates at ingestion time,
    enforcing the uniqueness invariant without relying on UUIDs.

    From the external perspective this hash is also the immutability proof: any
    tampering with the record fields will produce a different hash, making
    tampering detectable.  Internally the AI governance pipeline records every
    authorised state transition in the MemoryAuditEvent ledger rather than
    mutating the original record.
    """
    canonical = json.dumps(
        {
            "memory_layer": memory_layer,
            "source_kind": source_kind,
            "title": title,
            "content": content,
        },
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
