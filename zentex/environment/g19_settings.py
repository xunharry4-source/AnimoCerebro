"""
G19 - 用户偏好辨析与意图对齐 - 配置管理

使用 pydantic-settings 统一管理所有配置项。
支持从环境变量、.env 文件、配置文件加载。

配置加载优先级：
1. 环境变量 (G19_*)
2. .env 文件
3. 默认值
"""

from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseBackend(str, Enum):
    """数据库后端类型"""
    SQLITE = "sqlite"
    POSTGRESQL = "postgresql"


class LLMProvider(str, Enum):
    """LLM 提供商"""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    OLLAMA = "ollama"


class LogLevel(str, Enum):
    """日志级别"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class G19Settings(BaseSettings):
    """
    G19 模块完整配置
    
    所有配置项可通过环境变量覆盖，前缀为 G19_
    例如：G19_AUTO_CONFIRM_THRESHOLD=0.95
    """
    
    model_config = SettingsConfigDict(
        env_prefix="G19_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )
    
    # =========================================================================
    # 数据库配置
    # =========================================================================
    
    database_backend: DatabaseBackend = Field(
        default=DatabaseBackend.SQLITE,
        description="数据库后端类型 (sqlite/postgresql)"
    )
    
    sqlite_db_path: Path = Field(
        default=Path("app_data/g19_preference_store.db"),
        description="SQLite 数据库文件路径"
    )
    
    postgresql_url: Optional[str] = Field(
        default=None,
        description="PostgreSQL 连接字符串（仅当 backend=postgresql 时使用）"
    )
    
    enable_wal_mode: bool = Field(
        default=True,
        description="启用 SQLite WAL 模式以提升并发性能"
    )
    
    connection_pool_size: int = Field(
        default=5,
        ge=1,
        le=20,
        description="数据库连接池大小"
    )
    
    # =========================================================================
    # 判定引擎配置
    # =========================================================================
    
    auto_confirm_threshold: float = Field(
        default=0.9,
        ge=0.0,
        le=1.0,
        description="自动确认偏好的置信度阈值"
    )
    
    confirmation_timeout_hours: int = Field(
        default=24,
        ge=1,
        le=720,
        description="用户确认超时时间（小时）"
    )
    
    max_pending_cases_per_user: int = Field(
        default=100,
        ge=10,
        le=1000,
        description="每用户最大待确认案例数"
    )
    
    # =========================================================================
    # LLM 配置（用于智能判定）
    # =========================================================================
    
    llm_provider: LLMProvider = Field(
        default=LLMProvider.OPENAI,
        description="LLM 提供商"
    )
    
    llm_api_key: Optional[str] = Field(
        default=None,
        description="LLM API 密钥（从环境变量或 secret manager 加载）"
    )
    
    llm_model_name: str = Field(
        default="gpt-4o-mini",
        description="LLM 模型名称"
    )
    
    llm_temperature: float = Field(
        default=0.2,
        ge=0.0,
        le=1.0,
        description="LLM 温度参数（越低越确定）"
    )
    
    llm_max_retries: int = Field(
        default=3,
        ge=0,
        le=10,
        description="LLM 调用最大重试次数"
    )
    
    llm_timeout_seconds: int = Field(
        default=30,
        ge=5,
        le=120,
        description="LLM 调用超时时间（秒）"
    )
    
    # Ollama 特定配置
    ollama_base_url: str = Field(
        default="http://localhost:11434",
        description="Ollama 服务地址"
    )
    
    # =========================================================================
    # 极端信号拦截配置
    # =========================================================================
    
    risk_confirmation_threshold: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="需要二次确认的风险阈值"
    )
    
    risk_malicious_threshold: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="标记为潜在恶意的风险阈值"
    )
    
    risk_block_threshold: float = Field(
        default=0.9,
        ge=0.0,
        le=1.0,
        description="立即阻断的风险阈值"
    )
    
    # =========================================================================
    # 攻击检测配置
    # =========================================================================
    
    attack_similarity_threshold: float = Field(
        default=0.85,
        ge=0.0,
        le=1.0,
        description="攻击模式相似度阈值"
    )
    
    attack_pattern_cache_size: int = Field(
        default=1000,
        ge=100,
        le=10000,
        description="攻击模式缓存大小"
    )
    
    attack_sample_retention_days: int = Field(
        default=365,
        ge=30,
        le=3650,
        description="攻击样本保留天数"
    )
    
    # =========================================================================
    # 日志与监控配置
    # =========================================================================
    
    log_level: LogLevel = Field(
        default=LogLevel.INFO,
        description="日志级别"
    )
    
    enable_audit_logging: bool = Field(
        default=True,
        description="启用审计日志"
    )
    
    audit_log_path: Optional[Path] = Field(
        default=None,
        description="审计日志文件路径（None=写入 BrainTranscriptStore）"
    )
    
    # =========================================================================
    # 性能优化配置
    # =========================================================================
    
    enable_cache: bool = Field(
        default=True,
        description="启用缓存层"
    )
    
    cache_ttl_seconds: int = Field(
        default=300,
        ge=60,
        le=3600,
        description="缓存 TTL（秒）"
    )
    
    enable_async_processing: bool = Field(
        default=True,
        description="启用异步任务处理"
    )
    
    # =========================================================================
    # 安全配置
    # =========================================================================
    
    encrypt_sensitive_data: bool = Field(
        default=True,
        description="加密敏感数据（如信号内容哈希）"
    )
    
    encryption_key: Optional[str] = Field(
        default=None,
        description="加密密钥（生产环境应从 secret manager 加载）"
    )
    
    max_signal_length: int = Field(
        default=10000,
        ge=1000,
        le=100000,
        description="最大信号长度限制"
    )
    
    @field_validator('sqlite_db_path')
    @classmethod
    def validate_db_path(cls, v: Path) -> Path:
        """确保数据库目录存在"""
        v.parent.mkdir(parents=True, exist_ok=True)
        return v
    
    @field_validator('llm_api_key')
    @classmethod
    def validate_llm_key(cls, v: Optional[str], info) -> Optional[str]:
        """
        验证 LLM API 密钥
        
        - Ollama 不需要 API key
        - 其他提供商如果没有 API key，自动降级到 Ollama
        """
        provider = info.data.get('llm_provider')
        
        # 如果没有提供 API key 且不是 Ollama，自动切换到 Ollama
        if not v and provider and provider != LLMProvider.OLLAMA:
            # 返回 None，但会在 model_post_init 中处理
            return None
        
        return v
    
    def model_post_init(self, __context):
        """
        模型初始化后处理
        
        如果 LLM provider 需要 API key 但没有提供，自动切换到 Ollama
        """
        if (self.llm_provider != LLMProvider.OLLAMA and 
            not self.llm_api_key):
            # 自动降级到 Ollama（不需要 API key）
            object.__setattr__(self, 'llm_provider', LLMProvider.OLLAMA)


# 全局单例
_settings: Optional[G19Settings] = None


def get_g19_settings() -> G19Settings:
    """
    获取 G19 配置单例
    
    Returns:
        G19Settings: 配置对象
        
    Example:
        >>> settings = get_g19_settings()
        >>> print(settings.auto_confirm_threshold)
        0.9
    """
    global _settings
    if _settings is None:
        _settings = G19Settings()
    return _settings


def reload_g19_settings() -> G19Settings:
    """
    重新加载配置（用于热重载）
    
    Returns:
        G19Settings: 新的配置对象
        
    Example:
        >>> # 修改环境变量后重新加载
        >>> import os
        >>> os.environ['G19_AUTO_CONFIRM_THRESHOLD'] = '0.95'
        >>> settings = reload_g19_settings()
        >>> print(settings.auto_confirm_threshold)
        0.95
    """
    global _settings
    _settings = G19Settings()
    return _settings
