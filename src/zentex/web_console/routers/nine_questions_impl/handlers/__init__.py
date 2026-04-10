"""Nine questions handlers package.

Provides modular handlers for each of the 9 questions, along with shared utilities.
"""Handler modules for nine questions implementation.

This package provides modular organization of nine questions business logic:
- common_utils: Shared data normalization & serialization functions
- plugin_utils: Plugin discovery, mounting, and resolution functions
- trace_utils: Trace building and processing functions
- q1-q9_handlers: Question-specific evidence extraction and inference
"""

from .common_utils import (
    coerce_string_list,
    humanize_constraint_text,
    merge_context_payloads,
    normalize_health_status,
    normalize_ratio,
    serialize_contract_payload,
)

from .plugin_utils import (
    build_runtime_workspace_snapshot,
    derive_plugin_display_name,
    derive_plugin_function_description,
    functional_feature_codes_for_question,
    get_mounted_plugins_for_question,
    humanize_plugin_token,
    resolve_active_model_provider,
    resolve_active_nine_question_tool,
    run_full_nine_questions,
)

__all__ = [
    # common_utils
    "coerce_string_list",
    "humanize_constraint_text",
    "merge_context_payloads",
    "normalize_health_status",
    "normalize_ratio",
    "serialize_contract_payload",
    # plugin_utils
    "build_runtime_workspace_snapshot",
    "derive_plugin_display_name",
    "derive_plugin_function_description",
    "functional_feature_codes_for_question",
    "get_mounted_plugins_for_question",
    "humanize_plugin_token",
    "resolve_active_model_provider",
    "resolve_active_nine_question_tool",
    "run_full_nine_questions",
]
