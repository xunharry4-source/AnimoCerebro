from __future__ import annotations
try:
    import redis
except ImportError:
    redis = None
import os
from typing import Optional, Any

_redis_client: Optional[Any] = None

def get_redis_client() -> Any:
    """
    Singleton-like access to the Redis client.
    EN: Only allowed when ZENTEX_CLUSTER_MODE is 'true'.
    ZH: 仅在集群模式下允许启动 Redis 客户端。
    """
    global _redis_client
    
    cluster_mode = os.environ.get("ZENTEX_CLUSTER_MODE", "false").lower() == "true"
    if not cluster_mode:
        raise RuntimeError(
            "Redis client requested but ZENTEX_CLUSTER_MODE is not 'true'. "
            "In single-machine mode, use DiskCache instead."
        )

    if _redis_client is None:
        if redis is None:
            raise ImportError("redis module is not installed. Please install it with: pip install redis")
            
        redis_host = os.environ.get("REDIS_HOST", "localhost")
        redis_port = int(os.environ.get("REDIS_PORT", 6379))
        redis_db = int(os.environ.get("REDIS_DB", 0))
        redis_password = os.environ.get("REDIS_PASSWORD", None)
        
        _redis_client = redis.Redis(
            host=redis_host,
            port=redis_port,
            db=redis_db,
            password=redis_password,
            decode_responses=True
        )
    return _redis_client

