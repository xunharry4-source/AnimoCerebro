"""Task Core subpackage - Core task decomposition and analysis components."""

from zentex.tasks.core.decomposer import TaskDecomposerPlugin
from zentex.tasks.decomposition.pydantic_ai_decomposer import PydanticAITaskDecomposerPlugin

__all__ = ["TaskDecomposerPlugin", "PydanticAITaskDecomposerPlugin"]
