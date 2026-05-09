"""
Alignment - 数据库会话管理

使用 SQLAlchemy 管理数据库连接和会话。
支持 SQLite（带 WAL 模式）和 PostgreSQL。
"""

import logging
from contextlib import contextmanager
from typing import Generator, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from .preference_orm import Base
from .preference_settings import AlignmentSettings, get_alignment_settings

logger = logging.getLogger(__name__)


class AlignmentDatabase:
    """
    Alignment 数据库管理器
    
    负责：
    - 数据库引擎初始化
    - 会话管理
    - 表创建和迁移
    - WAL 模式启用（SQLite）
    """
    
    def __init__(self, settings: Optional[AlignmentSettings] = None):
        """
        初始化数据库管理器
        
        Args:
            settings: Alignment 配置对象，如果为 None 则使用全局配置
        """
        self.settings = settings or get_alignment_settings()
        self.engine = self._create_engine()
        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine,
        )
        
        # 创建所有表
        self._create_tables()
        
        logger.info(f"Alignment database initialized: {self.settings.database_backend.value}")
    
    def _create_engine(self):
        """
        创建数据库引擎
        
        Returns:
            SQLAlchemy Engine 实例
        """
        if self.settings.database_backend.value == "sqlite":
            # SQLite 配置
            db_url = f"sqlite:///{self.settings.sqlite_db_path}"
            
            engine = create_engine(
                db_url,
                connect_args={"check_same_thread": False},  # 允许多线程访问
                pool_pre_ping=True,  # 连接前检查有效性
                echo=False,  # 生产环境关闭 SQL 日志
            )
            
            # 启用 WAL 模式以提升并发性能
            if self.settings.enable_wal_mode:
                with engine.connect() as conn:
                    conn.execute(text("PRAGMA journal_mode=WAL"))
                    conn.execute(text("PRAGMA synchronous=NORMAL"))
                    conn.execute(text("PRAGMA cache_size=-64000"))  # 64MB cache
                    logger.info("SQLite WAL mode enabled")
            
            logger.info(f"SQLite database path: {self.settings.sqlite_db_path}")
            
        elif self.settings.database_backend.value == "postgresql":
            # PostgreSQL 配置
            if not self.settings.postgresql_url:
                raise ValueError(
                    "postgresql_url is required when using PostgreSQL backend"
                )
            
            engine = create_engine(
                self.settings.postgresql_url,
                pool_size=self.settings.connection_pool_size,
                max_overflow=10,
                pool_pre_ping=True,
                echo=False,
            )
            
            logger.info("PostgreSQL database connected")
        
        else:
            raise ValueError(
                f"Unsupported database backend: {self.settings.database_backend.value}"
            )
        
        return engine
    
    def _create_tables(self):
        """创建所有 ORM 模型对应的表"""
        Base.metadata.create_all(bind=self.engine)
        logger.info("Database tables created")
    
    def get_session(self) -> Session:
        """
        获取数据库会话
        
        Returns:
            SQLAlchemy Session 实例
            
        Note:
            调用者负责关闭会话
        """
        return self.SessionLocal()
    
    @contextmanager
    def session_scope(self) -> Generator[Session, None, None]:
        """
        会话上下文管理器
        
        自动处理提交、回滚和关闭。
        
        Yields:
            SQLAlchemy Session 实例
            
        Example:
            >>> db = AlignmentDatabase()
            >>> with db.session_scope() as session:
            ...     session.add(some_object)
            ...     # 自动提交或回滚
        """
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    
    def close(self):
        """关闭数据库引擎"""
        self.engine.dispose()
        logger.info("Database engine closed")
    
    def health_check(self) -> bool:
        """
        数据库健康检查
        
        Returns:
            True 如果数据库连接正常
        """
        try:
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False


# 全局单例
_db_instance: Optional[AlignmentDatabase] = None


def get_preference_database(settings: Optional[AlignmentSettings] = None) -> AlignmentDatabase:
    """
    获取 Alignment 数据库单例
    
    Args:
        settings: Alignment 配置对象，如果为 None 则使用全局配置
        
    Returns:
        AlignmentDatabase 实例
    """
    global _db_instance
    if _db_instance is None:
        _db_instance = AlignmentDatabase(settings)
    return _db_instance


def get_alignment_database(settings: Optional[AlignmentSettings] = None) -> AlignmentDatabase:
    """Backward-compatible alias for legacy imports."""
    return get_preference_database(settings)


def reset_preference_database():
    """重置数据库单例（用于测试）"""
    global _db_instance
    if _db_instance:
        _db_instance.close()
    _db_instance = None
