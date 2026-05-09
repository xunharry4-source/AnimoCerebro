__all__ = ["build_q4_what_can_i_do_plugin"]


def build_q4_what_can_i_do_plugin(*args, **kwargs):
    from plugins.nine_questions.q4_what_can_i_do.q4_what_can_i_do_plugin import (
        build_q4_what_can_i_do_plugin as _build,
    )

    return _build(*args, **kwargs)
