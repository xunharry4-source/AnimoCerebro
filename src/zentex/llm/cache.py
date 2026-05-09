"""
LLM Response Cache Module

Purpose:
    Provides intelligent caching for LLM responses to reduce latency and cost.
    
Responsibilities:
    - Generate unique cache keys based on prompt + context + model
    - Manage cache lifecycle (TTL, LRU eviction)
    - Persist cache to disk for warm starts
    - Track cache statistics for monitoring
    
Not Responsible For:
    - LLM model invocation (delegated to providers)
    - Cache invalidation across distributed nodes (single-instance only)
    - Semantic similarity matching (exact match only)
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """Cache entry with metadata for lifecycle management."""
    key: str
    value: Any
    created_at: float
    ttl: int
    access_count: int = 0
    last_accessed: float = field(default_factory=time.time)
    size_bytes: int = 0
    
    def is_expired(self) -> bool:
        """Check if entry has exceeded TTL."""
        return (time.time() - self.created_at) > self.ttl
    
    def touch(self):
        """Update access metadata."""
        self.access_count += 1
        self.last_accessed = time.time()
    
    def estimate_size(self) -> int:
        """Estimate memory footprint in bytes."""
        if self.size_bytes == 0:
            self.size_bytes = len(json.dumps(self.value).encode())
        return self.size_bytes


class LLMResponseCache:
    """
    Intelligent LLM response cache with TTL and LRU eviction.
    
    Features:
        - Content-based hash key generation
        - Dual eviction strategy (LRU + TTL)
        - Memory usage monitoring
        - Disk persistence support
        - Detailed statistics tracking
    """
    
    def __init__(
        self,
        max_size: int = 1000,
        max_memory_mb: int = 100,
        default_ttl: int = 300,
        persist_path: Optional[Path] = None,
        enable_stats: bool = True,
    ):
        self.max_size = max_size
        self.max_memory_bytes = max_memory_mb * 1024 * 1024
        self.default_ttl = default_ttl
        self.persist_path = persist_path
        self.enable_stats = enable_stats
        
        # Core data structures
        self._cache: dict[str, CacheEntry] = {}
        self._access_order: list[str] = []  # LRU tracking
        self._current_memory = 0
        
        # Statistics
        self._stats = {
            'hits': 0,
            'misses': 0,
            'evictions_lru': 0,
            'evictions_memory': 0,
            'expirations': 0,
            'total_requests': 0,
        }
        
        # Load persistent cache if available
        if persist_path and persist_path.exists():
            self._load_from_disk()
        
        logger.info(
            f"LLMResponseCache initialized: "
            f"max_size={max_size}, max_memory={max_memory_mb}MB, ttl={default_ttl}s"
        )
    
    def get(self, prompt: str, context: dict, model: str, **kwargs) -> Optional[Any]:
        """
        Retrieve cached LLM response.
        
        Args:
            prompt: The prompt text
            context: Context dictionary
            model: Model identifier
            **kwargs: Additional parameters (temperature, top_p, etc.)
        
        Returns:
            Cached response or None if cache miss
        """
        key = self._generate_key(prompt, context, model, **kwargs)
        
        if self.enable_stats:
            self._stats['total_requests'] += 1
        
        # Check existence
        if key not in self._cache:
            if self.enable_stats:
                self._stats['misses'] += 1
            logger.debug(f"Cache MISS: key={key[:12]}...")
            return None
        
        entry = self._cache[key]
        
        # Check expiration
        if entry.is_expired():
            self._remove_entry(key)
            if self.enable_stats:
                self._stats['expirations'] += 1
            logger.debug(f"Cache EXPIRED: key={key[:12]}...")
            return None
        
        # Update access metadata
        entry.touch()
        self._update_access_order(key)
        
        if self.enable_stats:
            self._stats['hits'] += 1
        
        hit_rate = self._calculate_hit_rate()
        logger.debug(
            f"Cache HIT: key={key[:12]}..., "
            f"access_count={entry.access_count}, "
            f"hit_rate={hit_rate:.1%}"
        )
        
        return entry.value
    
    def set(
        self,
        prompt: str,
        context: dict,
        model: str,
        value: Any,
        ttl: Optional[int] = None,
        **kwargs
    ):
        """
        Store LLM response in cache.
        
        Args:
            prompt: The prompt text
            context: Context dictionary
            model: Model identifier
            value: Response value to cache
            ttl: Time-to-live in seconds (uses default_ttl if None)
            **kwargs: Additional parameters
        """
        key = self._generate_key(prompt, context, model, **kwargs)
        
        # Create cache entry
        entry = CacheEntry(
            key=key,
            value=value,
            created_at=time.time(),
            ttl=ttl or self.default_ttl,
        )
        entry_size = entry.estimate_size()
        
        # Ensure capacity
        self._ensure_capacity(entry_size)
        
        # Store entry
        self._cache[key] = entry
        self._access_order.append(key)
        self._current_memory += entry_size
        
        logger.debug(
            f"Cache SET: key={key[:12]}..., "
            f"size={entry_size}B, ttl={entry.ttl}s"
        )
        
        # Async persistence
        if self.persist_path:
            self._schedule_persist()
    
    def clear(self):
        """Clear all cache entries."""
        self._cache.clear()
        self._access_order.clear()
        self._current_memory = 0
        logger.info("Cache cleared")
    
    def get_stats(self) -> dict:
        """Get cache statistics."""
        total = self._stats['hits'] + self._stats['misses']
        hit_rate = self._stats['hits'] / total if total > 0 else 0.0
        
        return {
            **self._stats,
            'hit_rate': hit_rate,
            'current_size': len(self._cache),
            'max_size': self.max_size,
            'current_memory_mb': self._current_memory / (1024 * 1024),
            'max_memory_mb': self.max_memory_bytes / (1024 * 1024),
            'memory_usage_percent': (
                self._current_memory / self.max_memory_bytes * 100
                if self.max_memory_bytes > 0 else 0
            ),
        }
    
    # ==================== Private Methods ====================
    
    def _generate_key(self, prompt: str, context: dict, model: str, **kwargs) -> str:
        """Generate unique cache key based on content hash."""
        content = json.dumps({
            'prompt': prompt,
            'context': context,
            'model': model,
            'kwargs': kwargs,
        }, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()
    
    def _ensure_capacity(self, new_entry_size: int):
        """Ensure sufficient capacity for new entry."""
        # Check count limit
        while len(self._cache) >= self.max_size:
            self._evict_lru()
        
        # Check memory limit
        while (self._current_memory + new_entry_size) > self.max_memory_bytes:
            if not self._evict_lru():
                # Cannot evict more, clear entire cache
                logger.warning("Cache memory limit reached, clearing all entries")
                self.clear()
                break
    
    def _evict_lru(self) -> bool:
        """Evict least recently used entry."""
        if not self._access_order:
            return False
        
        oldest_key = self._access_order.pop(0)
        
        if oldest_key in self._cache:
            entry = self._cache[oldest_key]
            self._current_memory -= entry.estimate_size()
            del self._cache[oldest_key]
            
            if self.enable_stats:
                self._stats['evictions_lru'] += 1
            
            logger.debug(f"Cache EVICT (LRU): key={oldest_key[:12]}...")
            return True
        
        return False
    
    def _remove_entry(self, key: str):
        """Remove cache entry."""
        if key in self._cache:
            entry = self._cache[key]
            self._current_memory -= entry.estimate_size()
            del self._cache[key]
        
        if key in self._access_order:
            self._access_order.remove(key)
    
    def _update_access_order(self, key: str):
        """Update access order (move to end for most recent)."""
        if key in self._access_order:
            self._access_order.remove(key)
        self._access_order.append(key)
    
    def _calculate_hit_rate(self) -> float:
        """Calculate cache hit rate."""
        total = self._stats['hits'] + self._stats['misses']
        return self._stats['hits'] / total if total > 0 else 0.0
    
    def _schedule_persist(self):
        """Schedule persistence (simplified: direct write)."""
        try:
            self._persist_to_disk()
        except Exception as e:
            logger.warning(f"Failed to persist cache: {e}")
    
    def _persist_to_disk(self):
        """Persist cache to disk."""
        if not self.persist_path:
            return
        
        data = {
            'entries': {
                key: {
                    'value': entry.value,
                    'created_at': entry.created_at,
                    'ttl': entry.ttl,
                    'access_count': entry.access_count,
                }
                for key, entry in self._cache.items()
                if not entry.is_expired()
            },
            'stats': self._stats,
            'metadata': {
                'persisted_at': time.time(),
                'entry_count': len(self._cache),
            }
        }
        
        self.persist_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.persist_path, 'w') as f:
            json.dump(data, f, indent=2)
        
        logger.debug(f"Cache persisted: {len(self._cache)} entries")
    
    def _load_from_disk(self):
        """Load cache from disk."""
        try:
            with open(self.persist_path, 'r') as f:
                data = json.load(f)
            
            loaded_count = 0
            for key, entry_data in data.get('entries', {}).items():
                entry = CacheEntry(
                    key=key,
                    value=entry_data['value'],
                    created_at=entry_data['created_at'],
                    ttl=entry_data['ttl'],
                    access_count=entry_data.get('access_count', 0),
                )
                
                # Only load non-expired entries
                if not entry.is_expired():
                    entry_size = entry.estimate_size()
                    
                    # Check memory limit
                    if self._current_memory + entry_size <= self.max_memory_bytes:
                        self._cache[key] = entry
                        self._access_order.append(key)
                        self._current_memory += entry_size
                        loaded_count += 1
            
            self._stats = data.get('stats', self._stats)
            logger.info(f"Loaded {loaded_count} entries from persistent cache")
            
        except Exception as e:
            logger.warning(f"Failed to load persistent cache: {e}")
