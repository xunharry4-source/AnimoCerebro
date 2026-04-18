"""
Task Decomposition LLM Prompt Builder — zentex.tasks.core.llm_prompt

RESPONSIBILITY:
  Owns ALL prompt construction and input content preprocessing for task
  decomposition LLM calls.  No other file in zentex.tasks may build or inline
  a prompt string that is sent to an LLM for decomposition purposes.

CONTRACT:
  - Prompt content is split into typed segment fields (DecompositionPromptSegments).
    Each segment represents a distinct intent and is built independently.
  - Content preprocessing (mission truncation, memory context extraction,
    requirements cleaning) happens in dedicated _preprocess_*() helpers.
  - The LLM receives a compact, well-structured prompt — not a raw data dump.
  - If an input field is None or empty it is replaced with an explicit
    "[未提供]" marker so the model always sees a complete structure.

SEGMENT STRUCTURE (in assembly order):
  1. role          — declares the LLM's identity as Task Decomposer
  2. constraints   — hard rules every subtask output must satisfy
  3. mission       — the actual task title and description being decomposed
  4. memory        — historical execution context (optional, aids decomposition)
  5. requirements  — caller-supplied additional constraints (optional)
  6. output_format — JSON example showing the exact expected structure

DOES NOT:
  - Call the LLM directly.
  - Own transcript_store writes or trace_id generation (caller's job).
  - Import from zentex.llm (avoids circular dependency).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Content preprocessing limits
# ---------------------------------------------------------------------------

_MAX_MISSION_TITLE_CHARS = 200
_MAX_MISSION_CONTENT_CHARS = 2_000   # Raw content cap
_MAX_MEMORY_TEXT_CHARS = 1_500       # Memory / historical context cap
_MAX_REQUIREMENT_CHARS = 300         # Per-requirement entry cap
_MAX_REQUIREMENTS = 10               # Max requirements shown in prompt
_MAX_SUBTASKS = 8
_MIN_SUBTASKS = 3

_SECTION_SEP = "\n\n"


# ---------------------------------------------------------------------------
# Segment dataclass
# ---------------------------------------------------------------------------

@dataclass
class DecompositionPromptSegments:
    """All named segments that make up a task decomposition prompt.

    Each field represents a distinct intent.  Empty fields are skipped
    during assembly — no blank sections appear in the final prompt.

    Segment intent map:
      role          → 告知 LLM 它是谁、它要做什么（角色定义）
      constraints   → 告知 LLM 输出的硬性约束（格式与数量）
      mission       → 提供要拆解的具体任务内容（核心输入）
      memory        → 提供历史经验辅助拆解（可选辅助输入）
      requirements  → 提供调用方的附加限制（可选补充约束）
      output_format → 告知 LLM 输出示例，消除格式歧义（输出示例）
    """

    # 1. Role — 角色定义
    role: str = ""

    # 2. Constraints — 硬性约束（字段完整性、枚举值、数量范围）
    constraints: str = ""

    # 3. Mission — 核心任务输入（标题 + 描述）
    mission: str = ""

    # 4. Memory — 历史经验辅助（可选）
    memory: str = ""

    # 5. Requirements — 附加限制（可选）
    requirements: str = ""

    # 6. Output format — JSON 示例
    output_format: str = ""

    def assemble(self) -> str:
        """Join non-empty segments in order and return the complete prompt string."""
        parts = [
            seg.strip()
            for seg in (
                self.role,
                self.constraints,
                self.mission,
                self.memory,
                self.requirements,
                self.output_format,
            )
            if seg and seg.strip()
        ]
        return _SECTION_SEP.join(parts)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_decomposition_prompt(
    mission_title: str,
    mission_content: str,
    memory_text: Optional[str] = None,
    extra_requirements: Optional[List[str]] = None,
) -> str:
    """Return a fully-preprocessed task decomposition prompt.

    Builds each segment independently, then assembles them in order.

    Args:
        mission_title:       Human-readable mission name.
        mission_content:     Mission description / notes (raw, will be preprocessed).
        memory_text:         Historical memory / context from previous executions.
        extra_requirements:  Any caller-supplied additional constraints.

    Returns:
        Complete prompt string ready for the LLM.
    """
    segs = DecompositionPromptSegments(
        role=_build_role_segment(),
        constraints=_build_constraints_segment(),
        mission=_build_mission_segment(mission_title, mission_content),
        memory=_build_memory_segment(memory_text),
        requirements=_build_requirements_segment(extra_requirements),
        output_format=_build_output_format_segment(),
    )
    return segs.assemble()


def build_decomposition_context_dict(
    mission_title: str,
    mission_content: str,
) -> Dict[str, Any]:
    """Return the context dict to store in the transcript alongside the prompt.

    This dict is NOT sent to the LLM — it is written to the transcript_store
    for auditability and replay.  It preserves pre-preprocessing originals.

    Args:
        mission_title:   Original mission title.
        mission_content: Original mission content (may be long).

    Returns:
        Dict suitable for transcript_store.write_entry(payload=...).
    """
    from datetime import datetime, timezone

    return {
        "mission_title": mission_title,
        "mission_content_preview": mission_content[:500] if mission_content else "[未提供]",
        "mission_content_length": len(mission_content) if mission_content else 0,
        "requested_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Segment builders — one function per segment field
# ---------------------------------------------------------------------------

def _build_role_segment() -> str:
    """Segment 1 — Role definition: who the LLM is and its top-level task."""
    return (
        f"你是 Zentex 的任务拆解引擎（Task Decomposer）。\n\n"
        f"你的职责是把一个高层任务（mission）拆解为 "
        f"{_MIN_SUBTASKS}–{_MAX_SUBTASKS} 个可直接执行的子任务（subtask）。"
    )


def _build_constraints_segment() -> str:
    """Segment 2 — Hard output constraints the LLM must not violate."""
    return (
        "## 硬性约束（必须严格遵守）\n\n"
        "- 输出必须是合法 JSON，顶层 key 为 `subtasks`（数组）\n"
        f"- 子任务数量必须在 {_MIN_SUBTASKS}–{_MAX_SUBTASKS} 之间\n"
        "- 每个子任务必须包含以下字段（缺一不可）：\n"
        "  - `local_id`：唯一标识，格式 step-1, step-2, …（不可重复）\n"
        "  - `title`：子任务标题（简洁，不超过 50 字）\n"
        "  - `task_type`：枚举之一 — "
        "cognitive_step | agent_delegation | system_action | intervention | mission\n"
        "  - `content`：子任务描述（具体可执行，不超过 200 字）\n"
        "  - `objective`：成功标准（不超过 100 字）\n"
        "  - `requirements`：前置条件列表（字符串数组，可为空数组）\n"
        "  - `depends_on`：依赖的 local_id 列表（只能引用本批次 local_id，可为空数组）\n"
        "  - `coordination_mode`：枚举之一 — parallel | bundle | sequential\n"
        "- 不得凭空发明能力；requirements 必须是可验证的具体条件\n"
        "- 请直接返回 JSON，不要包含任何额外解释文字"
    )


def _build_mission_segment(mission_title: str, mission_content: str) -> str:
    """Segment 3 — The core task input (title + description)."""
    clean_title = _preprocess_title(mission_title)
    clean_content = _preprocess_mission_content(mission_content)
    return (
        "## 待拆解任务\n\n"
        f"**任务标题**：{clean_title}\n\n"
        f"**任务描述**：\n{clean_content}"
    )


def _build_memory_segment(memory_text: Optional[str]) -> str:
    """Segment 4 — Optional historical execution context to inform decomposition."""
    if not memory_text or not memory_text.strip():
        return ""
    text = memory_text.strip()
    if len(text) > _MAX_MEMORY_TEXT_CHARS:
        text = f"[…已省略旧历史，保留最近记录…]\n\n{text[-_MAX_MEMORY_TEXT_CHARS:]}"
    return f"## 历史经验与上下文\n\n{text}"


def _build_requirements_segment(requirements: Optional[List[str]]) -> str:
    """Segment 5 — Optional caller-supplied additional constraints."""
    if not requirements:
        return ""

    cleaned: List[str] = []
    for req in requirements[:_MAX_REQUIREMENTS]:
        r = str(req).strip()
        if not r:
            continue
        if len(r) > _MAX_REQUIREMENT_CHARS:
            r = r[:_MAX_REQUIREMENT_CHARS] + "…（已截断）"
        cleaned.append(r)

    if not cleaned:
        return ""

    lines = "\n".join(f"{i + 1}. {r}" for i, r in enumerate(cleaned))
    omitted = max(0, len(requirements) - _MAX_REQUIREMENTS)
    note = f"\n（还有 {omitted} 条要求已省略）" if omitted else ""
    return f"## 附加要求\n\n{lines}{note}"


def _build_output_format_segment() -> str:
    """Segment 6 — JSON example showing the exact structure expected."""
    return (
        "## 输出格式示例\n\n"
        "```json\n"
        "{\n"
        '  "subtasks": [\n'
        "    {\n"
        '      "local_id": "step-1",\n'
        '      "title": "示例子任务标题",\n'
        '      "task_type": "cognitive_step",\n'
        '      "content": "具体执行内容描述（可操作）",\n'
        '      "objective": "成功完成后的验收标准",\n'
        '      "requirements": ["前置条件A"],\n'
        '      "depends_on": [],\n'
        '      "coordination_mode": "sequential"\n'
        "    }\n"
        "  ]\n"
        "}\n"
        "```"
    )


# ---------------------------------------------------------------------------
# Content preprocessing helpers
# ---------------------------------------------------------------------------

def _preprocess_title(title: str) -> str:
    if not title or not title.strip():
        return "[未提供任务标题]"
    t = title.strip()
    if len(t) > _MAX_MISSION_TITLE_CHARS:
        t = t[:_MAX_MISSION_TITLE_CHARS] + "…（已截断）"
    return t


def _preprocess_mission_content(content: str) -> str:
    """Truncate mission content using a 60 / 40 head-tail strategy.

    Keeps the first 60 % (background / context) and last 40 % (goal / constraints)
    so the LLM has both the setup and the specific ask even for very long inputs.
    """
    if not content or not content.strip():
        return "[未提供任务描述]"

    content = content.strip()
    if len(content) <= _MAX_MISSION_CONTENT_CHARS:
        return content

    head_len = int(_MAX_MISSION_CONTENT_CHARS * 0.6)
    tail_len = _MAX_MISSION_CONTENT_CHARS - head_len
    omitted = len(content) - head_len - tail_len
    logger.debug(
        "task llm_prompt: mission_content truncated — kept %d head + %d tail, omitted %d chars",
        head_len, tail_len, omitted,
    )
    return (
        f"{content[:head_len]}\n\n"
        f"[…已省略中间约 {omitted} 字符…]\n\n"
        f"{content[-tail_len:]}"
    )
