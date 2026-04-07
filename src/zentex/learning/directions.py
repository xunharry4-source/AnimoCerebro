from __future__ import annotations

from enum import Enum
from typing import Any, Dict


class LearningDirection(str, Enum):
    """
    Enum representing different learning directions or cognitive architectures.
    """
    G16_TOOL_SELF_STUDY = "g16_tool_self_study"
    G24_CURIOSITY = "g24_curiosity"


def describe_direction(direction: LearningDirection) -> Dict[str, Any]:
    """
    Describes the direction and its architecture reference.
    """
    mapping = {
        LearningDirection.G16_TOOL_SELF_STUDY: {
            "ref": "G16",
            "description": "Autonomous tool discovery and validation via documentation."
        },
        LearningDirection.G24_CURIOSITY: {
            "ref": "G24",
            "description": "Exploratory curiosity-driven data ingest."
        }
    }
    return mapping.get(direction, {"ref": "UNKNOWN", "description": "N/A"})
