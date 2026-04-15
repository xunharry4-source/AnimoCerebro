"""Foundation version definitions and compatibility logic."""

from pydantic import BaseModel, ConfigDict, Field

FOUNDATION_VERSION: str = "1.0.0"
KERNEL_PROTOCOL_VERSION: str = "1.0.0"


class SystemVersionInfo(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    major: int
    minor: int
    patch: int
    build_id: str = ""

    def as_string(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"

    @classmethod
    def from_string(cls, v: str) -> "SystemVersionInfo":
        parts = v.split(".")
        if len(parts) < 3:
            raise ValueError(f"Invalid version string: {v!r}. Expected 'major.minor.patch'.")
        return cls(major=int(parts[0]), minor=int(parts[1]), patch=int(parts[2]))

    def is_compatible_with(self, other: "SystemVersionInfo") -> bool:
        """Same major version = compatible."""
        return self.major == other.major
