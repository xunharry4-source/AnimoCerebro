import os
import fcntl
import time
import logging
from uuid import uuid4
from abc import ABC, abstractmethod
from typing import Optional

logger = logging.getLogger(__name__)

class AbstractDistributedLock(ABC):
    """Abstract interface for distributed locking across nodes/processes."""
    @abstractmethod
    def acquire(self, timeout: float = 10.0) -> bool:
        pass

    @abstractmethod
    def release(self) -> None:
        pass

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()

class FileDistributedLock(AbstractDistributedLock):
    """
    Standard unix file-based lock (flock).
    Safe for multi-process and multi-node (on NFS/EFS with lock support).
    """
    def __init__(self, lock_file_path: str):
        self.lock_file_path = lock_file_path
        self._lock_file = None

    def acquire(self, timeout: float = 10.0) -> bool:
        start_time = time.time()
        # Ensure directory exists
        os.makedirs(os.path.dirname(self.lock_file_path), exist_ok=True)
        
        while True:
            try:
                if self._lock_file is None:
                    self._lock_file = open(self.lock_file_path, "w")
                
                # Apply an exclusive lock (blocking/non-blocking via flag)
                # We use LOCK_EX | LOCK_NB for non-blocking attempt
                fcntl.flock(self._lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return True
            except (IOError, OSError):
                if time.time() - start_time >= timeout:
                    logger.error(f"Failed to acquire lock on {self.lock_file_path} after {timeout}s")
                    return False
                time.sleep(0.1)  # Polling interval

    def release(self) -> None:
        if self._lock_file:
            try:
                fcntl.flock(self._lock_file, fcntl.LOCK_UN)
                self._lock_file.close()
            except Exception as e:
                logger.warning(f"Error releasing lock {self.lock_file_path}: {e}")
            finally:
                self._lock_file = None

class RedisDistributedLock(AbstractDistributedLock):
    """
    Distributed lock using Redis (Redlock-like but single instance for simplicity).
    """
    def __init__(self, lock_key: str, ttl: int = 30):
        from zentex.common.redis_client import get_redis_client
        self.redis = get_redis_client()
        self.lock_key = f"zentex:lock:{lock_key}"
        self.ttl = ttl
        self.identifier = str(uuid4())

    def acquire(self, timeout: float = 10.0) -> bool:
        start_time = time.time()
        while True:
            # NX: Only set if it doesn't exist
            # EX: Expire in ttl seconds
            if self.redis.set(self.lock_key, self.identifier, ex=self.ttl, nx=True):
                return True
            
            if time.time() - start_time >= timeout:
                return False
            time.sleep(0.1)

    def release(self) -> None:
        """Release lock only if we own it (via Lua script for atomicity)."""
        script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """
        self.redis.eval(script, 1, self.lock_key, self.identifier)

class DiskCacheDistributedLock(AbstractDistributedLock):
    """
    Distributed lock using DiskCache for robust single-node multi-process safety.
    """
    def __init__(self, lock_key: str, expire: int = 30):
        from zentex.common.diskcache_client import get_disk_cache
        self.cache = get_disk_cache()
        self.lock_key = f"lock:{lock_key}"
        self.expire = expire
        self.identifier = str(uuid4())

    def acquire(self, timeout: float = 10.0) -> bool:
        start_time = time.time()
        while True:
            # cache.add returns True if key was not present and is now set
            if self.cache.add(self.lock_key, self.identifier, expire=self.expire):
                return True
            
            # Check if it's already held by us (re-entrant-ish or just safety)
            if self.cache.get(self.lock_key) == self.identifier:
                return True

            if time.time() - start_time >= timeout:
                return False
            time.sleep(0.1)

    def release(self) -> None:
        # Atomic release: only delete if it's ours
        # Since DiskCache doesn't have Lua, we use a simple check
        # This is safe enough for single-node multi-process
        if self.cache.get(self.lock_key) == self.identifier:
            self.cache.delete(self.lock_key)

def get_lock_for_resource(resource_id: str, lock_dir: str = "/tmp/zentex_locks") -> AbstractDistributedLock:
    """Factory to get the appropriate lock implementation."""
    cluster_mode = os.environ.get("ZENTEX_CLUSTER_MODE", "false").lower() == "true"
    
    if cluster_mode:
        # Redis is strictly for cluster mode
        try:
            return RedisDistributedLock(resource_id)
        except Exception as e:
            logger.warning(f"Failed to initialize Redis lock for {resource_id}, falling back to file lock: {e}")
            safe_name = resource_id.replace("/", "_").replace("\\", "_")
            lock_path = os.path.join(lock_dir, f"{safe_name}.lock")
            return FileDistributedLock(lock_path)
    else:
        # Single-node mode uses DiskCache for multi-process safety
        try:
            return DiskCacheDistributedLock(resource_id)
        except Exception as e:
            logger.warning(f"Failed to initialize DiskCache lock for {resource_id}, falling back to file lock: {e}")
            safe_name = resource_id.replace("/", "_").replace("\\", "_")
            lock_path = os.path.join(lock_dir, f"{safe_name}.lock")
            return FileDistributedLock(lock_path)
