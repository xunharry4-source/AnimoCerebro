"""
Zentex Learning Module - Learning engine and adaptive capabilities.

This module implements learning, DSPy integration, tool self-study, and sandboxed environments.

本模块实现学习、DSPy集成、工具自学和沙盒环境。
"""

from zentex.learning.engine import LearningCycleResult, run_learning_cycle, start_learning
from zentex.learning.tool_self_study_pipeline import run_dynamic_tool_self_study
from zentex.learning.models import ToolKnowledgeRecord, SandboxValidationResult
from zentex.learning.dspy_adapter import ZentexDSPyLM
from zentex.learning.sandbox import ThoughtSandbox
from zentex.learning.budget import ReasoningBudget
from zentex.learning.directions import LearningDirection
from zentex.learning.store import LEARNING_EVENT_TYPE, LearningStore

__all__ = [
    # Engine / 引擎
    "LearningCycleResult",
    "run_learning_cycle",
    "start_learning",
    
    # Tool Self-Study / 工具自学
    "run_dynamic_tool_self_study",
    "ToolKnowledgeRecord",
    "SandboxValidationResult",
    
    # DSPy Adapter / DSPy适配器
    "ZentexDSPyLM",
    
    # Sandbox / 沙盒
    "ThoughtSandbox",
    "LearningStore",
    "LEARNING_EVENT_TYPE",
    
    # Budget / 预算
    "ReasoningBudget",
    
    # Directions / 方向
    "LearningDirection",
]
