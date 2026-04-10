"""
Nine Questions Router Implementation Modules

This package contains the modularized implementation of the nine questions router.
The original monolithic nine_questions.py has been split into focused modules
for better maintainability and testability.
"""

# Import router and constants from route_handlers (which contains all endpoint definitions)
from .route_handlers import (
    router,
    QUESTION_TITLES,
    get_latest_nine_questions_report,
)

# Re-export evidence extraction functions for backward compatibility if needed
from .evidence_q1 import (
    _extract_q1_inference_result,
    _extract_q1_llm_upgrade,
    _extract_q1_preprocessed_evidence,
)
from .evidence_q2 import (
    _extract_q2_inference_result,
    _extract_q2_preprocessed_evidence,
)
from .evidence_q3 import (
    _extract_q3_inference_result,
    _extract_q3_preprocessed_evidence,
)
from .evidence_q4 import (
    _extract_q4_inference_result,
    _extract_q4_preprocessed_evidence,
)
from .evidence_q5 import (
    _extract_q5_inference_result,
    _extract_q5_preprocessed_evidence,
)
from .evidence_q6 import (
    _extract_q6_inference_result,
    _extract_q6_preprocessed_evidence,
)
from .evidence_q7 import (
    _extract_q7_inference_result,
    _extract_q7_preprocessed_evidence,
)
from .evidence_q8 import (
    _extract_q8_inference_result,
    _extract_q8_preprocessed_evidence,
)
from .evidence_q9 import (
    _extract_q9_inference_result,
    _extract_q9_preprocessed_evidence,
)

# Re-export helper utilities
from .helpers import (
    _normalize_health_status,
    _serialize_contract_payload,
    _coerce_string_list,
    _humanize_constraint_text,
    _merge_context_payloads,
    _normalize_ratio,
    _build_runtime_workspace_snapshot,
)

# Re-export plugin utilities
from .plugin_utils import (
    _humanize_plugin_token,
    _derive_plugin_display_name,
    _derive_plugin_function_description,
    _get_mounted_plugins_for_question,
    _functional_feature_codes_for_question,
    FEATURE_EXPLANATIONS,
)

__all__ = [
    "router",
    "QUESTION_TITLES",
    "get_latest_nine_questions_report",
    # Evidence extraction functions
    "_extract_q1_inference_result",
    "_extract_q1_llm_upgrade",
    "_extract_q1_preprocessed_evidence",
    "_extract_q2_inference_result",
    "_extract_q2_preprocessed_evidence",
    "_extract_q3_inference_result",
    "_extract_q3_preprocessed_evidence",
    "_extract_q4_inference_result",
    "_extract_q4_preprocessed_evidence",
    "_extract_q5_inference_result",
    "_extract_q5_preprocessed_evidence",
    "_extract_q6_inference_result",
    "_extract_q6_preprocessed_evidence",
    "_extract_q7_inference_result",
    "_extract_q7_preprocessed_evidence",
    "_extract_q8_inference_result",
    "_extract_q8_preprocessed_evidence",
    "_extract_q9_inference_result",
    "_extract_q9_preprocessed_evidence",
    # Helper utilities
    "_normalize_health_status",
    "_serialize_contract_payload",
    "_coerce_string_list",
    "_humanize_constraint_text",
    "_merge_context_payloads",
    "_normalize_ratio",
    "_build_runtime_workspace_snapshot",
    # Plugin utilities
    "_humanize_plugin_token",
    "_derive_plugin_display_name",
    "_derive_plugin_function_description",
    "_get_mounted_plugins_for_question",
    "_functional_feature_codes_for_question",
    "FEATURE_EXPLANATIONS",
]
