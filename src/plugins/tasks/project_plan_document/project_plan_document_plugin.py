"""
项目计划文档插件

用于非插件项目的任务发布前置条件。
将项目信息按照1,2,3,4,5五个部分组织，然后交给任务系统。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum
import uuid

from pydantic import Field

from zentex.plugins.contracts import (
    FunctionalPluginSpec,
    PluginHealthStatus,
    PluginLifecycleStatus,
)


class TaskCategory(str, Enum):
    """任务类别 - 用于区分插件vs普通项目"""
    PLUGIN_UPGRADE = "plugin_upgrade"
    PLUGIN_CREATE = "plugin_create"
    PROJECT_FEATURE = "project_feature"
    PROJECT_REFACTOR = "project_refactor"
    PROJECT_INFRASTRUCTURE = "project_infrastructure"
    RESEARCH = "research"
    MAINTENANCE = "maintenance"


class RiskPriority(str, Enum):
    """风险优先级"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class RiskItem:
    """风险项"""
    id: str = field(default_factory=lambda: f"RISK-{uuid.uuid4().hex[:8]}")
    title: str = ""
    description: str = ""
    probability: str = "medium"
    impact: str = "medium"
    priority: RiskPriority = RiskPriority.MEDIUM
    mitigation_strategy: str = ""
    contingency_plan: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "probability": self.probability,
            "impact": self.impact,
            "priority": self.priority.value if isinstance(self.priority, RiskPriority) else self.priority,
            "mitigation_strategy": self.mitigation_strategy,
            "contingency_plan": self.contingency_plan,
        }


@dataclass
class Milestone:
    """项目里程碑"""
    id: str = field(default_factory=lambda: f"MS-{uuid.uuid4().hex[:8]}")
    name: str = ""
    description: str = ""
    target_date: datetime = field(default_factory=datetime.now)
    deliverables: List[str] = field(default_factory=list)
    success_criteria: List[str] = field(default_factory=list)
    key_metrics: Dict[str, Any] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "target_date": self.target_date.isoformat(),
            "deliverables": self.deliverables,
            "success_criteria": self.success_criteria,
            "key_metrics": self.key_metrics,
            "dependencies": self.dependencies,
        }


