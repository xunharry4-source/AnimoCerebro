"""
产品文档转任务转换器

将产品文档转换为结构化的任务列表和子任务。
确保每个子任务都有明确的验证方法和目标。
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
import uuid

from zentex.tasks.product_document import (
    ProductDocument,
    FunctionalModule,
    FeaturePoint,
    ProjectObjective,
    ValidationMethod,
    ValidationType,
)


# ============================================================================
# 子任务定义
# ============================================================================

@dataclass
class SubTask:
    """子任务定义"""
    id: str = field(default_factory=lambda: f"ST-{uuid.uuid4().hex[:8]}")
    name: str = ""
    description: str = ""
    
    # 所属关系
    parent_task_id: str = ""  # 所属任务ID
    feature_point_id: Optional[str] = None  # 关联的功能点ID
    
    # 执行信息
    assigned_to: Optional[str] = None  # 分配给
    estimated_hours: float = 0
    priority: str = "medium"
    
    # 验证
    verification_method: ValidationType = ValidationType.AUTOMATED_TEST
    verification_description: str = ""
    verification_criteria: List[str] = field(default_factory=list)
    verification_tools: List[str] = field(default_factory=list)
    
    # 成功指标
    success_metrics: Dict[str, Any] = field(default_factory=dict)
    acceptance_criteria: List[str] = field(default_factory=list)
    
    # 依赖
    blocking_subtasks: List[str] = field(default_factory=list)
    blocked_by_subtasks: List[str] = field(default_factory=list)
    
    # 实现细节
    implementation_notes: Optional[str] = None
    technical_requirements: List[str] = field(default_factory=list)
    
    # 状态
    status: str = "pending"  # pending, in_progress, completed
    created_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "parent_task_id": self.parent_task_id,
            "feature_point_id": self.feature_point_id,
            "assigned_to": self.assigned_to,
            "estimated_hours": self.estimated_hours,
            "priority": self.priority,
            "verification": {
                "method": self.verification_method.value,
                "description": self.verification_description,
                "criteria": self.verification_criteria,
                "tools": self.verification_tools,
            },
            "success_metrics": self.success_metrics,
            "acceptance_criteria": self.acceptance_criteria,
            "blocking_subtasks": self.blocking_subtasks,
            "blocked_by_subtasks": self.blocked_by_subtasks,
            "implementation_notes": self.implementation_notes,
            "technical_requirements": self.technical_requirements,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
        }


# ============================================================================
# 任务定义
# ============================================================================

@dataclass
class GeneratedTask:
    """从产品文档生成的任务"""
    id: str = field(default_factory=lambda: f"TASK-{uuid.uuid4().hex[:8]}")
    task_type: str = "feature"  # feature, bug_fix, refactor, infrastructure
    
    # 基本信息
    name: str = ""
    description: str = ""
    objective_id: Optional[str] = None  # 关联的项目目标ID
    module_id: Optional[str] = None  # 所属模块ID
    
    # 执行信息
    priority: str = "medium"  # low, medium, high, critical
    estimated_hours: float = 0
    complexity: str = "medium"  # low, medium, high
    
    # 子任务
    subtasks: List[SubTask] = field(default_factory=list)
    
    # 验证
    module_validation: Optional[ValidationType] = None  # 模块级验证
    module_validation_description: str = ""
    
    # 依赖
    depends_on_tasks: List[str] = field(default_factory=list)
    blocking_tasks: List[str] = field(default_factory=list)
    
    # 时间管理
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    milestone: Optional[str] = None
    
    # 状态
    status: str = "pending"
    created_at: datetime = field(default_factory=datetime.now)
    
    def add_subtask(self, subtask: SubTask) -> None:
        """添加子任务"""
        subtask.parent_task_id = self.id
        self.subtasks.append(subtask)
    
    def get_total_estimated_hours(self) -> float:
        """获取总工时（包括子任务）"""
        return sum(st.estimated_hours for st in self.subtasks)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        module_validation_value = None
        if self.module_validation:
            if hasattr(self.module_validation, 'value'):
                module_validation_value = self.module_validation.value
            else:
                module_validation_value = str(self.module_validation)
        
        return {
            "id": self.id,
            "task_type": self.task_type,
            "name": self.name,
            "description": self.description,
            "objective_id": self.objective_id,
            "module_id": self.module_id,
            "priority": self.priority,
            "estimated_hours": self.estimated_hours,
            "complexity": self.complexity,
            "subtasks": [st.to_dict() for st in self.subtasks],
            "module_validation": module_validation_value,
            "module_validation_description": self.module_validation_description,
            "depends_on_tasks": self.depends_on_tasks,
            "blocking_tasks": self.blocking_tasks,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "milestone": self.milestone,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "subtask_count": len(self.subtasks),
            "total_estimated_hours": self.get_total_estimated_hours(),
        }


# ============================================================================
# 任务生成转换器
# ============================================================================

class ProductDocumentToTaskConverter:
    """从产品文档转换为任务列表的转换器"""
    
    def __init__(self):
        self.generated_tasks: List[GeneratedTask] = []
        self.task_id_map: Dict[str, str] = {}  # module_id -> task_id
    
    def convert(self, product_doc: ProductDocument) -> Tuple[List[GeneratedTask], List[str]]:
        """
        转换产品文档为任务列表
        
        返回: (任务列表, 错误列表)
        """
        errors = []
        
        # 验证产品文档
        is_valid, validation_errors = product_doc.validate_document()
        if not is_valid:
            return [], validation_errors
        
        # 为每个功能模块生成任务
        for module in product_doc.functional_modules:
            task = self._generate_task_from_module(
                module,
                product_doc.project_objectives,
                product_doc.project_plan,
            )
            self.generated_tasks.append(task)
            self.task_id_map[module.id] = task.id
        
        # 构建任务依赖关系
        self._build_task_dependencies(product_doc.functional_modules)
        
        return self.generated_tasks, errors
    
    def _generate_task_from_module(
        self,
        module: FunctionalModule,
        objectives: List[ProjectObjective],
        plan,
    ) -> GeneratedTask:
        """为功能模块生成任务"""
        task = GeneratedTask(
            task_type="feature",
            name=f"实现模块: {module.name}",
            description=module.description,
            module_id=module.id,
            priority=module.priority,
            estimated_hours=module.estimated_hours,
            complexity=self._map_complexity(module.risk_level),
        )
        
        # 关联项目目标
        related_objectives = [
            obj for obj in objectives
            if module.id in obj.related_modules
        ]
        if related_objectives:
            task.objective_id = related_objectives[0].id
        
        # 为每个功能点生成子任务
        for fp in module.feature_points:
            subtask = self._generate_subtask_from_feature_point(fp, module.id)
            task.add_subtask(subtask)
        
        # 设置模块级验证
        if module.module_validation:
            task.module_validation = module.module_validation.primary.method_type
            task.module_validation_description = module.module_validation.primary.description
        
        return task
    
    def _generate_subtask_from_feature_point(
        self,
        fp: FeaturePoint,
        module_id: str,
    ) -> SubTask:
        """为功能点生成子任务"""
        subtask = SubTask(
            name=fp.name,
            description=fp.description,
            feature_point_id=fp.id,
            estimated_hours=fp.estimated_hours,
            priority=self._map_fp_priority(fp.complexity),
        )
        
        # 设置验证信息
        if fp.validation:
            subtask.verification_method = fp.validation.primary.method_type
            subtask.verification_description = fp.validation.primary.description
            subtask.verification_criteria = fp.validation.primary.criteria
            subtask.verification_tools = fp.validation.primary.tools or []
        
        # 设置验收标准
        subtask.acceptance_criteria = [
            f"✓ {fp.description}",
            f"✓ 满足需求: {fp.requirement}",
            "✓ 代码审查通过",
            "✓ 验证测试通过",
        ]
        
        # 设置成功指标
        subtask.success_metrics = {
            "code_coverage": "80%+",
            "test_coverage": "90%+",
            "documentation": "完整",
            "performance": "符合标准",
        }
        
        # 设置实现注意事项
        if fp.implementation_notes:
            subtask.implementation_notes = fp.implementation_notes
        
        # 设置技术需求
        subtask.technical_requirements = fp.dependencies or []
        
        return subtask
    
    def _build_task_dependencies(self, modules: List[FunctionalModule]) -> None:
        """构建任务之间的依赖关系"""
        for module in modules:
            if module.id not in self.task_id_map:
                continue
            
            task = self._find_task_by_module_id(module.id)
            if not task:
                continue
            
            # 处理模块依赖
            for dep_id in module.dependencies:
                if dep_id in self.task_id_map:
                    task.depends_on_tasks.append(self.task_id_map[dep_id])
            
            # 处理阻塞器
            for blocker_id in module.blockers:
                if blocker_id in self.task_id_map:
                    task.blocking_tasks.append(self.task_id_map[blocker_id])
    
    def _find_task_by_module_id(self, module_id: str) -> Optional[GeneratedTask]:
        """按模块ID查找任务"""
        for task in self.generated_tasks:
            if task.module_id == module_id:
                return task
        return None
    
    @staticmethod
    def _map_complexity(risk_level: str) -> str:
        """映射风险级别到复杂度"""
        mapping = {
            "low": "low",
            "medium": "medium",
            "high": "high",
        }
        return mapping.get(risk_level, "medium")
    
    @staticmethod
    def _map_fp_priority(complexity: str) -> str:
        """映射功能点复杂度到优先级"""
        mapping = {
            "low": "low",
            "medium": "medium",
            "high": "high",
        }
        return mapping.get(complexity, "medium")


# ============================================================================
# 任务列表生成器
# ============================================================================

@dataclass
class TaskList:
    """任务列表"""
    id: str = field(default_factory=lambda: f"TL-{uuid.uuid4().hex[:8]}")
    product_document_id: str = ""
    created_from: str = ""  # 来源文档信息
    created_at: datetime = field(default_factory=datetime.now)
    
    tasks: List[GeneratedTask] = field(default_factory=list)
    product_document_data: Optional[Dict[str, Any]] = None  # 保存产品文档数据供查看
    
    def add_task(self, task: GeneratedTask) -> None:
        """添加任务"""
        self.tasks.append(task)
    
    def get_task_by_id(self, task_id: str) -> Optional[GeneratedTask]:
        """按ID获取任务"""
        for task in self.tasks:
            if task.id == task_id:
                return task
        return None
    
    def get_tasks_by_priority(self, priority: str) -> List[GeneratedTask]:
        """按优先级获取任务"""
        return [t for t in self.tasks if t.priority == priority]
    
    def get_tasks_ordered_by_dependencies(self) -> List[GeneratedTask]:
        """获取按依赖关系排序的任务列表"""
        sorted_tasks = []
        visited = set()
        
        def visit(task_id: str) -> None:
            if task_id in visited:
                return
            visited.add(task_id)
            
            task = self.get_task_by_id(task_id)
            if not task:
                return
            
            # 先访问依赖
            for dep_id in task.depends_on_tasks:
                visit(dep_id)
            
            sorted_tasks.append(task)
        
        for task in self.tasks:
            visit(task.id)
        
        return sorted_tasks
    
    def get_summary_stats(self) -> Dict[str, Any]:
        """获取摘要统计"""
        total_hours = sum(t.get_total_estimated_hours() for t in self.tasks)
        total_subtasks = sum(len(t.subtasks) for t in self.tasks)
        
        priority_counts = {}
        verification_methods = set()
        
        for task in self.tasks:
            priority_counts[task.priority] = priority_counts.get(task.priority, 0) + 1
            
            for st in task.subtasks:
                verification_methods.add(st.verification_method.value)
        
        return {
            "total_tasks": len(self.tasks),
            "total_subtasks": total_subtasks,
            "total_estimated_hours": total_hours,
            "priority_distribution": priority_counts,
            "verification_methods": sorted(list(verification_methods)),
            "average_hours_per_task": total_hours / len(self.tasks) if self.tasks else 0,
        }
    
    def generate_markdown_report(self) -> str:
        """生成Markdown格式的任务报告"""
        lines = []
        lines.append(f"# 任务列表报告")
        lines.append(f"来源: {self.created_from}")
        lines.append(f"生成时间: {self.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")
        
        # 摘要
        stats = self.get_summary_stats()
        lines.append("## 摘要")
        lines.append(f"- **总任务数**: {stats['total_tasks']}")
        lines.append(f"- **总子任务数**: {stats['total_subtasks']}")
        lines.append(f"- **总工时**: {stats['total_estimated_hours']} 小时")
        lines.append(f"- **平均每任务工时**: {stats['average_hours_per_task']:.1f} 小时")
        lines.append("")
        
        # 优先级分布
        lines.append("### 优先级分布")
        for priority, count in sorted(stats['priority_distribution'].items()):
            lines.append(f"- {priority}: {count} 个任务")
        lines.append("")
        
        # 验证方法
        lines.append("### 验证方法")
        for method in stats['verification_methods']:
            lines.append(f"- {method}")
        lines.append("")
        
        # 任务列表
        lines.append("## 任务详情")
        lines.append("")
        
        ordered_tasks = self.get_tasks_ordered_by_dependencies()
        for i, task in enumerate(ordered_tasks, 1):
            lines.append(f"### {i}. {task.name}")
            lines.append(f"**ID**: {task.id}")
            lines.append(f"**描述**: {task.description}")
            lines.append(f"- 优先级: {task.priority}")
            lines.append(f"- 工时: {task.estimated_hours} 小时")
            lines.append(f"- 复杂度: {task.complexity}")
            lines.append("")
            
            if task.subtasks:
                lines.append("#### 子任务")
                for j, st in enumerate(task.subtasks, 1):
                    lines.append(f"{j}. **{st.name}**")
                    lines.append(f"   - 工时: {st.estimated_hours}h")
                    lines.append(f"   - 验证: {st.verification_method.value}")
                    lines.append(f"   - 验收标准:")
                    for criterion in st.acceptance_criteria:
                        lines.append(f"     * {criterion}")
                    lines.append("")
            
            if task.depends_on_tasks:
                lines.append(f"**依赖任务**: {', '.join(task.depends_on_tasks)}")
                lines.append("")
        
        return "\n".join(lines)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "product_document_id": self.product_document_id,
            "created_from": self.created_from,
            "created_at": self.created_at.isoformat(),
            "tasks": [t.to_dict() for t in self.tasks],
            "summary_stats": self.get_summary_stats(),
            "product_document": self.product_document_data,  # 保存产品文档数据
        }


# ============================================================================
# 便捷转换函数
# ============================================================================

def convert_product_document_to_task_list(
    product_doc: ProductDocument,
) -> Tuple[TaskList, List[str]]:
    """
    将产品文档转换为任务列表
    
    返回: (任务列表, 错误列表)
    """
    converter = ProductDocumentToTaskConverter()
    tasks, errors = converter.convert(product_doc)
    
    task_list = TaskList(
        product_document_id=product_doc.id,
        created_from=f"{product_doc.name} v{product_doc.version}",
        product_document_data=product_doc.to_dict(),  # 保存完整的产品文档数据
    )
    
    for task in tasks:
        task_list.add_task(task)
    
    return task_list, errors


# ============================================================================
# 任务列表持久化
# ============================================================================

import json
from pathlib import Path


def save_task_list_to_json(
    task_list: TaskList,
    file_path: str | Path,
) -> Tuple[bool, Optional[str]]:
    """
    将任务列表保存为JSON文件（包含产品文档数据）
    
    返回: (成功标志, 错误信息)
    """
    try:
        file_path = Path(file_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        data = task_list.to_dict()
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        return True, None
    except Exception as e:
        return False, str(e)


def load_task_list_from_json(
    file_path: str | Path,
) -> Tuple[Optional[TaskList], Optional[str]]:
    """
    从JSON文件加载任务列表（包含产品文档数据）
    
    返回: (任务列表, 错误信息)
    """
    try:
        file_path = Path(file_path)
        
        if not file_path.exists():
            return None, f"文件不存在: {file_path}"
        
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 重建TaskList对象
        task_list = TaskList(
            id=data.get("id"),
            product_document_id=data.get("product_document_id"),
            created_from=data.get("created_from"),
            created_at=datetime.fromisoformat(data.get("created_at", datetime.now().isoformat())),
            product_document_data=data.get("product_document"),
        )
        
        # 重建任务
        for task_data in data.get("tasks", []):
            task = GeneratedTask(
                id=task_data.get("id"),
                task_type=task_data.get("task_type"),
                name=task_data.get("name"),
                description=task_data.get("description"),
                objective_id=task_data.get("objective_id"),
                module_id=task_data.get("module_id"),
                priority=task_data.get("priority"),
                estimated_hours=task_data.get("estimated_hours", 0),
                complexity=task_data.get("complexity"),
                module_validation=task_data.get("module_validation"),
                module_validation_description=task_data.get("module_validation_description"),
                depends_on_tasks=task_data.get("depends_on_tasks", []),
                blocking_tasks=task_data.get("blocking_tasks", []),
                status=task_data.get("status"),
                created_at=datetime.fromisoformat(task_data.get("created_at", datetime.now().isoformat())),
            )
            
            # 重建子任务
            for st_data in task_data.get("subtasks", []):
                subtask = SubTask(
                    id=st_data.get("id"),
                    name=st_data.get("name"),
                    description=st_data.get("description"),
                    parent_task_id=st_data.get("parent_task_id"),
                    feature_point_id=st_data.get("feature_point_id"),
                    assigned_to=st_data.get("assigned_to"),
                    estimated_hours=st_data.get("estimated_hours", 0),
                    priority=st_data.get("priority"),
                    verification_description=st_data.get("verification", {}).get("description"),
                    verification_criteria=st_data.get("verification", {}).get("criteria", []),
                    verification_tools=st_data.get("verification", {}).get("tools", []),
                    success_metrics=st_data.get("success_metrics", {}),
                    acceptance_criteria=st_data.get("acceptance_criteria", []),
                    blocking_subtasks=st_data.get("blocking_subtasks", []),
                    blocked_by_subtasks=st_data.get("blocked_by_subtasks", []),
                    implementation_notes=st_data.get("implementation_notes"),
                    technical_requirements=st_data.get("technical_requirements", []),
                    status=st_data.get("status"),
                    created_at=datetime.fromisoformat(st_data.get("created_at", datetime.now().isoformat())),
                )
                task.add_subtask(subtask)
            
            task_list.add_task(task)
        
        return task_list, None
    except Exception as e:
        return None, str(e)


def get_product_document_from_task_list(task_list: TaskList) -> Optional[Dict[str, Any]]:
    """从任务列表中获取保存的产品文档数据"""
    return task_list.product_document_data


def get_task_list_with_product_context(task_list: TaskList) -> Dict[str, Any]:
    """
    获取包含产品文档上下文的完整任务列表
    
    便于在任务系统中查看原始产品文档信息
    """
    return {
        "task_list_id": task_list.id,
        "product_document_id": task_list.product_document_id,
        "product_document_name": task_list.created_from,
        "created_at": task_list.created_at.isoformat(),
        "product_document": task_list.product_document_data,  # 完整的产品文档
        "tasks_summary": task_list.get_summary_stats(),
        "tasks": [t.to_dict() for t in task_list.tasks],
    }
