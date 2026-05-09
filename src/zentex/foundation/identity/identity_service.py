"""Identity service — manages identity state for the foundation module."""

from zentex.foundation.identity.identity_contract import IdentityCore, IdentityVersion


class IdentityService:
    """Manages a single immutable IdentityCore for the lifetime of the foundation.

    After construction no mutation of the stored identity is permitted.
    All public methods are read-only operations.
    """

    def __init__(self, identity: IdentityCore) -> None:
        self._identity: IdentityCore = identity

    def get_snapshot(self) -> IdentityCore:
        """Return the stored identity.

        The returned object is a frozen Pydantic model — safe to hand out directly.
        """
        return self._identity

    def validate_request(self, field: str, new_value: str) -> bool:
        """Return False if the field is locked, True if the change would be permitted."""
        return not self._identity.is_field_locked(field)

    def detect_drift(self, other: IdentityCore) -> dict:
        """Compare role_name, mission, and core_values between stored identity and other.

        Returns:
            {
                "drifted_fields": list[str],   # names of fields whose values differ
                "is_clean": bool,              # True when no drift detected
            }
        """
        drifted: list[str] = []

        if self._identity.role_name != other.role_name:
            drifted.append("role_name")

        if self._identity.mission != other.mission:
            drifted.append("mission")

        if self._identity.core_values != other.core_values:
            drifted.append("core_values")

        return {
            "drifted_fields": drifted,
            "is_clean": len(drifted) == 0,
        }

    def get_version(self) -> IdentityVersion:
        """Return the current identity version."""
        return self._identity.version
