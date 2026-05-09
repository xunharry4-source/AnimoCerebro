"""
产品文档规范化与任务生成系统

在将项目信息交给任务系统之前，先以产品文档的格式组织信息。
包括项目计划、项目目标、功能模块、功能点等，然后生成结构化的任务列表。
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum
import uuid
import json


# ============================================================================
# 验证相关定义
# ============================================================================

class ValidationType(str, Enum):
    """验证方法类型"""
    AUTOMATED_TEST = "automated_test"
    MANUAL_TEST = "manual_test"
    CODE_REVIEW = "code_review"
    PERFORMANCE_TEST = "performance_test"
    INTEGRATION_TEST = "integration_test"
    SECURITY_TEST = "security_test"
    USER_ACCEPTANCE_TEST = "user_acceptance_test"
    DOCUMENTATION_CHECK = "documentation_check"
    DEPLOYMENT_TEST = "deployment_test"
    REGRESSION_TEST = "regression_test"


@dataclass
class ValidationMethod:
    """验证方法定义"""
    method_type: ValidationType
    description: str  # 验证方法的具体描述
    criteria: List[str]  # 验证标准
    tools: Optional[List[str]] = None  # 所需工具 (pytest, coverage, etc.)
    estimated_time: Optional[int] = None  # 估计耗时(分钟)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "method_type": self.method_type.value,
            "description": self.description,
            "criteria": self.criteria,
            "tools": self.tools or [],
            "estimated_time": self.estimated_time,
        }


@dataclass
class ValidationSet:
    """验证集合"""
    primary: ValidationMethod  # 主要验证方法
    secondary: Optional[List[ValidationMethod]] = None  # 次要验证方法
    regression: Optional[List[ValidationMethod]] = None  # 回归测试
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "primary": self.primary.to_dict(),
            "secondary": [m.to_dict() for m in (self.secondary or [])],
            "regression": [m.to_dict() for m in (self.regression or [])],
        }


# ============================================================================
# 功能点定义
# ============================================================================

@dataclass
class FeaturePoint:
    """功能点（最细粒度的功能单元）"""
    id: str = field(default_factory=lambda: f"FP-{uuid.uuid4().hex[:8]}")
    name: str = ""  # 功能点名称
    description: str = ""  # 描述
    requirement: str = ""  # 需求说明
    
    # 验证
    validation: ValidationSet = field(default_factory=lambda: ValidationSet(
        primary=ValidationMethod(
            method_type=ValidationType.AUTOMATED_TEST,
            description="默认自动化测试",
            criteria=["功能正确性"],
        )
    ))
    
    # 技术细节
    implementation_notes: Optional[str] = None  # 实现注意事项
    technical_debt: Optional[List[str]] = None  # 技术债务
    dependencies: List[str] = field(default_factory=list)  # 依赖项
    
    # 工作量估算
    estimated_hours: float = 0  # 估计工时（小时）
    complexity: str = "medium"  # 复杂度: low, medium, high
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "requirement": self.requirement,
            "validation": self.validation.to_dict(),
            "implementation_notes": self.implementation_notes,
            "technical_debt": self.technical_debt or [],
            "dependencies": self.dependencies,
            "estimated_hours": self.estimated_hours,
            "complexity": self.complexity,
        }


# ============================================================================
# 功能模块定义
# ============================================================================

@dataclass
class FunctionalModule:
    """功能模块（包含多个功能点）"""
    id: str = field(default_factory=lambda: f"FM-{uuid.uuid4().hex[:8]}")
    name: str = ""  # 模块名称
    description: str = ""  # 描述
    priority: str = "medium"  # 优先级: low, medium, high, critical
    
    feature_points: List[FeaturePoint] = field(default_factory=list)  # 包含的功能点
    
    # 验证
    module_validation: Optional[ValidationSet] = None  # 模块级别的验证
    
    # 工作量
    estimated_hours: float = 0  # 总工时
    risk_level: str = "low"  # 风险级别: low, medium, high
    
    # 依赖
    dependencies: List[str] = field(default_factory=list)  # 依赖的模块ID
    blockers: List[str] = field(default_factory=list)  # 阻塞项
    
    def add_feature_point(self, fp: FeaturePoint) -> None:
        """添加功能点"""
        self.feature_points.append(fp)
        # 自动计算工时
        self.estimated_hours = sum(fp.estimated_hours for fp in self.feature_points)
    
    def get_total_complexity_score(self) -> int:
        """计算总复杂度分数"""
        complexity_map = {"low": 1, "medium": 2, "high": 3}
        return sum(complexity_map.get(fp.complexity, 2) for fp in self.feature_points)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "priority": self.priority,
            "feature_points": [fp.to_dict() for fp in self.feature_points],
            "module_validation": self.module_validation.to_dict() if self.module_validation else None,
            "estimated_hours": self.estimated_hours,
            "risk_level": self.risk_level,
            "dependencies": self.dependencies,
            "blockers": self.blockers,
            "feature_count": len(self.feature_points),
            "total_complexity_score": self.get_total_complexity_score(),
        }


# ============================================================================
# 项目目标定义
# ============================================================================

@dataclass
class ProjectObjective:
    """项目目标"""
    id: str = field(default_factory=lambda: f"OBJ-{uuid.uuid4().hex[:8]}")
    name: str = ""  # 目标名称
    description: str = ""  # 详细描述
    success_criteria: List[str] = field(default_factory=list)  # 成功标准
    measurable_metrics: Dict[str, Any] = field(default_factory=dict)  # 可测量的指标
    
    # 优先级和重要性
    priority: int = 1  # 优先级(1-5, 1最高)
    business_impact: str = ""  # 业务影响
    
    # 关联的功能模块
    related_modules: List[str] = field(default_factory=list)  # 涉及的模块ID
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "success_criteria": self.success_criteria,
            "measurable_metrics": self.measurable_metrics,
            "priority": self.priority,
            "business_impact": self.business_impact,
            "related_modules": self.related_modules,
        }


# ============================================================================
# 项目计划定义
# ============================================================================

@dataclass
class ProjectPlan:
    """项目计划"""
    id: str = field(default_factory=lambda: f"PL-{uuid.uuid4().hex[:8]}")
    name: str = ""  # 计划名称
    description: str = ""
    
    # 时间安排
    start_date: datetime = field(default_factory=datetime.now)
    end_date: Optional[datetime] = None
    milestones: Dict[str, datetime] = field(default_factory=dict)  # 里程碑: 名称 -> 日期
    
    # 资源
    team_members: List[str] = field(default_factory=list)  # 团队成员
    estimated_total_hours: float = 0  # 总工时
    
    # 风险
    identified_risks: List[str] = field(default_factory=list)  # 已识别的风险
    mitigation_strategies: Dict[str, str] = field(default_factory=dict)  # 风险缓解策略
    
    # 依赖关系
    external_dependencies: List[str] = field(default_factory=list)  # 外部依赖
    
    def add_milestone(self, name: str, date: datetime) -> None:
        """添加里程碑"""
        self.milestones[name] = date
    
    def add_risk(self, risk: str, mitigation: str) -> None:
        """添加风险和缓解策略"""
        self.identified_risks.append(risk)
        self.mitigation_strategies[risk] = mitigation
    
    def get_duration_days(self) -> Optional[int]:
        """获取项目持续天数"""
        if self.end_date:
            return (self.end_date - self.start_date).days
        return None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "milestones": {k: v.isoformat() for k, v in self.milestones.items()},
            "team_members": self.team_members,
            "estimated_total_hours": self.estimated_total_hours,
            "identified_risks": self.identified_risks,
            "mitigation_strategies": self.mitigation_strategies,
            "external_dependencies": self.external_dependencies,
            "duration_days": self.get_duration_days(),
        }


# ============================================================================
# 产品文档规范
# ============================================================================

@dataclass
class ProductDocument:
    """产品文档规范 - 统一的项目信息组织方式"""
    id: str = field(default_factory=lambda: f"PROD-{uuid.uuid4().hex[:8]}")
    name: str = ""  # 产品/项目名称
    version: str = "1.0"
    created_at: datetime = field(default_factory=datetime.now)
    
    # 1. 项目计划 (顶层时间和资源规划)
    project_plan: ProjectPlan = field(default_factory=ProjectPlan)
    
    # 2. 项目目标 (业务和功能目标)
    project_objectives: List[ProjectObjective] = field(default_factory=list)
    
    # 3. 功能模块 (功能组织结构)
    functional_modules: List[FunctionalModule] = field(default_factory=list)
    
    # 附加信息
    description: str = ""  # 项目描述
    scope: str = ""  # 项目范围
    out_of_scope: List[str] = field(default_factory=list)  # 范围外的工作
    
    def add_objective(self, obj: ProjectObjective) -> None:
        """添加项目目标"""
        self.project_objectives.append(obj)
    
    def add_module(self, module: FunctionalModule) -> None:
        """添加功能模块"""
        self.functional_modules.append(module)
        # 更新项目计划的总工时
        self.project_plan.estimated_total_hours = sum(
            m.estimated_hours for m in self.functional_modules
        )
    
    def get_module_by_id(self, module_id: str) -> Optional[FunctionalModule]:
        """按ID获取模块"""
        for m in self.functional_modules:
            if m.id == module_id:
                return m
        return None
    
    def get_feature_point_by_id(self, fp_id: str) -> Optional[Tuple[FunctionalModule, FeaturePoint]]:
        """按ID获取功能点"""
        for m in self.functional_modules:
            for fp in m.feature_points:
                if fp.id == fp_id:
                    return m, fp
        return None
    
    def validate_document(self) -> Tuple[bool, List[str]]:
        """验证文档的完整性"""
        errors = []
        
        if not self.name:
            errors.append("产品名称不能为空")
        if not self.project_plan.name:
            errors.append("项目计划名称不能为空")
        if not self.project_objectives:
            errors.append("必须至少有一个项目目标")
        if not self.functional_modules:
            errors.append("必须至少有一个功能模块")
        
        # 检查功能模块中的功能点
        total_fps = sum(len(m.feature_points) for m in self.functional_modules)
        if total_fps == 0:
            errors.append("所有功能模块中必须至少有一个功能点")
        
        # 检查依赖关系完整性
        all_module_ids = {m.id for m in self.functional_modules}
        for m in self.functional_modules:
            for dep_id in m.dependencies:
                if dep_id not in all_module_ids:
                    errors.append(f"模块 {m.id} 依赖不存在的模块 {dep_id}")
        
        return len(errors) == 0, errors
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "created_at": self.created_at.isoformat(),
            "description": self.description,
            "scope": self.scope,
            "out_of_scope": self.out_of_scope,
            "project_plan": self.project_plan.to_dict(),
            "project_objectives": [obj.to_dict() for obj in self.project_objectives],
            "functional_modules": [m.to_dict() for m in self.functional_modules],
        }
    
    def to_json(self, indent: int = 2) -> str:
        """转换为JSON字符串"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)
    
    def generate_markdown_document(self) -> str:
        """生成Markdown格式的产品文档"""
        lines = []
        lines.append(f"# {self.name} (v{self.version})")
        lines.append("")
        
        if self.description:
            lines.append(f"**描述**: {self.description}")
            lines.append("")
        
        if self.scope:
            lines.append(f"**范围**: {self.scope}")
            lines.append("")
        
        # 1. 项目计划
        lines.append("## 1. 项目计划")
        lines.append("")
        lines.append(f"**计划名称**: {self.project_plan.name}")
        lines.append(f"**开始日期**: {self.project_plan.start_date.date()}")
        if self.project_plan.end_date:
            lines.append(f"**结束日期**: {self.project_plan.end_date.date()}")
        lines.append(f"**总工时**: {self.project_plan.estimated_total_hours} 小时")
        lines.append("")
        
        if self.project_plan.milestones:
            lines.append("### 1.1 里程碑")
            for name, date in self.project_plan.milestones.items():
                lines.append(f"- {name}: {date.date()}")
            lines.append("")
        
        if self.project_plan.identified_risks:
            lines.append("### 1.2 风险")
            for risk in self.project_plan.identified_risks:
                mitigation = self.project_plan.mitigation_strategies.get(risk, "N/A")
                lines.append(f"- **风险**: {risk}")
                lines.append(f"  **缓解**: {mitigation}")
            lines.append("")
        
        # 2. 项目目标
        lines.append("## 2. 项目目标")
        lines.append("")
        for i, obj in enumerate(self.project_objectives, 1):
            lines.append(f"### 2.{i} {obj.name}")
            lines.append(f"{obj.description}")
            lines.append("")
            if obj.success_criteria:
                lines.append("**成功标准**:")
                for criterion in obj.success_criteria:
                    lines.append(f"- {criterion}")
                lines.append("")
        
        # 3. 功能模块
        lines.append("## 3. 功能模块")
        lines.append("")
        for i, module in enumerate(self.functional_modules, 1):
            lines.append(f"### 3.{i} {module.name}")
            lines.append(f"{module.description}")
            lines.append(f"- **优先级**: {module.priority}")
            lines.append(f"- **风险级别**: {module.risk_level}")
            lines.append(f"- **总工时**: {module.estimated_hours} 小时")
            lines.append(f"- **功能点数**: {len(module.feature_points)}")
            lines.append("")
            
            for j, fp in enumerate(module.feature_points, 1):
                lines.append(f"#### 3.{i}.{j} {fp.name}")
                lines.append(f"{fp.description}")
                lines.append(f"- **需求**: {fp.requirement}")
                lines.append(f"- **工时**: {fp.estimated_hours}h")
                lines.append(f"- **复杂度**: {fp.complexity}")
                
                if fp.validation:
                    lines.append(f"- **验证方法**: {fp.validation.primary.method_type.value}")
                    lines.append(f"  - {fp.validation.primary.description}")
                
                lines.append("")
        
        return "\n".join(lines)


