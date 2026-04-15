"""
系统架构定义模块

用于详细描述系统的整体架构、组件、数据流等信息。
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum
import uuid


class ComponentType(str, Enum):
    """组件类型"""
    SERVICE = "service"
    LIBRARY = "library"
    DATABASE = "database"
    EXTERNAL_API = "external_api"
    MESSAGE_QUEUE = "message_queue"
    CACHE = "cache"
    FRONTEND = "frontend"
    BACKEND = "backend"
    INFRASTRUCTURE = "infrastructure"


class DataFlowType(str, Enum):
    """数据流类型"""
    SYNC = "sync"
    ASYNC = "async"
    BATCH = "batch"
    STREAM = "stream"
    RPC = "rpc"


@dataclass
class ArchitectureComponent:
    """系统架构组件"""
    id: str = field(default_factory=lambda: f"COMP-{uuid.uuid4().hex[:8]}")
    name: str = ""
    component_type: ComponentType = ComponentType.SERVICE
    description: str = ""
    
    # 技术栈
    technology_stack: List[str] = field(default_factory=list)
    
    # 职责
    responsibilities: List[str] = field(default_factory=list)
    
    # 接口
    interfaces: Dict[str, str] = field(default_factory=dict)  # 接口名 -> 描述
    
    # 依赖
    depends_on: List[str] = field(default_factory=list)  # 依赖的组件ID
    provides_to: List[str] = field(default_factory=list)  # 为哪些组件提供服务
    
    # 性能指标
    performance_requirements: Dict[str, Any] = field(default_factory=dict)
    
    # 可靠性
    reliability: Dict[str, Any] = field(default_factory=dict)  # 可用性、容错等
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "name": self.name,
            "component_type": self.component_type.value,
            "description": self.description,
            "technology_stack": self.technology_stack,
            "responsibilities": self.responsibilities,
            "interfaces": self.interfaces,
            "depends_on": self.depends_on,
            "provides_to": self.provides_to,
            "performance_requirements": self.performance_requirements,
            "reliability": self.reliability,
        }


@dataclass
class DataFlow:
    """数据流定义"""
    id: str = field(default_factory=lambda: f"DF-{uuid.uuid4().hex[:8]}")
    name: str = ""
    source_component_id: str = ""
    target_component_id: str = ""
    flow_type: DataFlowType = DataFlowType.SYNC
    
    # 数据格式
    data_format: str = ""  # JSON, Protocol Buffer, etc.
    data_schema: Optional[Dict[str, Any]] = None
    
    # 流量特性
    frequency: str = ""  # 频率：实时、每分钟、每小时等
    volume: Optional[int] = None  # 数据量：条数/字节
    
    # 特殊需求
    requirements: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "name": self.name,
            "source_component_id": self.source_component_id,
            "target_component_id": self.target_component_id,
            "flow_type": self.flow_type.value,
            "data_format": self.data_format,
            "data_schema": self.data_schema,
            "frequency": self.frequency,
            "volume": self.volume,
            "requirements": self.requirements,
        }


@dataclass
class SystemArchitecture:
    """完整的系统架构定义"""
    id: str = field(default_factory=lambda: f"ARCH-{uuid.uuid4().hex[:8]}")
    name: str = ""
    description: str = ""
    version: str = "1.0"
    
    # 架构类型
    architecture_style: str = ""  # 微服务、单体、分布式等
    
    # 组件
    components: List[ArchitectureComponent] = field(default_factory=list)
    
    # 数据流
    data_flows: List[DataFlow] = field(default_factory=list)
    
    # 部署
    deployment_strategy: str = ""
    deployment_environments: List[str] = field(default_factory=list)  # dev, staging, prod
    
    # 扩展性和性能
    scalability: Dict[str, Any] = field(default_factory=dict)
    performance_targets: Dict[str, Any] = field(default_factory=dict)
    
    # 安全性
    security_considerations: List[str] = field(default_factory=list)
    
    # 监控和日志
    monitoring: Dict[str, Any] = field(default_factory=dict)
    logging_strategy: str = ""
    
    def add_component(self, component: ArchitectureComponent) -> None:
        """添加组件"""
        self.components.append(component)
    
    def add_data_flow(self, flow: DataFlow) -> None:
        """添加数据流"""
        self.data_flows.append(flow)
    
    def get_component_by_id(self, component_id: str) -> Optional[ArchitectureComponent]:
        """按ID获取组件"""
        for comp in self.components:
            if comp.id == component_id:
                return comp
        return None
    
    def get_component_by_name(self, name: str) -> Optional[ArchitectureComponent]:
        """按名称获取组件"""
        for comp in self.components:
            if comp.name == name:
                return comp
        return None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "architecture_style": self.architecture_style,
            "components": [c.to_dict() for c in self.components],
            "data_flows": [f.to_dict() for f in self.data_flows],
            "deployment_strategy": self.deployment_strategy,
            "deployment_environments": self.deployment_environments,
            "scalability": self.scalability,
            "performance_targets": self.performance_targets,
            "security_considerations": self.security_considerations,
            "monitoring": self.monitoring,
            "logging_strategy": self.logging_strategy,
        }
    
    def generate_markdown_diagram(self) -> str:
        """生成Markdown格式的架构图"""
        lines = []
        lines.append(f"## 系统架构: {self.name}")
        lines.append("")
        lines.append(f"**架构类型**: {self.architecture_style}")
        lines.append(f"**部署策略**: {self.deployment_strategy}")
        lines.append("")
        
        # 组件列表
        lines.append("### 组件")
        for i, comp in enumerate(self.components, 1):
            lines.append(f"{i}. **{comp.name}** ({comp.component_type.value})")
            lines.append(f"   {comp.description}")
            if comp.technology_stack:
                lines.append(f"   技术栈: {', '.join(comp.technology_stack)}")
            if comp.responsibilities:
                lines.append(f"   职责:")
                for resp in comp.responsibilities:
                    lines.append(f"   - {resp}")
            lines.append("")
        
        # 数据流
        if self.data_flows:
            lines.append("### 数据流")
            for flow in self.data_flows:
                source = self.get_component_by_id(flow.source_component_id)
                target = self.get_component_by_id(flow.target_component_id)
                source_name = source.name if source else "Unknown"
                target_name = target.name if target else "Unknown"
                
                lines.append(f"- {source_name} → {target_name}")
                lines.append(f"  类型: {flow.flow_type.value}")
                lines.append(f"  格式: {flow.data_format}")
                if flow.frequency:
                    lines.append(f"  频率: {flow.frequency}")
                lines.append("")
        
        # 部署环境
        if self.deployment_environments:
            lines.append("### 部署环境")
            for env in self.deployment_environments:
                lines.append(f"- {env}")
            lines.append("")
        
        # 性能目标
        if self.performance_targets:
            lines.append("### 性能目标")
            for key, value in self.performance_targets.items():
                lines.append(f"- {key}: {value}")
            lines.append("")
        
        # 安全考虑
        if self.security_considerations:
            lines.append("### 安全考虑")
            for sec in self.security_considerations:
                lines.append(f"- {sec}")
            lines.append("")
        
        return "\n".join(lines)
