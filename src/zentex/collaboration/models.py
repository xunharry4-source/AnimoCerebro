from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class AckStatus(str, Enum):
    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"


class VoteDecision(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"
    ABSTAIN = "abstain"


class ConsensusStatus(str, Enum):
    PENDING = "pending"
    PASSED = "passed"
    REJECTED = "rejected"


class PeerBrain(BaseModel):
    model_config = ConfigDict(extra="forbid")

    brain_id: str = Field(min_length=1)
    shared_secret: str = Field(min_length=8)
    endpoint: str | None = None
    trust_score: float = Field(default=1.0, ge=0.0, le=1.0)
    active: bool = True
    registered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SharedExperience(BaseModel):
    model_config = ConfigDict(extra="forbid")

    experience_id: str = Field(default_factory=lambda: str(uuid4()))
    source_brain_id: str = Field(min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)
    nonce: str = Field(default_factory=lambda: uuid4().hex)
    signature: str = Field(min_length=1)
    accepted_to_core_memory: bool = False
    quarantine_reason: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DeliveryAck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ack_id: str = Field(default_factory=lambda: str(uuid4()))
    message_id: str = Field(min_length=1)
    target_brain_id: str = Field(min_length=1)
    transport_mode: Literal["http", "mailbox"]
    status: AckStatus = AckStatus.PENDING
    attempts: int = Field(default=0, ge=0)
    error: str | None = None
    delivered_at: datetime | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ConsensusProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal_id: str = Field(default_factory=lambda: str(uuid4()))
    proposer_brain_id: str = Field(min_length=1)
    topic: str = Field(min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)
    risk_level: Literal["low", "medium", "high", "critical"] = "medium"
    quorum: int = Field(ge=1)
    status: ConsensusStatus = ConsensusStatus.PENDING
    passed: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ConsensusVote(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vote_id: str = Field(default_factory=lambda: str(uuid4()))
    proposal_id: str = Field(min_length=1)
    voter_brain_id: str = Field(min_length=1)
    decision: VoteDecision
    rationale: str = Field(min_length=1)
    signature: str = Field(min_length=1)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
