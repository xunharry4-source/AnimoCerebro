"""
Zentex Learning Module - Learning engine and adaptive capabilities.

This module implements learning, DSPy integration, G16 pipeline, and sandboxed environments.

本模块实现学习、DSPy集成、G16管道和沙盒环境。
"""

from zentex.learning.engine import LearningCycleResult, run_learning_cycle, start_learning
from zentex.learning.g16_pipeline import run_g16_dynamic_tool_self_study
from zentex.learning.g16_models import ToolKnowledgeRecord, SandboxValidationResult
from zentex.learning.dspy_adapter import ZentexDSPyLM
from zentex.learning.sandbox import ThoughtSandbox
from zentex.learning.budget import ReasoningBudget
from zentex.learning.directions import LearningDirection

__all__ = [
    # Engine / 引擎
    "LearningCycleResult",
    "run_learning_cycle",
    "start_learning",
    
    # G16 Pipeline / G16管道
    "run_g16_dynamic_tool_self_study",
    "ToolKnowledgeRecord",
    "SandboxValidationResult",
    
    # DSPy Adapter / DSPy适配器
    "ZentexDSPyLM",
    
    # Sandbox / 沙盒
    "ThoughtSandbox",
    
    # Budget / 预算
    "ReasoningBudget",
    
    # Directions / 方向
    "LearningDirection",
]
