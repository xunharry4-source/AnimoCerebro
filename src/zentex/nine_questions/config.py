from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from zentex.launcher.config import ConfigLoadError, load_yaml_config


DEFAULT_NINE_QUESTIONS_CONFIG_PATH = Path("config") / "nine_questions.yml"


@dataclass(frozen=True)
class NineQuestionsExecuteAllConfig:
    skip_refresh_when_q1_q3_unchanged: bool = True


def _as_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def load_nine_questions_execute_all_config(
    config_path: Path | str = DEFAULT_NINE_QUESTIONS_CONFIG_PATH,
) -> NineQuestionsExecuteAllConfig:
    path = Path(config_path)
    payload: dict[str, Any] = {}
    if path.exists():
        try:
            payload = load_yaml_config(path)
        except ConfigLoadError:
            raise

    section = payload.get("nine_questions")
    section = section if isinstance(section, dict) else {}
    execute_all = section.get("execute_all")
    execute_all = execute_all if isinstance(execute_all, dict) else {}

    default_skip = NineQuestionsExecuteAllConfig.skip_refresh_when_q1_q3_unchanged
    configured_skip = _as_bool(
        execute_all.get(
            "skip_refresh_when_q1_q3_unchanged",
            execute_all.get(
                "skip_refresh_when_any_data_exists",
                execute_all.get("skip_full_when_q1_q3_unchanged"),
            ),
        ),
        default_skip,
    )
    env_skip = os.environ.get(
        "ZENTEX_NINE_QUESTIONS_SKIP_REFRESH_WHEN_Q1_Q3_UNCHANGED",
        os.environ.get("ZENTEX_NINE_QUESTIONS_SKIP_REFRESH_WHEN_ANY_DATA_EXISTS"),
    )
    return NineQuestionsExecuteAllConfig(
        skip_refresh_when_q1_q3_unchanged=_as_bool(env_skip, configured_skip),
    )
