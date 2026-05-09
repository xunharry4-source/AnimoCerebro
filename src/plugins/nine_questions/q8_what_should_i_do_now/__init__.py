__all__ = ["build_q8_what_should_i_do_now_plugin"]


def build_q8_what_should_i_do_now_plugin(*args, **kwargs):
    from plugins.nine_questions.q8_what_should_i_do_now.q8_what_should_i_do_now_plugin import (
        build_q8_what_should_i_do_now_plugin as _build,
    )

    return _build(*args, **kwargs)
