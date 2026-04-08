"""
Environment Awareness Module / 环境感知模块

This module provides comprehensive environment awareness capabilities for the Zentex brain,
enabling it to perceive and interpret physical host states, workspace changes, and external
signals. It implements the G8 (Environment Awareness & Situation Interpretation Layer) 
specification from the product documentation.

该模块为 Zentex 大脑提供全面的环境感知能力，使其能够感知和解释物理宿主状态、
工作区变化和外部信号。实现了产品文档中的 G8（环境觉知与态势解释层）规范。

Core Components:
- EnvironmentScouter: Physical host state sampling (CPU/memory/disk/network)
- SituationInterpreter: Translates environmental changes into role/goal impacts
- SensoryDataCleaner: Injection filtering and signal sanitization
- ContextSnapshot: Time-series context recording
- MultiSourceComparator: Cross-source conflict detection and scoring

主要组件：
- EnvironmentScouter: 物理宿主状态采样（CPU/内存/磁盘/网络）
- SituationInterpreter: 将环境变化翻译为角色/目标影响
- SensoryDataCleaner: 注入过滤和信号清洗
- ContextSnapshot: 时间序列上下文记录
- MultiSourceComparator: 跨源冲突检测与打分
"""

from zentex.environment.scouter import EnvironmentScouter
from zentex.environment.interpreter import SituationInterpreter
from zentex.environment.cleaner import SensoryDataCleaner
from zentex.environment.snapshot import ContextSnapshot, ContextSnapshotStore
from zentex.environment.comparator import MultiSourceComparator
from zentex.environment.service import EnvironmentAwarenessService

__all__ = [
    "EnvironmentScouter",
    "SituationInterpreter",
    "SensoryDataCleaner",
    "ContextSnapshot",
    "ContextSnapshotStore",
    "MultiSourceComparator",
    "EnvironmentAwarenessService",
]

__version__ = "1.0.0"
