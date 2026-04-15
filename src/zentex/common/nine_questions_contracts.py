from __future__ import annotations
from typing import Any, Union, List, Optional, Dict
from pydantic import BaseModel, ConfigDict, Field

# ── Cognitive Evidence Models ──────────────────────────────────────────

class Q1StructureTreeRow(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    row_id: str
    path: str
    label: str
    depth: int = 0
    kind: str = "directory"
    file_count: int | None = None
    summary: str | None = None

class Q1CandidateGroupDetail(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    group_id: str
    label: str
    file_count: int | None = None
    summary: str | None = None

class Q1RiskFileDetail(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    path: str
    severity: str | None = None
    reason: str | None = None

class Q1WorkspaceSampleSummary(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True)
    path: str | None = None
    file: str | None = None
    title: str | None = None
    header: str | None = None
    summary: str | None = None
    snippet: str | None = None

class Q1LongTextEvidence(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    evidence_id: str
    label: str
    kind: str
    source: str
    path: str | None = None
    text: str

class Q1PhysicalAndEnvironmentEvidence(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    environment_event: Dict[str, Any] = Field(default_factory=dict)
    physical_host_state: Dict[str, Any] = Field(default_factory=dict)
    memory_pressure: str | None = None
    network_health: str | None = None
    memory_pressure_status: str = "unknown"
    network_health_status: str = "unknown"
    environment_summary: List[str] = Field(default_factory=list)

class Q1WorkspaceStructureEvidence(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    directory_hierarchy_summary: str | None = None
    top_level_dirs: List[str] = Field(default_factory=list)
    file_total_count: int | None = None
    suffix_distribution: Dict[str, int] = Field(default_factory=dict)
    high_frequency_filename_keywords: Dict[str, int] = Field(default_factory=dict)
    candidate_groups: List[str] = Field(default_factory=list)
    obvious_risk_files: List[str] = Field(default_factory=list)
    directory_tree_rows: List[Q1StructureTreeRow] = Field(default_factory=list)
    candidate_group_details: List[Q1CandidateGroupDetail] = Field(default_factory=list)
    obvious_risk_file_details: List[Q1RiskFileDetail] = Field(default_factory=list)
    analyzer_snapshot: Dict[str, Any] = Field(default_factory=dict)

class Q1WorkspaceContentSamplingEvidence(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    sampled_file_summaries: List[Q1WorkspaceSampleSummary] = Field(default_factory=list)
    log_anomaly_snippets: List[str] = Field(default_factory=list)
    long_text_evidence: List[Q1LongTextEvidence] = Field(default_factory=list)
    sample_count: int = 0
    anomaly_count: int = 0
    sampler_snapshot: Dict[str, Any] = Field(default_factory=dict)

class Q1PreprocessedEvidence(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    physical_and_environment: Q1PhysicalAndEnvironmentEvidence
    workspace_structure: Q1WorkspaceStructureEvidence
    workspace_content_sampling: Q1WorkspaceContentSamplingEvidence

# ── Inference View Models ─────────────────────────────────────────────

class WorkspaceDomainInferenceView(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    primary_domain: str
    secondary_domains: List[str] = Field(default_factory=list)
    confidence: float
    reasoning_summary: str
    uncertainties: List[str] = Field(default_factory=list)
    suggested_first_step: str
    host_runtime_type: str | None = None
    host_runtime_reason: str | None = None

# ── Core Report Models ────────────────────────────────────────────────

class MountedPluginInfo(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    plugin_id: str
    display_name: str
    source_kind: str  # "base", "patch"
    version: str
    description: str
    function_description: str
    status: str  # "active", "candidate", "degraded", "revoked"

class NineQuestionReportItem(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True)
    question_id: str
    title: str
    tool_id: str
    summary: str
    confidence: float
    result: Any
    context_updates: Dict[str, Any] = Field(default_factory=dict)
    trace_id: str
    timestamp: str
    cache_status: str = "未知"
    provider_name: str | None = None
    mounted_plugins: List[MountedPluginInfo] = Field(default_factory=list)
    # ... Simplified view for core integration ...
