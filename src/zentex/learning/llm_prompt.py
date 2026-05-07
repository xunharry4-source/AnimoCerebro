from __future__ import annotations
"""
Learning LLM Prompt Builder — zentex.learning.llm_prompt

RESPONSIBILITY:
  Owns ALL prompt construction and input content preprocessing for the
  learning module's LLM / DSPy calls.

  No other file in zentex.learning may build or inline a prompt string or
  construct raw DSPy InputField values that are sent to an LLM.

CONTRACT:
  - DSPy inputs are split into typed segment fields (ToolDistillationInputs,
    ToolCriticInputs).  Each field represents a distinct intent and is
    preprocessed independently before being passed to the DSPy module.
  - Content preprocessing (URL validation, feedback trimming, schema capping)
    happens in dedicated _preprocess_*() helpers.
  - If an input field is None or empty it is replaced with a safe default so
    the LLM / DSPy always receives a complete, unambiguous structure.

SEGMENT / FIELD INTENT MAP:

  ToolDistillationInputs:
    doc_url          → 要蒸馏的工具来源文档（数据来源锚点）
    feedback_history → 上一轮沙箱/评审失败原因（迭代修正输入）

  ToolCriticInputs:
    doc_url               → 原始文档 URL（审查参考基准）
    proposed_tool_name    → 蒸馏步骤产出的工具名（待审对象标识）
    proposed_code_schema  → 蒸馏产出的 schema（待审内容主体）
    proposed_test_cases   → 蒸馏产出的测试用例（待审验证依据）

DOES NOT:
  - Import or use DSPy directly (no coupling to DSPy internals).
  - Call the LLM directly.
  - Own LearningStore writes or trace_id generation (caller's job).
  - Import from zentex.llm (avoids circular dependency).
"""


import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from zentex.common.prompt_template_files import render_prompt_template

logger = logging.getLogger(__name__)
_TEMPLATE_DIR = Path(__file__).resolve().with_name("prompt_templates")


def _render_template(name: str, values: dict[str, str]) -> str:
    return render_prompt_template(_TEMPLATE_DIR, name, values, error_prefix="learning")


# ---------------------------------------------------------------------------
# Content preprocessing limits
# ---------------------------------------------------------------------------

_MAX_DOC_URL_CHARS = 2_048           # Sanity cap on documentation URL length
_MAX_FEEDBACK_HISTORY_CHARS = 1_500  # Cap for accumulated sandbox feedback
_MAX_FEEDBACK_ENTRIES = 5            # Keep only the last N feedback entries
_MAX_SCHEMA_CHARS = 2_000            # Cap for proposed_code_schema block
_MAX_TEST_CASES_CHARS = 1_500        # Cap for proposed_test_cases block
_MAX_TOOL_NAME_CHARS = 100


# ---------------------------------------------------------------------------
# Input field dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ToolDistillationInputs:
    """Preprocessed, ready-to-use inputs for the ToolDistillationModule.

    Maps 1-to-1 to DSPy InputFields — unpack with **dataclass.asdict() or
    pass directly as kwargs.

    Field intent:
      doc_url          → 工具文档 URL，是蒸馏过程的唯一知识来源（数据来源锚点）
      feedback_history → 历次沙箱或 Critic 评审的失败原因摘要（迭代修正输入）
                         首次调用时为 "None"，后续调用随失败次数积累
    """

    doc_url: str
    feedback_history: str

    def to_dspy_kwargs(self) -> Dict[str, str]:
        """Return a dict ready to unpack into a DSPy module call."""
        return {
            "doc_url": self.doc_url,
            "feedback_history": self.feedback_history,
        }


@dataclass
class ToolCriticInputs:
    """Preprocessed, ready-to-use inputs for the ToolCriticModule.

    Maps 1-to-1 to DSPy InputFields.

    Field intent:
      doc_url               → 原始文档 URL，作为审查的参考基准（审查标准来源）
      proposed_tool_name    → 蒸馏步骤产出的工具名（待审对象标识）
      proposed_code_schema  → 蒸馏产出的 input_schema / output_schema / description
                              合并体（待审内容主体）
      proposed_test_cases   → 蒸馏产出的测试用例 JSON 数组（待审验证依据）
    """

    doc_url: str
    proposed_tool_name: str
    proposed_code_schema: str
    proposed_test_cases: str

    def to_dspy_kwargs(self) -> Dict[str, str]:
        """Return a dict ready to unpack into a DSPy module call."""
        return {
            "doc_url": self.doc_url,
            "proposed_tool_name": self.proposed_tool_name,
            "proposed_code_schema": self.proposed_code_schema,
            "proposed_test_cases": self.proposed_test_cases,
        }


