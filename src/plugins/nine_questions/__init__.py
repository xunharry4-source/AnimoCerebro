from plugins.nine_questions.q1_where_am_i import (
    build_q1_where_am_i_capability_patch_plugin,
    build_q1_where_am_i_plugin,
)
from plugins.nine_questions.q2_who_am_i import build_q2_who_am_i_plugin
from plugins.nine_questions.q3_what_do_i_have import build_q3_what_do_i_have_plugin
from plugins.nine_questions.q4_what_can_i_do import (
    build_q4_what_can_i_do_plugin,
    build_q4_capability_patch_plugin,
)
from plugins.nine_questions.q5_what_am_i_allowed_to_do import (
    build_q5_what_am_i_allowed_to_do_plugin,
    build_q5_compliance_patch_plugin,
)
from plugins.nine_questions.q6_what_should_i_not_do import (
    build_q6_what_should_i_not_do_plugin,
    build_q6_security_patch_plugin,
)
from plugins.nine_questions.q7_what_else_can_i_do import (
    build_q7_what_else_can_i_do_plugin,
    build_q7_alternative_patch_plugin,
)
from plugins.nine_questions.q8_what_should_i_do_now import (
    build_q8_what_should_i_do_now_plugin,
    build_q8_objective_patch_plugin,
)
from plugins.nine_questions.q9_how_should_i_act import (
    build_q9_how_should_i_act_plugin,
    build_q9_posture_patch_plugin,
)

__all__ = [
    "build_q1_where_am_i_plugin",
    "build_q1_where_am_i_capability_patch_plugin",
    "build_q2_who_am_i_plugin",
    "build_q3_what_do_i_have_plugin",
    "build_q4_what_can_i_do_plugin",
    "build_q4_capability_patch_plugin",
    "build_q5_what_am_i_allowed_to_do_plugin",
    "build_q5_compliance_patch_plugin",
    "build_q6_what_should_i_not_do_plugin",
    "build_q6_security_patch_plugin",
    "build_q7_what_else_can_i_do_plugin",
    "build_q7_alternative_patch_plugin",
    "build_q8_what_should_i_do_now_plugin",
    "build_q8_objective_patch_plugin",
    "build_q9_how_should_i_act_plugin",
    "build_q9_posture_patch_plugin",
]
