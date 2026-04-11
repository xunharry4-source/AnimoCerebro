from __future__ import annotations

import enum
import logging
from typing import Protocol

try:
    import zstandard as zstd
except ImportError:
    zstd = None  # type: ignore

try:
    import lz4.frame as lz4
except ImportError:
    lz4 = None  # type: ignore

logger = logging.getLogger(__name__)


class CompressionAlgorithm(str, enum.Enum):
    NONE = "none"
    ZSTD = "zstd"
    LZ4 = "lz4"


class CompressionStrategy(Protocol):
    def compress(self, data: bytes) -> bytes:
        ...

    def decompress(self, data: bytes) -> bytes:
        ...


class NoCompressionStrategy:
    def compress(self, data: bytes) -> bytes:
        return data

    def decompress(self, data: bytes) -> bytes:
        return data


class ZstdCompressionStrategy:
    def __init__(self, level: int = 3):
        if zstd is None:
            raise ImportError("zstandard library not installed.")
        self.level = level
        self._compressor = zstd.ZstdCompressor(level=level)
        self._decompressor = zstd.ZstdDecompressor()

    def compress(self, data: bytes) -> bytes:
        return self._compressor.compress(data)

    def decompress(self, data: bytes) -> bytes:
        return self._decompressor.decompress(data)


class LZ4CompressionStrategy:
    def __init__(self):
        if lz4 is None:
            raise ImportError("lz4 library not installed.")

    def compress(self, data: bytes) -> bytes:
        return lz4.compress(data)

    def decompress(self, data: bytes) -> bytes:
        # Some lz4 versions use lz4.frame.decompress, others just lz4.decompress
        # The import at the top is lz4.frame as lz4
        return lz4.decompress(data)


class TieredCompressionService:
    """
    Production-grade tiered compression service for Memory Engine v2.0.

    Strategy mapping:
    - HOT (runtime_log)  -> LZ4 (Fastest, low overhead < 5ms)
    - WARM (reflection)  -> Zstd L3 (Balanced, 4-6x ratio)
    - COLD (archive)     -> Zstd L9 (Aggressive, 6-10x ratio)
    """

    # Magic bytes for detection
    ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"
    LZ4_MAGIC = b"\x04\x22\x4d\x18"

    def __init__(self):
        self._strategies: dict[str, CompressionStrategy] = {
            "none": NoCompressionStrategy(),
        }
        
        if lz4:
            self._strategies["lz4"] = LZ4CompressionStrategy()
        
        if zstd:
            self._strategies["zstd_3"] = ZstdCompressionStrategy(level=3)
            self._strategies["zstd_9"] = ZstdCompressionStrategy(level=9)

    def get_strategy_for_tier(self, tier: str) -> CompressionStrategy:
        """Map memory tier to specific strategy implementation."""
        t = tier.lower()
        if t == "hot":
            return self._strategies.get("lz4", self._strategies["none"])
        elif t == "warm":
            return self._strategies.get("zstd_3", self._strategies["none"])
        elif t == "cold":
            return self._strategies.get("zstd_9", self._strategies["none"])
        return self._strategies["none"]

    def compress_for_tier(self, data: bytes, tier: str) -> bytes:
        """Compress data using the optimal strategy for the given tier."""
        strategy = self.get_strategy_for_tier(tier)
        return strategy.compress(data)

    def decompress(self, data: bytes) -> bytes:
        """Decompress data with automatic magic-byte detection (Backward Compatible)."""
        if not data or len(data) < 4:
            return data

        # Detect by magic bytes
        if data.startswith(self.ZSTD_MAGIC):
            # Use any Zstd decompressor (they are compatible across levels)
            strategy = self._strategies.get("zstd_3") or self._strategies.get("zstd_9")
            if strategy:
                return strategy.decompress(data)
        elif data.startswith(self.LZ4_MAGIC):
            strategy = self._strategies.get("lz4")
            if strategy:
                return strategy.decompress(data)
        
        # Fallback to NONE
        return data
