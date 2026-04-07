from __future__ import annotations

from pydantic import BaseModel


class ReasoningBudget(BaseModel):
    """
    Controls resource usage during the learning cycle.
    """
    remaining_tokens: int = 0
