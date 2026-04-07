from __future__ import annotations

# Backwards-compatible import shim for older test/module paths.

from plugins.nine_questions.q8_what_should_i_do_now.models import ObjectiveProfile
from plugins.nine_questions.q8_what_should_i_do_now.q8_what_should_i_do_now_plugin import (
    WhatShouldIDoNowPlugin,
)

__all__ = ["WhatShouldIDoNowPlugin", "ObjectiveProfile"]

