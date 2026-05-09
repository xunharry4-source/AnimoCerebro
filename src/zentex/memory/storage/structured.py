from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

"""
Typed entity and relationship schemas for structured knowledge representation.

职责:
  - 定义 Pydantic-based 类型化实体（Person、Organization、Concept 等）。
  - 定义类型化关系（WORKS_FOR、LIVES_IN、CAUSES 等）。
  - 提供基于规则的轻量级实体提取器（无 LLM；仅用于结构化初步标注）。
  - 提供 EntityRegistry：集中管理已知实体，避免重复创建。
  - 与 KuzuGraphMemoryClient 解耦：结构化模型可独立使用，也可序列化后写入 Kuzu。

不负责:
  - 高置信度的语义实体识别（需 LLM；由 EnhancedMemoryService 扩展）。
  - 物理持久化（由调用方或 kuzu_backend.py 负责）。
  - 多模态内容处理（图片、音频；见 multimodal 扩展点）。
"""

import re
import threading
from datetime import datetime, timezone
UTC = timezone.utc
from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Entity types
# ---------------------------------------------------------------------------

class EntityType(str, Enum):
    PERSON = "Person"
    ORGANIZATION = "Organization"
    LOCATION = "Location"
    CONCEPT = "Concept"
    TECHNOLOGY = "Technology"
    EVENT = "Event"
    ARTIFACT = "Artifact"       # Document, code, file, etc.
    AGENT = "Agent"             # AI agent or software agent
    UNKNOWN = "Unknown"


# ---------------------------------------------------------------------------
# Relationship types
# ---------------------------------------------------------------------------

class RelationshipType(str, Enum):
    # Person ↔ Organization
    WORKS_FOR = "WORKS_FOR"
    MANAGES = "MANAGES"
    FOUNDED = "FOUNDED"
    MEMBER_OF = "MEMBER_OF"

    # Person / Agent ↔ Location
    LIVES_IN = "LIVES_IN"
    LOCATED_IN = "LOCATED_IN"
    OPERATES_IN = "OPERATES_IN"

    # Causal / temporal
    CAUSES = "CAUSES"
    PRECEDES = "PRECEDES"
    FOLLOWS = "FOLLOWS"
    ENABLES = "ENABLES"
    PREVENTS = "PREVENTS"

    # Knowledge
    KNOWS = "KNOWS"
    KNOWS_ABOUT = "KNOWS_ABOUT"
    CONTRADICTS = "CONTRADICTS"
    SUPPORTS = "SUPPORTS"

    # Technology
    USES = "USES"
    IMPLEMENTS = "IMPLEMENTS"
    DEPENDS_ON = "DEPENDS_ON"

    # Generic
    RELATED_TO = "RELATED_TO"
    PART_OF = "PART_OF"
    INSTANCE_OF = "INSTANCE_OF"


# ---------------------------------------------------------------------------
# Typed entity model
# ---------------------------------------------------------------------------

class TypedEntity(BaseModel):
    """A typed, identifiable entity extracted from memory content."""

    model_config = ConfigDict(extra="allow")

    entity_id: str = Field(default_factory=lambda: str(uuid4()))
    entity_type: str  # One of EntityType values
    name: str
    aliases: list[str] = Field(default_factory=list)
    description: str = Field(default="")
    source_memory_id: Optional[str] = None
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    first_seen: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_seen: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict = Field(default_factory=dict)

    def canonical_name(self) -> str:
        return self.name.strip().lower()


# ---------------------------------------------------------------------------
# Typed relationship model
# ---------------------------------------------------------------------------

class TypedRelationship(BaseModel):
    """A typed, directed relationship between two entities."""

    model_config = ConfigDict(extra="allow")

    relationship_id: str = Field(default_factory=lambda: str(uuid4()))
    relationship_type: str  # One of RelationshipType values
    source_entity_id: str
    target_entity_id: str
    source_memory_id: Optional[str] = None
    # Temporal validity (Graphiti-inspired)
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    description: str = Field(default="")
    metadata: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def is_valid_at(self, dt: datetime) -> bool:
        if self.valid_from and dt < self.valid_from:
            return False
        if self.valid_to and dt > self.valid_to:
            return False
        return True


# ---------------------------------------------------------------------------
# Entity registry
# ---------------------------------------------------------------------------

