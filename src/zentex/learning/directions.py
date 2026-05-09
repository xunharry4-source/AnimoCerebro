from __future__ import annotations

from enum import Enum
from typing import Any, Dict


class LearningDirection(str, Enum):
    """
    Enum representing different learning directions or cognitive architectures.
    """
    TOOL_SELF_STUDY = "tool_self_study"
    CURIOSITY = "curiosity"
    NINE_QUESTION_INTEGRATION = "nine_question_integration"


def parse_learning_direction(direction: str | LearningDirection) -> LearningDirection:
    """
    Parse a public direction value.
    """
    if isinstance(direction, LearningDirection):
        return direction
    return LearningDirection(direction)


def describe_direction(direction: LearningDirection) -> Dict[str, Any]:
    """
    Describes the direction and its architecture reference.
    """
    mapping = {
        LearningDirection.TOOL_SELF_STUDY: {
            "ref": "TOOL_SELF_STUDY",
            "description": "Autonomous tool discovery and validation via documentation."
        },
        LearningDirection.CURIOSITY: {
            "ref": "G24",
            "description": "Exploratory curiosity-driven data ingest."
        },
        LearningDirection.NINE_QUESTION_INTEGRATION: {
            "ref": "NQ",
            "description": "Nine-question downstream learning persistence."
        }
    }
    return mapping.get(direction, {"ref": "UNKNOWN", "description": "N/A"})
