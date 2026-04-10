"""
系统健康监控数据模型

本模块定义系统健康监控功能的API契约，包括：
- Token使用统计
- LLM Provider健康状态
- 功能模块健康状态
- 整体系统健康评估

所有模型用于 /api/web/health/system 端点的响应结构。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ModuleHealthStatus(BaseModel):
    """单个功能模块的健康状态"""
    model_config = ConfigDict(extra="forbid", frozen=True)

    module_id: str = Field(min_length=1, description="模块ID")
    module_name: str = Field(min_length=1, description="模块名称")
    health_status: str = Field(description="健康状态: healthy/degraded/unhealthy/unknown")
    status_message: Optional[str] = Field(default=None, description="状态说明")
    last_check_at: Optional[str] = Field(default=None, description="最后检查时间")
    metrics: Dict[str, Any] = Field(default_factory=dict, description="模块指标")


class LLMProviderStats(BaseModel):
    """LLM Provider统计信息"""
    model_config = ConfigDict(extra="forbid", frozen=True)

    provider_name: str = Field(min_length=1, description="Provider名称")
    api_base: Optional[str] = Field(default=None, description="API地址")
    health_status: str = Field(description="健康状态")
    request_count: int = Field(ge=0, description="请求次数")
    input_tokens: int = Field(ge=0, description="输入token数")
    output_tokens: int = Field(ge=0, description="输出token数")
    total_tokens: int = Field(ge=0, description="总token数")
    error_count: int = Field(ge=0, default=0, description="错误次数")


class TokenUsageStats(BaseModel):
    """Token使用统计"""
    model_config = ConfigDict(extra="forbid", frozen=True)

    total_request_count: int = Field(ge=0, description="总请求次数")
    total_input_tokens: int = Field(ge=0, description="总输入token")
    total_output_tokens: int = Field(ge=0, description="总输出token")
    total_tokens: int = Field(ge=0, description="总token数")
    providers: List[LLMProviderStats] = Field(default_factory=list, description="各Provider统计")


class SystemHealthPayload(BaseModel):
    """系统健康状态响应"""
    model_config = ConfigDict(extra="forbid", frozen=True)

    overall_health: str = Field(description="整体健康状态: healthy/degraded/unhealthy")
    token_usage: TokenUsageStats = Field(description="Token使用统计")
    modules: List[ModuleHealthStatus] = Field(default_factory=list, description="功能模块健康状态")
    timestamp: str = Field(description="统计时间戳")
