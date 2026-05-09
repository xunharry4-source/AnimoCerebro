"""
项目计划文档转任务转换器

将项目计划文档转换为任务列表，支持从里程碑和风险项生成任务
"""

from __future__ import annotations

from typing import Tuple, List, Optional, Any, Dict
import uuid
from datetime import datetime

from zentex.tasks.task_generator import TaskList, GeneratedTask, SubTask
from .project_plan_document_plugin import ProjectPlanDocument, ValidationType


class ProjectPlanToTaskConverter:
    """项目计划文档到任务列表的转换器"""
    
    def __init__(self):
        self.generated_tasks: List[GeneratedTask] = []
        self.task_id_map: Dict[str, str] = {}
    
    def convert(self, plan_doc: ProjectPlanDocument) -> Tuple[TaskList, List[str]]:
        """
        转换项目计划文档为任务列表
        
        返回: (任务列表, 错误列表)
        """
        errors = []
        
        # 验证产品文档
        is_valid, validation_errors = plan_doc.validate_document()
        if not is_valid:
            return TaskList(), validation_errors
        
        # 从里程碑生成任务
        for milestone in plan_doc.part4_milestones:
            task = self._generate_task_from_milestone(milestone, plan_doc)
            self.generated_tasks.append(task)
            self.task_id_map[milestone.id] = task.id
        
        # 从风险项生成任务
        for risk in plan_doc.part5_risks:
            task = self._generate_task_from_risk(risk, plan_doc)
            self.generated_tasks.append(task)
        
        # 构建任务依赖关系
        self._build_task_dependencies(plan_doc.part4_milestones)
        
        # 创建任务列表
        task_list = TaskList(
            product_document_id=plan_doc.id,
            created_from=f"{plan_doc.part1_project_name} v{plan_doc.part1_version}",
            product_document_data=plan_doc.to_dict(),
        )
        
        for task in self.generated_tasks:
            task_list.add_task(task)
        
        return task_list, errors
    
    def _generate_task_from_milestone(
        self,
        milestone,
        plan_doc: ProjectPlanDocument,
    ) -> GeneratedTask:
        """从里程碑生成任务"""
        task = GeneratedTask(
            task_type="milestone",
            name=f"里程碑: {milestone.name}",
            description=milestone.description,
            priority="high",
            estimated_hours=0,  # 从子任务计算
            complexity="high",
        )
        
        # 为交付物生成子任务
        for i, deliverable in enumerate(milestone.deliverables, 1):
            subtask = SubTask(
                name=f"{milestone.name} - {deliverable}",
                description=f"完成交付物: {deliverable}",
                estimated_hours=0,
                priority="high",
                verification_method=ValidationType.INTEGRATION_TEST,
                verification_description="验证交付物完整性和质量",
                verification_criteria=milestone.success_criteria,
                acceptance_criteria=[f"✓ {deliverable} 完成", f"✓ 通过验收标准"],
                success_metrics={
                    "完成度": "100%",
                    "质量": "符合标准",
                },
            )
            task.add_subtask(subtask)
        
        return task
    
    def _generate_task_from_risk(
        self,
        risk,
        plan_doc: ProjectPlanDocument,
    ) -> GeneratedTask:
        """从风险项生成任务"""
        task = GeneratedTask(
            task_type="risk_mitigation",
            name=f"风险应对: {risk.title}",
            description=risk.description,
            priority=self._map_risk_priority(risk.priority.value),
            estimated_hours=4,  # 风险应对任务基础工时
            complexity="medium",
        )
        
        # 缓解策略子任务
        subtask1 = SubTask(
            name=f"{risk.title} - 缓解策略实施",
            description=f"实施缓解策略: {risk.mitigation_strategy}",
            estimated_hours=2,
            priority=self._map_risk_priority(risk.priority.value),
            verification_method=ValidationType.MANUAL_TEST,
            verification_description="验证缓解策略有效性",
            verification_criteria=["缓解策略已实施", "效果符合预期"],
            acceptance_criteria=[
                f"✓ {risk.mitigation_strategy}",
                "✓ 风险等级降低",
            ],
            success_metrics={
                "风险概率": "降低50%",
                "风险影响": "可控",
            },
        )
        task.add_subtask(subtask1)
        
        # 应急计划子任务
        subtask2 = SubTask(
            name=f"{risk.title} - 应急计划准备",
            description=f"准备应急计划: {risk.contingency_plan}",
            estimated_hours=2,
            priority=self._map_risk_priority(risk.priority.value),
            verification_method=ValidationType.MANUAL_TEST,
            verification_description="验证应急计划可行性",
            verification_criteria=["应急计划已制定", "团队已培训"],
            acceptance_criteria=[
                f"✓ {risk.contingency_plan}",
                "✓ 应急响应时间 < 2小时",
            ],
            success_metrics={
                "应急响应时间": "< 2小时",
                "应急方案成功率": "> 95%",
            },
        )
        task.add_subtask(subtask2)
        
        return task
    
    def _build_task_dependencies(self, milestones) -> None:
        """构建任务之间的依赖关系"""
        for i, milestone in enumerate(milestones):
            if i == 0:
                continue  # 第一个里程碑没有依赖
            
            task = self._find_task_by_name(f"里程碑: {milestone.name}")
            prev_task = self._find_task_by_name(f"里程碑: {milestones[i-1].name}")
            
            if task and prev_task:
                task.depends_on_tasks.append(prev_task.id)
    
    def _find_task_by_name(self, name: str) -> Optional[GeneratedTask]:
        """按名称查找任务"""
        for task in self.generated_tasks:
            if task.name == name:
                return task
        return None
    
    @staticmethod
    def _map_risk_priority(risk_priority: str) -> str:
        """映射风险优先级到任务优先级"""
        mapping = {
            "critical": "critical",
            "high": "high",
            "medium": "medium",
            "low": "low",
        }
        return mapping.get(risk_priority, "medium")


def convert_project_plan_to_task_list(
    plan_doc: ProjectPlanDocument,
) -> Tuple[TaskList, List[str]]:
    """
    将项目计划文档转换为任务列表
    
    返回: (任务列表, 错误列表)
    """
    converter = ProjectPlanToTaskConverter()
    return converter.convert(plan_doc)