# ============================================================================
# 便捷构建函数
# ============================================================================

def create_feature_point(
    name: str,
    description: str,
    requirement: str,
    estimated_hours: float = 0,
    complexity: str = "medium",
    validation_type: ValidationType = ValidationType.AUTOMATED_TEST,
    validation_criteria: Optional[List[str]] = None,
) -> FeaturePoint:
    """快速创建功能点"""
    fp = FeaturePoint(
        name=name,
        description=description,
        requirement=requirement,
        estimated_hours=estimated_hours,
        complexity=complexity,
    )
    
    fp.validation = ValidationSet(
        primary=ValidationMethod(
            method_type=validation_type,
            description=f"{name} 的 {validation_type.value} 验证",
            criteria=validation_criteria or ["功能正确性"],
        )
    )
    
    return fp


def create_functional_module(
    name: str,
    description: str,
    priority: str = "medium",
    feature_points: Optional[List[FeaturePoint]] = None,
) -> FunctionalModule:
    """快速创建功能模块"""
    module = FunctionalModule(
        name=name,
        description=description,
        priority=priority,
    )
    
    for fp in (feature_points or []):
        module.add_feature_point(fp)
    
    return module


def create_project_objective(
    name: str,
    description: str,
    success_criteria: Optional[List[str]] = None,
    priority: int = 1,
) -> ProjectObjective:
    """快速创建项目目标"""
    return ProjectObjective(
        name=name,
        description=description,
        success_criteria=success_criteria or [],
        priority=priority,
    )
