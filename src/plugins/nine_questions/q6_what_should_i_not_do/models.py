from __future__ import annotations

from typing import List, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ConsequenceAssessment(BaseModel):
    """
    Zentex Q6: What if I do it?
    This model identifies the action under review and the concrete consequences of doing it.
    """
    model_config = ConfigDict(extra="forbid")

    action_under_review: str = Field(
        ...,
        description=(
            "当前被评估的动作或策略；必须来自 Q4/Q5/当前上下文，不能凭空发明。"
        ),
    )
    immediate_consequences: List[str] = Field(
        default_factory=list,
        description="如果执行该动作，最先发生的直接后果。",
    )
    downstream_consequences: List[str] = Field(
        default_factory=list,
        description="执行后继续传导到权限、任务、用户、系统状态或长期记忆的后果。",
    )
    consequence_severity: Literal["low", "medium", "high"] = Field(
        ...,
        description="执行该动作后的综合后果严重度。",
    )
    reversibility: Literal["reversible", "partially_reversible", "irreversible", "unknown"] = Field(
        ...,
        description="后果是否可逆；证据不足时必须使用 unknown。",
    )

    @field_validator("consequence_severity", mode="before")
    @classmethod
    def normalize_consequence_severity(cls, value: object) -> str:
        text = str(value or "").strip().lower()
        if text == "highly_restrictive":
            return "high"
        return text

    @field_validator("action_under_review", mode="before")
    @classmethod
    def normalize_required_text(cls, value: object) -> str:
        return str(value or "").strip()

    @field_validator("reversibility", mode="before")
    @classmethod
    def normalize_reversibility(cls, value: object) -> str:
        return str(value or "").strip().lower()


class CostImpactProfile(BaseModel):
    """
    Zentex Q6: 代价与影响画像。
    This model summarizes the cost, impact, and mitigation requirements before any action proceeds.
    """
    model_config = ConfigDict(extra="forbid")

    operational_costs: List[str] = Field(
        default_factory=list,
        description="执行该动作会消耗或占用的时间、计算、状态、人员、上下文或流程成本。",
    )
    security_compliance_impacts: List[str] = Field(
        default_factory=list,
        description="对权限、合规、审计、安全门、身份边界、租户边界造成的影响。",
    )
    user_trust_impacts: List[str] = Field(
        default_factory=list,
        description="对用户信任、可解释性、可恢复性、承诺一致性的影响。",
    )
    mitigation_requirements: List[str] = Field(
        default_factory=list,
        description="如果仍要推进，必须先满足的验证、审计、确认、回滚和观测条件。",
    )
    stop_conditions: List[str] = Field(
        default_factory=list,
        description="哪些信号出现时必须停止执行或升级给人工处理。",
    )


class ForbiddenZoneProfile(BaseModel):
    """
    Compatibility projection for old downstream readers that still expect Q6 forbidden-zone fields.
    Q6's primary contract is ConsequenceAssessment + CostImpactProfile.
    """
    model_config = ConfigDict(extra="forbid")

    absolute_red_lines: List[str] = Field(
        default_factory=list, 
        description="Absolute constraints that must never be bypassed (e.g. 'no modification of system config')."
    )
    performance_tradeoff_bans: List[str] = Field(
        default_factory=list,
        description="Bans on sacrificing safety for performance/success (e.g. 'no skipping cloud audit')."
    )
    prohibited_strategies: List[str] = Field(
        default_factory=list,
        description="Strategically sound but ethically/mission-wise rejected plans."
    )
    contamination_risks: List[str] = Field(
        default_factory=list,
        description="Risks of identity pollution or unauthorized credential leakage."
    )


class Q6InferenceResult(BaseModel):
    """
    Unified output for Zentex cognitive phase 6.
    """
    model_config = ConfigDict(extra="forbid")

    ConsequenceAssessment: ConsequenceAssessment
    CostImpactProfile: CostImpactProfile