# ---------------------------------------------------------------------------
# Public API — Tool Self-Study
# ---------------------------------------------------------------------------

def build_tool_distillation_inputs(
    doc_url: str,
    feedback_history: str = "None",
) -> ToolDistillationInputs:
    """Build and return preprocessed inputs for the ToolDistillationModule.

    Each field is cleaned independently before being packed into the dataclass.

    Args:
        doc_url:          Documentation URL to distill a cognitive tool from.
        feedback_history: Raw accumulated sandbox feedback from prior attempts.

    Returns:
        ToolDistillationInputs with clean, truncated field values.
    """
    return ToolDistillationInputs(
        doc_url=_preprocess_doc_url(doc_url),
        feedback_history=_preprocess_feedback_history(feedback_history),
    )


def build_tool_critic_inputs(
    doc_url: str,
    proposed_tool_name: str,
    proposed_code_schema: str,
    proposed_test_cases: str,
) -> ToolCriticInputs:
    """Build and return preprocessed inputs for the ToolCriticModule.

    Each field is cleaned independently before being packed into the dataclass.

    Args:
        doc_url:               Original documentation URL.
        proposed_tool_name:    Tool name produced by the distillation step.
        proposed_code_schema:  Schema JSON strings from distillation.
        proposed_test_cases:   Test cases JSON string from distillation.

    Returns:
        ToolCriticInputs with cleaned/truncated field values.
    """
    return ToolCriticInputs(
        doc_url=_preprocess_doc_url(doc_url),
        proposed_tool_name=_preprocess_tool_name(proposed_tool_name),
        proposed_code_schema=_preprocess_schema_block(proposed_code_schema),
        proposed_test_cases=_preprocess_test_cases(proposed_test_cases),
    )


def summarise_feedback_for_next_attempt(
    previous_feedback_history: str,
    new_critique: str,
    attempt_number: int,
) -> str:
    """Merge previous feedback with a new critique to form the next iteration's input.

    Keeps only the most recent _MAX_FEEDBACK_ENTRIES entries so the feedback
    string does not grow unboundedly across iterations.

    Args:
        previous_feedback_history: The feedback_history used in the last attempt.
        new_critique:              The critique_feedback from ToolCriticModule
                                   or sandbox rejection reason.
        attempt_number:            1-based attempt counter (used for labelling).

    Returns:
        Updated feedback_history string ready for the next distillation call.
    """
    new_entry = f"[尝试 {attempt_number}] {new_critique.strip()}"

    if previous_feedback_history in ("None", "", None):
        return new_entry

    existing = _split_feedback_entries(str(previous_feedback_history))
    kept = (existing + [new_entry])[-_MAX_FEEDBACK_ENTRIES:]

    merged = "\n\n".join(kept)
    if len(merged) > _MAX_FEEDBACK_HISTORY_CHARS:
        merged = "[…旧反馈已省略…]\n\n" + merged[-_MAX_FEEDBACK_HISTORY_CHARS:]

    return merged


# ---------------------------------------------------------------------------
# Field-level preprocessing helpers
# ---------------------------------------------------------------------------

def _preprocess_doc_url(url: str) -> str:
    """Validate and normalise the documentation URL field.

    Intent: 确保传入蒸馏模块的文档 URL 是合法、可读的 HTTP(S) 地址。
    """
    if not url or not str(url).strip():
        return "[未提供文档 URL]"

    url = str(url).strip()

    if not re.match(r"^https?://", url, re.IGNORECASE):
        logger.warning(
            "learning llm_prompt: doc_url missing http(s) scheme: %r", url[:80]
        )

    if len(url) > _MAX_DOC_URL_CHARS:
        logger.warning(
            "learning llm_prompt: doc_url truncated from %d to %d chars",
            len(url), _MAX_DOC_URL_CHARS,
        )
        return url[:_MAX_DOC_URL_CHARS]

    return url