@dataclass
class ProjectPlanDocument:
    """
    项目计划文档 - 按照 1,2,3,4,5 五个部分组织
    
    第1部分: 基本信息
    第2部分: 项目计划
    第3部分: 整体项目目标
    第4部分: 里程碑
    第5部分: 风险点
    """
    id: str = field(default_factory=lambda: f"PLAN-{uuid.uuid4().hex[:8]}")
    
    # 第1部分: 基本信息
    part1_project_name: str = ""
    part1_description: str = ""
    part1_task_category: str = TaskCategory.PROJECT_FEATURE.value
    part1_version: str = "1.0.0"
    
    # 第2部分: 项目计划
    part2_start_date: Optional[datetime] = None
    part2_end_date: Optional[datetime] = None
    part2_team_members: List[str] = field(default_factory=list)
    part2_estimated_total_hours: float = 0
    part2_resource_requirements: List[str] = field(default_factory=list)
    part2_budget: Optional[str] = None
    part2_external_dependencies: List[str] = field(default_factory=list)
    
    # 第3部分: 整体项目目标
    part3_business_goals: List[str] = field(default_factory=list)
    part3_technical_goals: List[str] = field(default_factory=list)
    part3_success_metrics: List[str] = field(default_factory=list)
    part3_acceptance_criteria: List[str] = field(default_factory=list)
    
    # 第4部分: 里程碑
    part4_milestones: List[Milestone] = field(default_factory=list)
    
    # 第5部分: 风险点
    part5_risks: List[RiskItem] = field(default_factory=list)
    
    # 元数据
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    def is_plugin_task(self) -> bool:
        """检查是否为插件任务"""
        return self.part1_task_category in [
            TaskCategory.PLUGIN_UPGRADE.value,
            TaskCategory.PLUGIN_CREATE.value,
        ]
    
    def add_milestone(self, milestone: Milestone) -> None:
        """添加里程碑"""
        self.part4_milestones.append(milestone)
    
    def add_risk(self, risk: RiskItem) -> None:
        """添加风险项"""
        self.part5_risks.append(risk)
    
    def validate_document(self) -> Tuple[bool, List[str]]:
        """验证文档完整性"""
        errors = []
        
        # 第1部分验证
        if not self.part1_project_name:
            errors.append("第1部分: 项目名称不能为空")
        if not self.part1_description:
            errors.append("第1部分: 项目描述不能为空")
        
        # 第2部分验证
        if not self.part2_start_date or not self.part2_end_date:
            errors.append("第2部分: 开始和结束日期不能为空")
        if not self.part2_team_members:
            errors.append("第2部分: 团队成员不能为空")
        if self.part2_estimated_total_hours <= 0:
            errors.append("第2部分: 总工时必须大于0")
        
        # 第3部分验证
        if not self.part3_business_goals:
            errors.append("第3部分: 业务目标不能为空")
        if not self.part3_success_metrics:
            errors.append("第3部分: 成功指标不能为空")
        
        # 第4部分验证
        if not self.part4_milestones:
            errors.append("第4部分: 至少需要一个里程碑")
        for ms in self.part4_milestones:
            if not ms.deliverables:
                errors.append(f"第4部分: 里程碑 '{ms.name}' 需要交付物")
            if not ms.success_criteria:
                errors.append(f"第4部分: 里程碑 '{ms.name}' 需要成功标准")
        
        # 第5部分验证
        if not self.part5_risks:
            errors.append("第5部分: 至少需要识别一个风险项")
        
        return len(errors) == 0, errors
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "part1": {
                "project_name": self.part1_project_name,
                "description": self.part1_description,
                "task_category": self.part1_task_category,
                "version": self.part1_version,
            },
            "part2": {
                "start_date": self.part2_start_date.isoformat() if self.part2_start_date else None,
                "end_date": self.part2_end_date.isoformat() if self.part2_end_date else None,
                "team_members": self.part2_team_members,
                "estimated_total_hours": self.part2_estimated_total_hours,
                "resource_requirements": self.part2_resource_requirements,
                "budget": self.part2_budget,
                "external_dependencies": self.part2_external_dependencies,
            },
            "part3": {
                "business_goals": self.part3_business_goals,
                "technical_goals": self.part3_technical_goals,
                "success_metrics": self.part3_success_metrics,
                "acceptance_criteria": self.part3_acceptance_criteria,
            },
            "part4": {
                "milestones": [m.to_dict() for m in self.part4_milestones],
            },
            "part5": {
                "risks": [r.to_dict() for r in self.part5_risks],
            },
            "metadata": {
                "created_at": self.created_at.isoformat(),
                "updated_at": self.updated_at.isoformat(),
            },
        }


