from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

class ReflectionError(Exception):
    """反思模块基础异常"""
    pass

class ReflectionNotFoundError(ReflectionError):
    """反思记录未找到异常"""
    pass

class InvalidReflectionError(ReflectionError):
    """无效反思异常"""
    pass

class ReflectionGenerationError(ReflectionError):
    """反思生成异常"""
    pass

class ReflectionValidationError(ReflectionError):
    """反思验证异常"""
    pass

class ReflectionGovernanceError(ReflectionError):
    """反思治理异常"""
    pass

class ReflectionPatternError(ReflectionError):
    """反思模式异常"""
    pass
