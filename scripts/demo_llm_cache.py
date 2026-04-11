#!/usr/bin/env python3
"""
Quick demo script to verify LLM cache functionality.

Usage:
    python scripts/demo_llm_cache.py
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from zentex.llm.cache import LLMResponseCache


def demo_basic_cache():
    """Demonstrate basic cache operations."""
    print("=" * 60)
    print("LLM Response Cache Demo")
    print("=" * 60)
    
    # Create cache instance
    cache = LLMResponseCache(
        max_size=100,
        max_memory_mb=10,
        default_ttl=60,
    )
    
    print("\n1. Initial cache stats:")
    stats = cache.get_stats()
    print(f"   Size: {stats['current_size']}/{stats['max_size']}")
    print(f"   Memory: {stats['current_memory_mb']:.2f}MB/{stats['max_memory_mb']:.2f}MB")
    print(f"   Hit rate: {stats['hit_rate']:.1%}")
    
    # Simulate LLM calls
    print("\n2. Simulating LLM calls...")
    
    # First call - cache miss
    print("   Call 1: 'What is AI?' (cache miss)")
    result = cache.get("What is AI?", {}, "gpt-4")
    print(f"   Result: {result}")
    
    # Cache the response
    print("   Caching response...")
    cache.set("What is AI?", {}, "gpt-4", {"answer": "AI is artificial intelligence"})
    
    # Second call - cache hit
    print("\n   Call 2: 'What is AI?' (cache hit)")
    result = cache.get("What is AI?", {}, "gpt-4")
    print(f"   Result: {result}")
    
    # Different question - cache miss
    print("\n   Call 3: 'What is ML?' (cache miss)")
    result = cache.get("What is ML?", {}, "gpt-4")
    print(f"   Result: {result}")
    
    print("\n3. Final cache stats:")
    stats = cache.get_stats()
    print(f"   Hits: {stats['hits']}")
    print(f"   Misses: {stats['misses']}")
    print(f"   Hit rate: {stats['hit_rate']:.1%}")
    print(f"   Total requests: {stats['total_requests']}")
    print(f"   Current size: {stats['current_size']}")


def demo_cache_expiration():
    """Demonstrate cache expiration."""
    print("\n" + "=" * 60)
    print("Cache Expiration Demo")
    print("=" * 60)
    
    import time
    
    cache = LLMResponseCache(
        max_size=100,
        default_ttl=2,  # 2 seconds TTL
    )
    
    print("\n1. Setting cache with 2s TTL...")
    cache.set("test", {}, "m", "value", ttl=2)
    
    print("   Immediate get:", cache.get("test", {}, "m"))
    
    print("\n2. Waiting 3 seconds for expiration...")
    time.sleep(3)
    
    print("   Get after expiration:", cache.get("test", {}, "m"))
    
    stats = cache.get_stats()
    print(f"\n3. Expirations count: {stats['expirations']}")


def demo_lru_eviction():
    """Demonstrate LRU eviction."""
    print("\n" + "=" * 60)
    print("LRU Eviction Demo")
    print("=" * 60)
    
    cache = LLMResponseCache(max_size=3, max_memory_mb=10)
    
    print("\n1. Adding 3 entries (max_size=3)...")
    cache.set("p1", {}, "m", "r1")
    cache.set("p2", {}, "m", "r2")
    cache.set("p3", {}, "m", "r3")
    print(f"   Cache size: {len(cache._cache)}")
    
    print("\n2. Accessing p1 (makes it recently used)...")
    cache.get("p1", {}, "m")
    
    print("\n3. Adding p4 (should evict p2 - least recently used)...")
    cache.set("p4", {}, "m", "r4")
    print(f"   Cache size: {len(cache._cache)}")
    
    print("\n4. Checking which entries exist:")
    print(f"   p1: {cache.get('p1', {}, 'm')}")  # Should exist
    print(f"   p2: {cache.get('p2', {}, 'm')}")  # Should be None (evicted)
    print(f"   p3: {cache.get('p3', {}, 'm')}")  # Should exist
    print(f"   p4: {cache.get('p4', {}, 'm')}")  # Should exist
    
    stats = cache.get_stats()
    print(f"\n5. LRU evictions: {stats['evictions_lru']}")


def demo_persistence():
    """Demonstrate cache persistence."""
    print("\n" + "=" * 60)
    print("Cache Persistence Demo")
    print("=" * 60)
    
    import tempfile
    
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_file = Path(tmpdir) / "test_cache.json"
        
        print(f"\n1. Creating cache with persistence: {cache_file}")
        cache1 = LLMResponseCache(
            max_size=100,
            persist_path=cache_file,
        )
        
        print("   Adding entries...")
        cache1.set("p1", {}, "m", "response1")
        cache1.set("p2", {}, "m", "response2")
        
        print(f"   Cache 1 size: {len(cache1._cache)}")
        
        print("\n2. Creating new cache instance (loads from disk)...")
        cache2 = LLMResponseCache(
            max_size=100,
            persist_path=cache_file,
        )
        
        print(f"   Cache 2 size: {len(cache2._cache)}")
        print(f"   p1 from cache 2: {cache2.get('p1', {}, 'm')}")
        print(f"   p2 from cache 2: {cache2.get('p2', {}, 'm')}")


if __name__ == "__main__":
    try:
        demo_basic_cache()
        demo_cache_expiration()
        demo_lru_eviction()
        demo_persistence()
        
        print("\n" + "=" * 60)
        print("✅ All demos completed successfully!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ Demo failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
