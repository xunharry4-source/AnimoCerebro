from __future__ import annotations

"""
Shared versioning helpers for upgrade planning.

This file centralizes candidate version derivation so LLM upgrades and plugin
upgrades follow the same release semantics instead of each module inventing its
own version bump logic.
"""

from enum import Enum


class UpgradeChangeScope(str, Enum):
    """Supported semantic upgrade scopes for candidate planning."""

    PATCH = "patch"
    MINOR = "minor"
    MAJOR = "major"


def derive_candidate_version(baseline_version: str, scope: UpgradeChangeScope) -> str:
    """
    Derive the next candidate version from a semantic baseline version.

    Fail-closed:
    - requires exactly three numeric semantic version components
    - always appends a `-candidate` suffix so planning cannot be confused with
      an already-promoted active release
    """

    raw = (baseline_version or "").strip()
    if not raw:
        raise ValueError("baseline_version must not be empty")

    base = raw.split("-", 1)[0]
    parts = base.split(".")
    if len(parts) != 3 or any(not part.isdigit() for part in parts):
        raise ValueError(
            "baseline_version must use semantic versioning like '1.2.3'"
        )

    major, minor, patch = (int(part) for part in parts)
    if scope is UpgradeChangeScope.PATCH:
        patch += 1
    elif scope is UpgradeChangeScope.MINOR:
        minor += 1
        patch = 0
    else:
        major += 1
        minor = 0
        patch = 0

    return f"{major}.{minor}.{patch}-candidate"
