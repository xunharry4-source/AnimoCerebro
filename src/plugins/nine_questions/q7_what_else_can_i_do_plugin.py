from __future__ import annotations

# Backwards-compatible import shim for older test/module paths.

from plugins.nine_questions.q7_what_else_can_i_do.models import AlternativeStrategyProfile
from plugins.nine_questions.q7_what_else_can_i_do.q7_what_else_can_i_do_plugin import (
    WhatElseCanIDoPlugin,
)

__all__ = ["WhatElseCanIDoPlugin", "AlternativeStrategyProfile"]