def _preprocess_feedback_history(feedback: str) -> str:
    """Clean and trim the accumulated feedback field.

    Intent: 只保留最近几轮的失败原因，避免历史反馈淹没当轮的核心修正指令。

    - "None" or empty → "None" (no prior attempts / first call)
    - Long history    → keep last _MAX_FEEDBACK_ENTRIES blocks only
    """
    if not feedback or feedback.strip() in ("None", ""):
        return "None"

    entries = _split_feedback_entries(feedback.strip())
    kept = entries[-_MAX_FEEDBACK_ENTRIES:]
    result = "\n\n".join(e.strip() for e in kept if e.strip())

    if len(result) > _MAX_FEEDBACK_HISTORY_CHARS:
        result = "[…旧反馈已省略…]\n\n" + result[-_MAX_FEEDBACK_HISTORY_CHARS:]

    return result or "None"


def _preprocess_tool_name(name: str) -> str:
    """Sanitise the proposed tool name field.

    Intent: 确保传入 Critic 的工具名是合法、无噪声的短字符串。
    """
    if not name or not str(name).strip():
        return "[未提供工具名]"
    name = str(name).strip()
    if len(name) > _MAX_TOOL_NAME_CHARS:
        name = name[:_MAX_TOOL_NAME_CHARS] + "…（已截断）"
    return name


def _preprocess_schema_block(schema: str) -> str:
    """Cap the proposed_code_schema field.

    Intent: 避免超长 schema 字符串使 Critic 提示词膨胀，导致关键审查指令
    被稀释或截断。
    """
    if not schema or not str(schema).strip():
        return "[未提供 schema]"

    schema = str(schema).strip()
    if len(schema) > _MAX_SCHEMA_CHARS:
        logger.debug(
            "learning llm_prompt: schema truncated from %d to %d chars",
            len(schema), _MAX_SCHEMA_CHARS,
        )
        schema = schema[:_MAX_SCHEMA_CHARS] + "\n\n// [schema 过长，已截断]"

    return schema


def build_learning_maintenance_synthesis_prompt(
    *,
    top_tags: List[str],
    focus_topics: List[str],
    layer_distribution: Dict[str, int],
    cross_module_pressure: Dict[str, float] | None = None,
) -> str:
    """Return a prompt for LLM-based cross-module learning synthesis.

    Used by ``LearningService._summarize_maintenance_inputs()`` to produce an
    LLM-enriched summary from aggregated memory + reflection statistics, replacing
    the raw counter-based fallback.

    Output schema (strict JSON):
    {
      "summary": "<one-sentence learning synthesis>",
      "top_learning_themes": ["...", ...],
      "recommended_directions": ["...", ...]
    }
    """
    tag_block = ", ".join(top_tags[:10]) if top_tags else "（无标签数据）"
    topic_block = "; ".join(focus_topics[:5]) if focus_topics else "（无反思主题数据）"
    layer_block = ", ".join(f"{k}:{v}" for k, v in layer_distribution.items()) if layer_distribution else "（无分层数据）"
    pressure_block = (
        ", ".join(f"{k}:{float(v):.2f}" for k, v in cross_module_pressure.items())
        if cross_module_pressure
        else "（无跨模块压力数据）"
    )

    return _render_template(
        "maintenance_synthesis.md",
        {
            "TAG_BLOCK": tag_block,
            "TOPIC_BLOCK": topic_block,
            "LAYER_BLOCK": layer_block,
            "PRESSURE_BLOCK": pressure_block,
        },
    )


def _preprocess_test_cases(test_cases: str) -> str:
    """Cap the proposed_test_cases field.

    Intent: 避免超长测试用例列表撑大 Critic 提示词，只保留头部用例供审查。
    """
    if not test_cases or not str(test_cases).strip():
        return "[未提供测试用例]"

    test_cases = str(test_cases).strip()
    if len(test_cases) > _MAX_TEST_CASES_CHARS:
        logger.debug(
            "learning llm_prompt: test_cases truncated from %d to %d chars",
            len(test_cases), _MAX_TEST_CASES_CHARS,
        )
        test_cases = test_cases[:_MAX_TEST_CASES_CHARS] + "\n\n// [测试用例过长，已截断]"

    return test_cases


def _split_feedback_entries(feedback: str) -> List[str]:
    """Split a feedback_history string into per-attempt entries.

    Entries are delimited by "[尝试 N]" markers.  If no markers exist,
    the whole string is treated as one entry.
    """
    parts = re.split(r"(?=\[尝试\s+\d+\])", feedback)
    return [p.strip() for p in parts if p.strip()]
