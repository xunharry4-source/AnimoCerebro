"""
产品文档标准化模板和验证工具

确保所有产品文档都遵循统一的格式和结构。
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Any, Tuple
import json
from datetime import datetime


@dataclass
class DocumentTemplate:
    """产品文档标准模板"""
    
    # 所需的章节
    REQUIRED_SECTIONS = {
        "1. 系统架构描述": {
            "architecture_style": "架构类型(微服务/单体/分布式等)",
            "components": "主要组件和其职责",
            "data_flows": "数据流和交互",
            "deployment": "部署架构",
            "performance_targets": "性能目标",
        },
        "2. 项目计划": {
            "timeline": "时间计划和里程碑",
            "resources": "所需资源和人员",
            "risks": "风险识别和缓解策略",
            "dependencies": "外部依赖",
        },
        "3. 项目目标": {
            "business_goals": "业务目标",
            "technical_goals": "技术目标",
            "success_criteria": "成功标准",
            "metrics": "可测量的指标",
        },
        "4. 功能模块": {
            "module_list": "模块清单",
            "module_priority": "模块优先级",
            "module_dependencies": "模块间依赖",
        },
        "5. 详细功能点": {
            "feature_descriptions": "功能描述",
            "acceptance_criteria": "验收标准",
            "verification_methods": "验证方法",
            "estimates": "工作量估计",
        },
    }
    
    @staticmethod
    def get_template() -> Dict[str, Any]:
        """获取产品文档模板"""
        return {
            "metadata": {
                "product_name": "",
                "version": "1.0.0",
                "author": "",
                "created_date": datetime.now().isoformat(),
                "last_updated": datetime.now().isoformat(),
            },
            "executive_summary": "",
            
            "1_system_architecture": {
                "overview": "",
                "architecture_style": "",
                "components": [],
                "data_flows": [],
                "deployment": "",
                "scalability": {},
                "performance_targets": {},
                "security": [],
                "monitoring": {},
            },
            
            "2_project_plan": {
                "timeline": {},
                "milestones": [],
                "team_members": [],
                "resources": {},
                "risks": [],
                "mitigation_strategies": {},
                "external_dependencies": [],
            },
            
            "3_project_objectives": {
                "business_goals": [],
                "technical_goals": [],
                "success_criteria": {},
                "measurable_metrics": {},
                "priority_ranking": {},
            },
            
            "4_functional_modules": {
                "modules": [
                    {
                        "id": "",
                        "name": "",
                        "description": "",
                        "priority": "medium",
                        "risk_level": "low",
                        "dependencies": [],
                        "estimated_hours": 0,
                        "features": [],
                    }
                ]
            },
            
            "5_detailed_features": {
                "features": [
                    {
                        "id": "",
                        "name": "",
                        "module_id": "",
                        "description": "",
                        "requirement": "",
                        "complexity": "medium",
                        "estimated_hours": 0,
                        "verification": {
                            "method": "automated_test",
                            "criteria": [],
                            "tools": [],
                            "target": "",
                        },
                        "acceptance_criteria": [],
                        "technical_requirements": [],
                    }
                ]
            },
        }
    
    @staticmethod
    def validate_template(doc: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """验证文档是否符合模板"""
        errors = []
        
        # 检查必要的顶级章节
        required_sections = [
            "metadata",
            "executive_summary",
            "1_system_architecture",
            "2_project_plan",
            "3_project_objectives",
            "4_functional_modules",
            "5_detailed_features",
        ]
        
        for section in required_sections:
            if section not in doc:
                errors.append(f"缺少必需章节: {section}")
        
        # 检查元数据
        if "metadata" in doc:
            metadata = doc["metadata"]
            if not metadata.get("product_name"):
                errors.append("产品名称不能为空")
            if not metadata.get("author"):
                errors.append("作者不能为空")
        
        # 检查系统架构
        if "1_system_architecture" in doc:
            arch = doc["1_system_architecture"]
            if not arch.get("architecture_style"):
                errors.append("必须指定架构类型")
            if not arch.get("components"):
                errors.append("必须定义至少一个组件")
        
        # 检查项目计划
        if "2_project_plan" in doc:
            plan = doc["2_project_plan"]
            if not plan.get("milestones"):
                errors.append("必须定义至少一个里程碑")
            if not plan.get("team_members"):
                errors.append("必须指定团队成员")
        
        # 检查项目目标
        if "3_project_objectives" in doc:
            obj = doc["3_project_objectives"]
            if not obj.get("business_goals"):
                errors.append("必须定义业务目标")
        
        # 检查功能模块
        if "4_functional_modules" in doc:
            modules = doc["4_functional_modules"]
            if not modules.get("modules") or len(modules["modules"]) == 0:
                errors.append("必须定义至少一个功能模块")
            else:
                for module in modules["modules"]:
                    if not module.get("name"):
                        errors.append("模块名称不能为空")
        
        # 检查详细功能点
        if "5_detailed_features" in doc:
            features = doc["5_detailed_features"]
            if not features.get("features") or len(features["features"]) == 0:
                errors.append("必须定义至少一个功能点")
            else:
                for feature in features["features"]:
                    if not feature.get("name"):
                        errors.append("功能点名称不能为空")
                    if not feature.get("verification"):
                        errors.append(f"功能点 {feature.get('name')} 缺少验证方法")
        
        return len(errors) == 0, errors


class DocumentFormatter:
    """产品文档格式化工具"""
    
    @staticmethod
    def validate_and_normalize(doc: Dict[str, Any]) -> Tuple[bool, Dict[str, Any], List[str]]:
        """
        验证和规范化文档
        
        返回: (是否有效, 规范化后的文档, 错误和警告列表)
        """
        errors = []
        
        # 验证模板
        is_valid, template_errors = DocumentTemplate.validate_template(doc)
        errors.extend(template_errors)
        
        # 规范化
        normalized = DocumentFormatter._normalize_document(doc)
        
        return is_valid, normalized, errors
    
    @staticmethod
    def _normalize_document(doc: Dict[str, Any]) -> Dict[str, Any]:
        """规范化文档内容"""
        # 删除额外字段，只保留模板中的字段
        normalized = {}
        template = DocumentTemplate.get_template()
        
        for key in template.keys():
            if key in doc:
                normalized[key] = doc[key]
            else:
                normalized[key] = template[key]
        
        return normalized
    
    @staticmethod
    def pretty_print(doc: Dict[str, Any], indent: int = 2) -> str:
        """美化打印文档"""
        return json.dumps(doc, ensure_ascii=False, indent=indent)


class DocumentValidator:
    """产品文档验证工具"""
    
    @staticmethod
    def check_consistency(doc: Dict[str, Any]) -> List[str]:
        """检查文档的一致性"""
        warnings = []
        
        # 检查模块引用
        modules = {}
        if "4_functional_modules" in doc:
            for module in doc["4_functional_modules"].get("modules", []):
                modules[module.get("id")] = module.get("name")
        
        if "5_detailed_features" in doc:
            for feature in doc["5_detailed_features"].get("features", []):
                module_id = feature.get("module_id")
                if module_id and module_id not in modules:
                    warnings.append(
                        f"功能点 '{feature.get('name')}' 引用了不存在的模块 {module_id}"
                    )
        
        # 检查依赖关系
        all_module_ids = set(modules.keys())
        for module in doc.get("4_functional_modules", {}).get("modules", []):
            for dep_id in module.get("dependencies", []):
                if dep_id not in all_module_ids:
                    warnings.append(
                        f"模块 '{module.get('name')}' 依赖了不存在的模块 {dep_id}"
                    )
        
        # 检查工时一致性
        module_hours = {}
        for module in doc.get("4_functional_modules", {}).get("modules", []):
            module_id = module.get("id")
            declared_hours = module.get("estimated_hours", 0)
            
            # 计算功能点总工时
            feature_hours = 0
            for feature in doc.get("5_detailed_features", {}).get("features", []):
                if feature.get("module_id") == module_id:
                    feature_hours += feature.get("estimated_hours", 0)
            
            if feature_hours > 0 and abs(declared_hours - feature_hours) > 1:
                warnings.append(
                    f"模块 '{module.get('name')}' 声明工时 {declared_hours}h，"
                    f"但功能点总工时 {feature_hours}h，不一致"
                )
        
        # 检查优先级定义
        for module in doc.get("4_functional_modules", {}).get("modules", []):
            priority = module.get("priority", "").lower()
            if priority not in ["low", "medium", "high", "critical"]:
                warnings.append(
                    f"模块 '{module.get('name')}' 的优先级 '{priority}' 无效"
                )
        
        return warnings
    
    @staticmethod
    def check_completeness(doc: Dict[str, Any]) -> Dict[str, int]:
        """检查文档的完整性百分比"""
        total_fields = 0
        filled_fields = 0
        
        def count_fields(obj):
            nonlocal total_fields, filled_fields
            if isinstance(obj, dict):
                for key, value in obj.items():
                    if key.startswith("_"):
                        continue
                    total_fields += 1
                    if value and (
                        not isinstance(value, (list, dict))
                        or (isinstance(value, (list, dict)) and len(value) > 0)
                    ):
                        filled_fields += 1
                    if isinstance(value, (dict, list)):
                        count_fields(value)
            elif isinstance(obj, list):
                for item in obj:
                    if isinstance(item, (dict, list)):
                        count_fields(item)
        
        count_fields(doc)
        
        completeness = int((filled_fields / total_fields * 100)) if total_fields > 0 else 0
        
        return {
            "total_fields": total_fields,
            "filled_fields": filled_fields,
            "completeness_percentage": completeness,
        }
    
    @staticmethod
    def generate_validation_report(doc: Dict[str, Any]) -> str:
        """生成完整的验证报告"""
        lines = []
        
        # 验证模板
        is_valid, errors = DocumentTemplate.validate_template(doc)
        lines.append("=" * 70)
        lines.append("产品文档验证报告")
        lines.append("=" * 70)
        lines.append("")
        
        if is_valid:
            lines.append("✅ 模板验证: 通过")
        else:
            lines.append("❌ 模板验证: 失败")
            lines.append("")
            lines.append("错误:")
            for error in errors:
                lines.append(f"  - {error}")
        
        lines.append("")
        
        # 一致性检查
        warnings = DocumentValidator.check_consistency(doc)
        if warnings:
            lines.append("⚠️ 一致性检查: 发现问题")
            for warning in warnings:
                lines.append(f"  - {warning}")
        else:
            lines.append("✅ 一致性检查: 通过")
        
        lines.append("")
        
        # 完整性检查
        completeness = DocumentValidator.check_completeness(doc)
        lines.append("📊 完整性检查:")
        lines.append(f"  - 总字段数: {completeness['total_fields']}")
        lines.append(f"  - 已填字段: {completeness['filled_fields']}")
        lines.append(f"  - 完整度: {completeness['completeness_percentage']}%")
        
        lines.append("")
        lines.append("=" * 70)
        
        return "\n".join(lines)


# ============================================================================
# 快速创建函数
# ============================================================================

def create_blank_product_document(
    product_name: str,
    author: str,
) -> Dict[str, Any]:
    """创建一个空白的产品文档"""
    template = DocumentTemplate.get_template()
    template["metadata"]["product_name"] = product_name
    template["metadata"]["author"] = author
    return template


def load_product_document_from_json(json_str: str) -> Tuple[bool, Dict[str, Any], List[str]]:
    """从JSON字符串加载产品文档"""
    try:
        doc = json.loads(json_str)
        is_valid, normalized, errors = DocumentFormatter.validate_and_normalize(doc)
        return is_valid, normalized, errors
    except json.JSONDecodeError as e:
        return False, {}, [f"JSON解析错误: {str(e)}"]


def save_product_document_to_json(doc: Dict[str, Any]) -> str:
    """将产品文档保存为JSON"""
    return DocumentFormatter.pretty_print(doc)