class ProjectPlanDocumentPlugin(FunctionalPluginSpec):
    behavior_key: str = "tasks.project_plan_document"
    display_name: str = "Project Plan Document"
    description: str = "Validate and shape project plan documents for task generation."
    capability_tags: List[str] = [
        "tasks.project_plan_document",
        "tasks.project_plan_validation",
        "tasks.project_plan_template",
    ]

    @classmethod
    def plugin_kind(cls) -> str:
        return "project_plan_document"

    def execute(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        action = str(parameters.get("action") or "template").strip().lower()
        if action == "template":
            return {
                "status": "ok",
                "document": ProjectPlanDocument().to_dict(),
            }

        document = ProjectPlanDocument(
            part1_project_name=str(parameters.get("project_name") or ""),
            part1_description=str(parameters.get("description") or ""),
            part1_task_category=str(parameters.get("task_category") or TaskCategory.PROJECT_FEATURE.value),
            part2_team_members=list(parameters.get("team_members") or []),
            part2_estimated_total_hours=float(parameters.get("estimated_total_hours") or 0),
            part3_business_goals=list(parameters.get("business_goals") or []),
            part3_success_metrics=list(parameters.get("success_metrics") or []),
            part4_milestones=list(parameters.get("milestones") or []),
            part5_risks=list(parameters.get("risks") or []),
        )
        is_valid, errors = document.validate_document()
        return {
            "status": "ok" if is_valid else "invalid",
            "valid": is_valid,
            "errors": errors,
            "document": document.to_dict(),
        }


# Trigger model reconstruction for Pydantic v2
ProjectPlanDocumentPlugin.model_rebuild()


def factory(*args: Any, **kwargs: Any) -> ProjectPlanDocumentPlugin:
    """Plugin factory for management service instantiation."""
    # Ensure mandatory fields are present even if called with empty kwargs
    kwargs.setdefault("plugin_id", "project_plan_document")
    kwargs.setdefault("version", "1.0.0")
    kwargs.setdefault("feature_code", "tasks.project_plan.document")
    kwargs.setdefault("lifecycle_status", PluginLifecycleStatus.ACTIVE)
    kwargs.setdefault("rollback_conditions", ["project_plan_document_regression"])
    
    return ProjectPlanDocumentPlugin(**kwargs)


def build_project_plan_document_plugin(
    *,
    plugin_id: str = "project_plan_document",
    version: str = "1.0.0",
    lifecycle_status: PluginLifecycleStatus = PluginLifecycleStatus.CANDIDATE,
) -> ProjectPlanDocumentPlugin:
    return ProjectPlanDocumentPlugin(
        plugin_id=plugin_id,
        version=version,
        feature_code="tasks.project_plan.document",
        is_concurrency_safe=True,
        lifecycle_status=lifecycle_status,
        health_status=PluginHealthStatus.HEALTHY,
        rollback_conditions=["project_plan_document_regression"],
        revocation_reasons=["reserved_for_runtime_audit"],
    )


ProjectPlanDocumentPlugin.model_rebuild()


def generate_markdown_report(doc: ProjectPlanDocument) -> str:
    """生成Markdown格式的项目计划报告 (Refactored from misplaced method)"""
    lines = []
    lines.append(f"# 项目计划文档: {doc.part1_project_name}")
    lines.append(f"版本: {doc.part1_version} | 创建时间: {doc.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    
    # 第1部分
    lines.append("## 第1部分: 基本信息")
    lines.append(f"- **项目名称**: {doc.part1_project_name}")
    lines.append(f"- **任务类别**: {doc.part1_task_category}")
    lines.append(f"- **描述**: {doc.part1_description}")
    lines.append("")
    
    # 第2部分
    lines.append("## 第2部分: 项目计划")
    if doc.part2_start_date:
        lines.append(f"- **开始日期**: {doc.part2_start_date.strftime('%Y-%m-%d')}")
    if doc.part2_end_date:
        lines.append(f"- **结束日期**: {doc.part2_end_date.strftime('%Y-%m-%d')}")
    lines.append(f"- **总工时**: {doc.part2_estimated_total_hours} 小时")
    lines.append("- **团队成员**:")
    for member in doc.part2_team_members:
        lines.append(f"  - {member}")
    if doc.part2_resource_requirements:
        lines.append("- **资源需求**:")
        for res in doc.part2_resource_requirements:
            lines.append(f"  - {res}")
    if doc.part2_budget:
        lines.append(f"- **预算**: {doc.part2_budget}")
    lines.append("")
    
    # 第3部分
    lines.append("## 第3部分: 整体项目目标")
    lines.append("### 业务目标")
    for goal in doc.part3_business_goals:
        lines.append(f"- {goal}")
    lines.append("### 技术目标")
    for goal in doc.part3_technical_goals:
        lines.append(f"- {goal}")
    lines.append("### 成功指标")
    for metric in doc.part3_success_metrics:
        lines.append(f"- {metric}")
    lines.append("### 验收标准")
    for criteria in doc.part3_acceptance_criteria:
        lines.append(f"- {criteria}")
    lines.append("")
    
    # 第4部分
    lines.append("## 第4部分: 里程碑")
    for i, ms in enumerate(doc.part4_milestones, 1):
        lines.append(f"### 里程碑{i}: {ms.name}")
        lines.append(f"**目标日期**: {ms.target_date.strftime('%Y-%m-%d')}")
        lines.append(f"**描述**: {ms.description}")
        lines.append("**交付物**:")
        for deliverable in ms.deliverables:
            lines.append(f"- {deliverable}")
        lines.append("**成功标准**:")
        for criteria in ms.success_criteria:
            lines.append(f"- {criteria}")
        lines.append("")
    
    # 第5部分
    lines.append("## 第5部分: 风险点")
    for i, risk in enumerate(doc.part5_risks, 1):
        lines.append(f"### 风险{i}: {risk.title}")
        lines.append(f"**优先级**: {risk.priority.value if hasattr(risk.priority, 'value') else risk.priority}")
        lines.append(f"**描述**: {risk.description}")
        lines.append(f"**概率**: {risk.probability} | **影响**: {risk.impact}")
        lines.append(f"**缓解策略**: {risk.mitigation_strategy}")
        lines.append(f"**应急计划**: {risk.contingency_plan}")
        lines.append("")
    
    return "\n".join(lines)
