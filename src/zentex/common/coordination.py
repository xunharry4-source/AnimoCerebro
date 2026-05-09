import os
import time
import logging
import uuid
from typing import Optional
from zentex.common.redis_client import get_redis_client

logger = logging.getLogger(__name__)

class LeaderElection:
    """
    Distributed leader election.
    Uses Redis in cluster mode, DiskCache in single-node mode.
    Ensures background tasks (consolidation, auto-resume) run on only one node/process.
    """
    def __init__(self, resource_name: str, ttl_ms: int = 30000):
        self.key = f"leader:{resource_name}"
        self.node_id = f"{os.uname().nodename}-{uuid.uuid4().hex[:8]}"
        self.ttl_ms = ttl_ms
        self.is_leader = False
        self.cluster_mode = os.environ.get("ZENTEX_CLUSTER_MODE", "false").lower() == "true"
        
        if not self.cluster_mode:
            from zentex.common.diskcache_client import get_disk_cache
            self.cache = get_disk_cache()
            self._local_key = f"zentex:leader:{resource_name}"
        else:
            self.cache = None

    def try_acquire(self) -> bool:
        """Atomic leader acquisition."""
        if self.cluster_mode:
            client = get_redis_client()
            # NX: Set if not exists, PX: expiry in milliseconds
            success = client.set(self._full_redis_key(), self.node_id, nx=True, px=self.ttl_ms)
            
            if success:
                if not self.is_leader:
                    logger.info(f"Node {self.node_id} acquired Redis leadership for {self.key}")
                self.is_leader = True
                return True
            
            # Check if we are already the leader (extend lease)
            current_leader = client.get(self._full_redis_key())
            if current_leader == self.node_id:
                client.psetex(self._full_redis_key(), self.ttl_ms, self.node_id)
                self.is_leader = True
                return True
        else:
            # Single-node mode: Use DiskCache set with expire
            # Note: DiskCache set(nx=True) is not atomic for lead election without a lock,
            # but DiskCache itself handles multi-process concurrency on the sqlite DB.
            # For strictness, we can use a lock inside or the set(nx=True) if available via 'add'
            success = self.cache.add(self._local_key, self.node_id, expire=self.ttl_ms / 1000.0)
            if success:
                if not self.is_leader:
                    logger.info(f"Process {self.node_id} acquired DiskCache leadership for {self.key}")
                self.is_leader = True
                return True
            
            # Check for lease extension
            current_leader = self.cache.get(self._local_key)
            if current_leader == self.node_id:
                self.cache.set(self._local_key, self.node_id, expire=self.ttl_ms / 1000.0)
                self.is_leader = True
                return True

        if self.is_leader:
            logger.info(f"Node/Process {self.node_id} lost leadership for {self.key}")
        self.is_leader = False
        return False

    def _full_redis_key(self) -> str:
        return f"zentex:{self.key}"

    def release(self):
        """Release leadership if held"""
        if not self.is_leader:
            return

        if self.cluster_mode:
            client = get_redis_client()
            script = """
            if redis.call("get", KEYS[1]) == ARGV[1] then
                return redis.call("del", KEYS[1])
            else
                return 0
            end
            """
            client.eval(script, 1, self._full_redis_key(), self.node_id)
        else:
            # DiskCache release: only if we match
            if self.cache.get(self._local_key) == self.node_id:
                self.cache.delete(self._local_key)
        
        self.is_leader = False
        logger.info(f"Node/Process {self.node_id} released leadership for {self.key}")
