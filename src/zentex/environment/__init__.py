"""
Environment Awareness Module / 环境感知模块

This module provides comprehensive environment awareness capabilities for the Zentex brain,
enabling it to perceive and interpret physical host states, workspace changes, and external
signals. It implements the G8 (Environment Awareness & Situation Interpretation Layer) 
specification from the product documentation.

该模块为 Zentex 大脑提供全面的环境感知能力，使其能够感知和解释物理宿主状态、
工作区变化和外部信号。实现了产品文档中的 G8（环境觉知与态势解释层）规范。

Also includes Preference Alignment (User Preference Discrimination & Intent Alignment) capabilities:
- Three-step judgment process (anomaly -> preference candidate -> confirmation)
- Extreme signal interception and risk assessment
- Attack sample marking and detection
- Preference management (confirm/revoke/query)

同时包含偏好对齐（用户偏好辨析与意图对齐）能力：
- 三步判断流程（异常 -> 偏好候选 -> 确认）
- 极端信号拦截与风险评估
- 攻击样本标记与检测
- 偏好管理（确认/撤销/查询）
"""

from zentex.environment.scouter import EnvironmentScouter
from zentex.environment.interpreter import SituationInterpreter
from zentex.environment.cleaner import SensoryDataCleaner
from zentex.environment.snapshot import ContextSnapshot, ContextSnapshotStore
from zentex.environment.comparator import MultiSourceComparator
from zentex.environment.service import (
    EnvironmentAwarenessService,
    get_environment_service,
)

__all__ = [
    "EnvironmentScouter",
    "SituationInterpreter",
    "SensoryDataCleaner",
    "ContextSnapshot",
    "ContextSnapshotStore",
    "MultiSourceComparator",
    "EnvironmentAwarenessService",
    "get_environment_service",
]

__version__ = "1.0.0"
