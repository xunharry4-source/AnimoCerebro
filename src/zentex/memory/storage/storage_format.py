from __future__ import annotations

import struct
import logging
from typing import Any, Protocol

try:
    import msgpack
except ImportError:
    msgpack = None  # type: ignore

logger = logging.getLogger(__name__)

class Serializer(Protocol):
    def serialize(self, data: dict[str, Any]) -> bytes:
        ...

    def deserialize(self, data: bytes) -> dict[str, Any]:
        ...

class MessagePackSerializer:
    """
    Binary serialization using MessagePack for Memory Engine v2.0.

    Structure:
    [MAGIC: 4 bytes] 'ZMEM'
    [VERSION: 1 byte] Current: 1
    [FLAGS: 1 byte] (bit 0: compressed, bit 1: encrypted, bit 2: dual-write)
    [TIMESTAMP: 4 bytes] Unsigned int (Unix epoch bits)
    [PAYLOAD: variable] (MsgPack'ed data)
    """
    MAGIC = b"ZMEM"
    VERSION = 1
    HEADER_SIZE = 10
    HEADER_FORMAT = "<4sBB I" # Magic, Version, Flags, Timestamp

    def __init__(self):
        if msgpack is None:
            raise ImportError("msgpack library not installed.")

    def serialize(self, data: dict[str, Any], compressed: bool = False, encrypted: bool = False, dual_write: bool = False) -> bytes:
        import time
        flags = 0
        if compressed: flags |= 0x01
        if encrypted: flags |= 0x02
        if dual_write: flags |= 0x04
        
        # Use short timestamp to save space while keeping versioning trace
        ts = int(time.time()) & 0xFFFFFFFF
        header = struct.pack(self.HEADER_FORMAT, self.MAGIC, self.VERSION, flags, ts)
        
        # Optimization: use_bin_type=True for efficiency, pack to bytes
        payload = msgpack.packb(data, use_bin_type=True)
        return header + payload

    def deserialize(self, data: bytes) -> dict[str, Any]:
        if not data.startswith(self.MAGIC):
            raise ValueError("Invalid magic bytes for ZMEM storage format.")
        
        if len(data) < self.HEADER_SIZE:
            raise ValueError("Payload too small for ZMEM header.")

        header = data[:self.HEADER_SIZE]
        _, version, flags, ts = struct.unpack(self.HEADER_FORMAT, header)
        
        if version > self.VERSION:
            logger.warning(f"ZMEM version forward-compatibility warning: file v{version}, local v{self.VERSION}")
        
        payload = data[self.HEADER_SIZE:]
        return msgpack.unpackb(payload, raw=False)

    @classmethod
    def is_binary(cls, data: bytes) -> bool:
        return data.startswith(cls.MAGIC)