class EntityRegistry:
    """
    Centralised store for TypedEntity objects.

    Deduplicates by canonical name + entity_type.
    Thread-safe.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entities: dict[str, TypedEntity] = {}           # entity_id → entity
        self._name_index: dict[tuple[str, str], str] = {}    # (canonical_name, type) → entity_id

    def register(self, entity: TypedEntity) -> TypedEntity:
        """Register an entity; return existing entity if name+type already known."""
        key = (entity.canonical_name(), entity.entity_type)
        with self._lock:
            if key in self._name_index:
                existing_id = self._name_index[key]
                return self._entities[existing_id]
            self._entities[entity.entity_id] = entity
            self._name_index[key] = entity.entity_id
        return entity

    def get(self, entity_id: str) -> Optional[TypedEntity]:
        with self._lock:
            return self._entities.get(entity_id)

    def find_by_name(self, name: str, entity_type: Optional[str] = None) -> list[TypedEntity]:
        canonical = name.strip().lower()
        with self._lock:
            results = []
            for (cn, et), eid in self._name_index.items():
                if cn == canonical and (entity_type is None or et == entity_type):
                    entity = self._entities.get(eid)
                    if entity:
                        results.append(entity)
            return results

    def all_entities(self) -> list[TypedEntity]:
        with self._lock:
            return list(self._entities.values())

    def stats(self) -> dict:
        with self._lock:
            by_type: dict[str, int] = {}
            for e in self._entities.values():
                by_type[e.entity_type] = by_type.get(e.entity_type, 0) + 1
            return {"total": len(self._entities), "by_type": by_type}


# ---------------------------------------------------------------------------
# Rule-based entity extractor (no LLM)
# ---------------------------------------------------------------------------

# Simple patterns for bootstrap extraction; not production-grade NER.
_PERSON_PATTERN = re.compile(
    r"\b([A-Z][a-z]+ (?:[A-Z][a-z]+ ){0,1}[A-Z][a-z]+)\b"
)
_LOCATION_PATTERN = re.compile(
    r"\b(?:Union[in, Union[at], Union[from], to])\s+([A-Z][a-zA-Z\s]{2,30}(?:Union[City, Union[Town], Union[Province], Union[Country], Region])?)\b"
)
_ORG_PATTERN = re.compile(
    r"\b([A-Z][a-zA-Z\s]{1,30}(?:Union[Inc, Union[Corp], Union[Ltd], Union[LLC], Union[GmbH], Union[Co], Union[Foundation], Union[Institute], Union[University], Team])\.?)\b"
)
_CONCEPT_PATTERN = re.compile(
    r"`([a-zA-Z_][a-zA-Z0-9_]{2,40})`"  # Code identifiers in backticks treated as Concept
)
_TECH_KEYWORDS = frozenset({
    "python", "rust", "golang", "java", "kubernetes", "docker", "redis",
    "postgresql", "mysql", "kafka", "elasticsearch", "react", "vue", "angular",
    "llm", "gpt", "bert", "transformer", "pytorch", "tensorflow",
    "langchain", "langmem", "graphiti", "kuzu", "pydantic", "fastapi",
})


class RuleBasedEntityExtractor:
    """
    Lightweight rule-based extractor that bootstraps typed entities from free text.

    不需要 LLM 调用。适用于预处理和初步标注；生产级 NER 建议替换为 LLM-based 实现。
    """

    def __init__(self, registry: Optional[EntityRegistry] = None) -> None:
        self._registry = registry or EntityRegistry()

    def extract(
        self,
        text: str,
        *,
        source_memory_id: Optional[str] = None,
    ) -> list[TypedEntity]:
        """
        Extract typed entities from free text.

        Returns a deduplicated list of TypedEntity objects registered in the registry.
        """
        entities: list[TypedEntity] = []

        # Persons
        for m in _PERSON_PATTERN.finditer(text):
            e = TypedEntity(
                entity_type=EntityType.PERSON,
                name=m.group(1),
                source_memory_id=source_memory_id,
                confidence=0.6,
            )
            entities.append(self._registry.register(e))

        # Locations
        for m in _LOCATION_PATTERN.finditer(text):
            e = TypedEntity(
                entity_type=EntityType.LOCATION,
                name=m.group(1).strip(),
                source_memory_id=source_memory_id,
                confidence=0.5,
            )
            entities.append(self._registry.register(e))

        # Organizations
        for m in _ORG_PATTERN.finditer(text):
            e = TypedEntity(
                entity_type=EntityType.ORGANIZATION,
                name=m.group(1).strip(),
                source_memory_id=source_memory_id,
                confidence=0.6,
            )
            entities.append(self._registry.register(e))

        # Code/concept identifiers
        for m in _CONCEPT_PATTERN.finditer(text):
            e = TypedEntity(
                entity_type=EntityType.CONCEPT,
                name=m.group(1),
                source_memory_id=source_memory_id,
                confidence=0.8,
            )
            entities.append(self._registry.register(e))

        # Technology keywords (case-insensitive)
        words = re.findall(r"\b\w+\b", text.lower())
        for word in set(words):
            if word in _TECH_KEYWORDS:
                e = TypedEntity(
                    entity_type=EntityType.TECHNOLOGY,
                    name=word,
                    source_memory_id=source_memory_id,
                    confidence=0.9,
                )
                entities.append(self._registry.register(e))

        # Deduplicate by entity_id preserving order.
        seen: set[str] = set()
        unique: list[TypedEntity] = []
        for e in entities:
            if e.entity_id not in seen:
                seen.add(e.entity_id)
                unique.append(e)
        return unique


# ---------------------------------------------------------------------------
# Multi-modal memory placeholder
# ---------------------------------------------------------------------------

class MultimodalMemoryHint(BaseModel):
    """
    Placeholder for multi-modal memory support.

    当前系统只支持文本记忆。未来扩展可在此定义图片、音频、代码片段的
    first-class 记忆格式。本类仅作为设计预留，不参与任何运行逻辑。
    """

    model_config = ConfigDict(extra="forbid")

    hint_id: str = Field(default_factory=lambda: str(uuid4()))
    modality: str  # "text" | "image" | "audio" | "code" | "structured_data"
    reference_uri: str = ""        # URI to external asset (if not inline)
    inline_content: Optional[bytes] = None
    mime_type: str = ""
    description: str = ""
    source_memory_id: Optional[str] = None
