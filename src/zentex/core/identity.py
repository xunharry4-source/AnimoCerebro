from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from zentex.common.state import SharedStateStore

logger = logging.getLogger(__name__)


class IdentityKernel(BaseModel):
    """
    Immutable core of the Zentex subject.
    
    Ensures continuity and provides the baseline for all cognitive motivations.
    """
    identity_id: str = Field(..., description="Unique identifier for this identity anchor.")
    role_baseline: str = Field(..., description="The fundamental role definition (Q2 baseline).")
    mission_baseline: str = Field(..., description="The fundamental mission definition (Q8 baseline).")
    value_vetoes: List[str] = Field(default_factory=list, description="List of prohibited actions or values.")
    meta_motivation: str = Field(..., description="The underlying drive for existence and evolution.")
    continuity_constraints: List[str] = Field(default_factory=list, description="Rules governing identity evolution.")
    
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Continuity Lock logic
    lock_hash: Optional[str] = None

    def calculate_lock_hash(self) -> str:
        """Generate a deterministic hash of the core identity fields."""
        data = {
            "role": self.role_baseline,
            "mission": self.mission_baseline,
            "vetoes": sorted(self.value_vetoes),
            "motivation": self.meta_motivation,
        }
        encoded = json.dumps(data, sort_keys=True).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def verify_lock(self) -> bool:
        """Verify that the current state matches the identity lock."""
        if not self.lock_hash:
            return True  # Lock not set yet
        return self.calculate_lock_hash() == self.lock_hash

    def seal(self) -> None:
        """Lock the current identity state."""
        self.lock_hash = self.calculate_lock_hash()
        self.updated_at = datetime.now(timezone.utc)


class IdentityKernelStore:
    """
    Persistent storage for IdentityKernels.
    
    Uses SharedStateStore to handle both standalone (DiskCache) and cluster (Redis) modes.
    """
    def __init__(self, namespace: str = "identity"):
        self._store = SharedStateStore(namespace)

    def save_kernel(self, kernel: IdentityKernel, seal: bool = True) -> None:
        """Save an IdentityKernel to the store."""
        if seal and not kernel.lock_hash:
            kernel.seal()
        
        self._store.set(kernel.identity_id, kernel)
        logger.info(f"IdentityKernel '{kernel.identity_id}' saved (sealed={seal})")

    def get_kernel(self, identity_id: str) -> Optional[IdentityKernel]:
        """Retrieve an IdentityKernel by ID."""
        return self._store.get(identity_id, model_type=IdentityKernel)

    def list_kernels(self) -> Dict[str, IdentityKernel]:
        """List all identity kernels in the store."""
        return self._store.list_all(model_type=IdentityKernel)

    def verify_continuity(self, identity_id: str) -> bool:
        """Perform a physical verification of the identity continuity lock."""
        kernel = self.get_kernel(identity_id)
        if not kernel:
            return False
        
        is_valid = kernel.verify_lock()
        if not is_valid:
            logger.error(f"IDENTITY DRIFT DETECTED: Kernel '{identity_id}' lock mismatch!")
        return is_valid
