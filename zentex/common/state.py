import json
import os
from typing import Any, Dict, Optional, Type, TypeVar
from pydantic import BaseModel
from zentex.common.redis_client import get_redis_client

T = TypeVar("T", bound=BaseModel)

class SharedStateStore:
    """
    Centralized store for sharing state across cluster nodes using Redis.
    Uses DiskCache in single-node mode for robust multi-process state persistence.
    """
    def __init__(self, namespace: str):
        self.namespace = f"zentex:state:{namespace}"
        self.cluster_mode = os.environ.get("ZENTEX_CLUSTER_MODE", "false").lower() == "true"
        if not self.cluster_mode:
            from zentex.common.diskcache_client import get_disk_cache
            self.cache = get_disk_cache()
            # Use a prefix-based local isolation inside DiskCache
            self._local_prefix = f"{self.namespace}:"
        else:
            self.cache = None

    def set(self, key: str, value: Any):
        if self.cluster_mode:
            client = get_redis_client()
            if isinstance(value, BaseModel):
                data = value.model_dump_json()
            else:
                data = json.dumps(value)
            client.hset(self.namespace, key, data)
        else:
            if isinstance(value, BaseModel):
                data = value.model_dump_json()
            else:
                data = json.dumps(value)
            self.cache.set(self._local_prefix + key, data)

    def get(self, key: str, model_type: Optional[Type[T]] = None) -> Optional[Any]:
        if self.cluster_mode:
            client = get_redis_client()
            data = client.hget(self.namespace, key)
            if data is None:
                return None
            
            parsed = json.loads(data)
            if model_type:
                return model_type.model_validate(parsed)
            return parsed
        else:
            data = self.cache.get(self._local_prefix + key)
            if data is None:
                return None
            parsed = json.loads(data)
            if model_type:
                return model_type.model_validate(parsed)
            return parsed

    def delete(self, key: str):
        if self.cluster_mode:
            get_redis_client().hdel(self.namespace, key)
        else:
            self.cache.delete(self._local_prefix + key)

    def list_all(self, model_type: Optional[Type[T]] = None) -> Dict[str, Any]:
        if self.cluster_mode:
            client = get_redis_client()
            all_data = client.hgetall(self.namespace)
            result = {}
            for k, v in all_data.items():
                parsed = json.loads(v)
                if model_type:
                    result[k] = model_type.model_validate(parsed)
                else:
                    result[k] = parsed
            return result
        else:
            # DiskCache doesn't have an native hgetall, we iterate keys
            result = {}
            for k in self.cache:
                if k.startswith(self._local_prefix):
                    v = self.cache.get(k)
                    key_suffix = k[len(self._local_prefix):]
                    parsed = json.loads(v)
                    if model_type:
                        result[key_suffix] = model_type.model_validate(parsed)
                    else:
                        result[key_suffix] = parsed
            return result
