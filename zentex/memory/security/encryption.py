from __future__ import annotations

import base64
import os
import logging
import threading
from typing import Protocol

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.backends import default_backend
except ImportError:
    AESGCM = None  # type: ignore
    HKDF = None  # type: ignore
    hashes = None # type: ignore
    default_backend = None # type: ignore

logger = logging.getLogger(__name__)

class EncryptionStrategy(Protocol):
    def encrypt(self, data: bytes) -> bytes:
        ...

    def decrypt(self, data: bytes) -> bytes:
        ...

class NoEncryptionStrategy:
    def encrypt(self, data: bytes) -> bytes:
        return data

    def decrypt(self, data: bytes) -> bytes:
        return data

class AESGCMEncryptionStrategy:
    """
    AES-256-GCM authenticated encryption service.
    
    Structure:
    [MAGIC: 8 bytes] 'ZMEM_ENC'
    [NONCE: 12 bytes]
    [PAYLOAD: variable] (contains encrypted data + 16 byte auth tag appended by AESGCM)
    """
    MAGIC = b"ZMEM_ENC"
    NONCE_SIZE = 12

    def __init__(self, key: bytes):
        if AESGCM is None:
            raise ImportError("cryptography library not installed.")
        # Ensure key is 32 bytes for AES-256
        if len(key) != 32:
            raise ValueError("AES-256 key must be exactly 32 bytes.")
        self._aesgcm = AESGCM(key)

    def encrypt(self, data: bytes) -> bytes:
        nonce = os.urandom(self.NONCE_SIZE)
        # AESGCM.encrypt returns ciphertext + tag
        ciphertext = self._aesgcm.encrypt(nonce, data, self.MAGIC)
        return self.MAGIC + nonce + ciphertext

    def decrypt(self, data: bytes) -> bytes:
        if not data.startswith(self.MAGIC):
            raise ValueError("Invalid magic bytes for encrypted payload.")
        
        offset = len(self.MAGIC)
        nonce = data[offset : offset + self.NONCE_SIZE]
        ciphertext = data[offset + self.NONCE_SIZE :]
        
        return self._aesgcm.decrypt(nonce, ciphertext, self.MAGIC)

class EnterpriseEncryptionService:
    """
    Enterprise-grade encryption service for Memory Engine v2.0.

    Hierarchy:
    Master Key (Environment) -> HKDF -> Data Key (Per-Context)

    Algorithms:
    - KDF: HKDF-SHA256
    - AEAD: AES-256-GCM (Authenticated Encryption)
    """

    # Static salt for Master Key derivation. 
    # In multi-tenant environments, this could be per-tenant.
    SALT = b"zentex_memory_v2_encryption_salt"
    _missing_key_logged = False

    def __init__(self, master_key_str: str | None = None):
        self._master_key = master_key_str or os.environ.get("MEMORY_MASTER_KEY")
        self.enabled = (self._master_key is not None)
        self._cache: dict[str, AESGCMEncryptionStrategy] = {}
        self._lock = threading.Lock()

        if self.enabled:
            logger.info("Enterprise encryption service initialized (Master Key present).")
        else:
            if not EnterpriseEncryptionService._missing_key_logged:
                logger.info("No master key found. Memory encryption remains disabled.")
                EnterpriseEncryptionService._missing_key_logged = True

    def _derive_key(self, context: str) -> bytes:
        """Derive a context-specific 32-byte key from the master key."""
        if not self._master_key:
            raise RuntimeError("Key derivation failed: No master key.")

        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=self.SALT,
            info=f"memory_context:{context}".encode("utf-8"),
            backend=default_backend()
        )
        return hkdf.derive(self._master_key.encode("utf-8"))

    def get_strategy_for_context(self, context: str) -> EncryptionStrategy:
        """Get or create a strategy for the given context (e.g. tenant_id)."""
        if not self.enabled:
            return NoEncryptionStrategy()

        with self._lock:
            if context not in self._cache:
                derived_key = self._derive_key(context)
                self._cache[context] = AESGCMEncryptionStrategy(derived_key)
            return self._cache[context]

    def encrypt(self, data: bytes, context: str = "default") -> bytes:
        """Encrypt data using the context-specific data key."""
        if not self.enabled:
            return data
        strategy = self.get_strategy_for_context(context)
        return strategy.encrypt(data)

    def decrypt(self, data: bytes, context: str = "default") -> bytes:
        """Decrypt data, attempting current context then fallback detection."""
        if not self.enabled:
            return data
        if not data.startswith(AESGCMEncryptionStrategy.MAGIC):
            return data

        try:
            strategy = self.get_strategy_for_context(context)
            return strategy.decrypt(data)
        except Exception:
            # Fallback: if wrong context, decryption will fail because of G38 magic or Tag failure.
            # In a real system, we might search multiple contexts or store key_id in header.
            logger.error(f"Decryption failed for context: {context}")
            raise
