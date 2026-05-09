from __future__ import annotations
"""
Reflection LLM Prompt Builder — zentex.reflection.llm_prompt

RESPONSIBILITY:
  Owns ALL prompt construction and input content preprocessing for the
  reflection module's LLM calls.  No other file in zentex.reflection may
  build or inline a prompt string that is sent to an LLM.

CONTRACT:
  - Prompt content is split into typed segment fields (ReflectionPromptSegments).
    Each segment is built independently, validated, then assembled in order.
  - Content preprocessing (truncation, field extraction, noise removal) happens
    in dedicated _preprocess_*() helpers — never inside the caller.
  - If an input field is empty or None it is replaced with an explicit
    "[未提供]" marker so the LLM receives a complete, unambiguous structure.

SEGMENT STRUCTURE (in assembly order):
  1. role          — who the LLM is and what task it is performing
  2. subject       — the reflection subject / event being analysed
  3. context       — preprocessed evidence / context block (JSON)
  4. dimensions    — the analysis dimensions the LLM must cover
  5. output_rules  — quality and format constraints for the answer
  6. output_schema — the exact JSON schema expected
  7. guidance      — type-specific professional analysis guidance (optional)

DOES NOT:
  - Call the LLM directly.
  - Own any service state or lifecycle.
  - Import from zentex.llm (no circular dependency risk).
"""


import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from zentex.common.prompt_template_files import render_prompt_template

logger = logging.getLogger(__name__)
_TEMPLATE_DIR = Path(__file__).resolve().with_name("prompt_templates")


def _render_template(name: str, values: dict[str, str]) -> str:
    return render_prompt_template(_TEMPLATE_DIR, name, values, error_prefix="reflection")


# ---------------------------------------------------------------------------
# Content preprocessing limits
# ---------------------------------------------------------------------------

_MAX_CONTEXT_JSON_CHARS = 4_000   # Max chars for the serialised context block
_MAX_FIELD_CHARS = 800            # Max chars for any single context field value
_MAX_SUBJECT_CHARS = 300          # Max chars for the subject / title
_MAX_GUIDANCE_CHARS = 1_200       # Max chars for the type-specific guidance block

_SECTION_SEP = "\n\n"             # Separator between assembled sections


# ---------------------------------------------------------------------------
# Segment dataclass
# ---------------------------------------------------------------------------

@dataclass
class ReflectionPromptSegments:
    """All named segments that make up a reflection prompt.

    Each field is a clean, ready-to-render string.  None or empty strings are
    skipped during assembly — no blank sections appear in the final prompt.
    """

    # 1. Who the LLM is and what it must do
    role: str = ""

    # 2. The concrete reflection subject (event / decision / action being analysed)
    subject: str = ""

    # 3. Preprocessed evidence / context block (JSON or key-value text)
    context: str = ""

    # 4. The analysis dimensions the LLM must address
    dimensions: str = ""

    # 5. Quality and format constraints for the LLM's answer
    output_rules: str = ""

    # 6. The exact JSON schema expected in the response
    output_schema: str = ""

    # 7. Type-specific professional guidance (optional — appended last if present)
    guidance: str = ""

    def assemble(self) -> str:
        """Join non-empty segments in order and return the complete prompt string."""
        parts: List[str] = []
        for seg in (
            self.role,
            self.subject,
            self.context,
            self.dimensions,
            self.output_rules,
            self.output_schema,
            self.guidance,
        ):
            if seg and seg.strip():
                parts.append(seg.strip())
        return _SECTION_SEP.join(parts)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_reflection_prompt(
    subject: str,
    reflection_type_value: str,
    reflection_type_name: str,
    context: Dict[str, Any],
    type_specific_guidance: str = "",
) -> str:
    """Public API: Build a complete reflection prompt string."""
    segs = ReflectionPromptSegments(
        role=_build_role_segment(reflection_type_name),
        subject=_build_subject_segment(subject),
        context=_build_context_segment(context),
        dimensions=_build_dimensions_segment(),
        output_rules=_build_output_rules_segment(),
        output_schema=_build_output_schema_segment(),
        guidance=_build_guidance_segment(type_specific_guidance),
    )
    return segs.assemble()


def build_quality_audit_prompt(
    subject: str,
    reflection_content: Dict[str, Any],
    context: Dict[str, Any],
) -> str:
    """Return a prompt for an LLM-based quality audit of a reflection.
    
    Args:
        subject: The reflection subject.
        reflection_content: The dictionary containing insights, lessons, etc.
        context: The original context used for generation.
        
    Returns:
        Complete audit prompt string.
    """
    return _render_template(
        "quality_audit.md",
        {
            "SUBJECT": subject,
            "REFLECTION_CONTENT_JSON": json.dumps(reflection_content, ensure_ascii=False, indent=2),
            "CONTEXT_JSON": json.dumps(_preprocess_context(context), ensure_ascii=False, indent=2),
        },
    )


def build_maintenance_synthesis_prompt(
    *,
    top_tags: List[str],
    titles: List[str],
    layer_distribution: Dict[str, Any],
    unverified_count: int,
    tier_pressure: Dict[str, Any] | None = None,
) -> str:
    """Return a prompt for semantic synthesis of memory-maintenance insights.

    Used by ``LLMReflectionGenerator.synthesize_maintenance_insights()``
    to produce actionable, LLM-derived insights from memory-layer statistics
    — replacing the raw tag-counter fallback in
    ``ReflectionService.trigger_memory_aware_maintenance()``.

    Output schema (strict JSON):
    {
      "summary": "<one-sentence synthesis of memory state>",
      "insights": ["...", ...],
      "lessons": ["...", ...],
      "improvements": ["...", ...]
    }
    """
    tag_block = ", ".join(top_tags[:10]) if top_tags else "（无标签数据）"
    title_block = "; ".join(titles[:5]) if titles else "（无标题数据）"
    layer_block = ", ".join(f"{k}:{v}" for k, v in layer_distribution.items()) if layer_distribution else "（无分层数据）"
    unverified_line = f"{unverified_count} 条记忆尚未验证。" if unverified_count else "所有近期记忆均已验证。"
    pressure_block = (
        ", ".join(f"{k}:{float(v):.2f}" for k, v in tier_pressure.items())
        if tier_pressure
        else "（无压力数据）"
    )

    return _render_template(
        "maintenance_synthesis.md",
        {
            "TAG_BLOCK": tag_block,
            "TITLE_BLOCK": title_block,
            "LAYER_BLOCK": layer_block,
            "UNVERIFIED_LINE": unverified_line,
            "PRESSURE_BLOCK": pressure_block,
        },
    )


def build_type_specific_guidance(
    reflection_type_value: str,
    context: Dict[str, Any],
) -> str:
    """Return type-specific Markdown guidance for the given reflection type.

    Args:
        reflection_type_value: Machine value of ReflectionType.
        context:               Raw or preprocessed context dict.

    Returns:
        Markdown guidance string, or empty string for unrecognised types.
    """
    if reflection_type_value == "decision_reflection":
        return _guidance_decision(context)
    if reflection_type_value == "error_reflection":
        return _guidance_error(context)
    if reflection_type_value == "success_reflection":
        return _guidance_success(context)
    if reflection_type_value == "action_reflection":
        return _guidance_action(context)
    return _guidance_generic()


# ---------------------------------------------------------------------------
# Segment builders — one function per segment field
# ---------------------------------------------------------------------------

def _build_role_segment(reflection_type_name: str) -> str:
    """Segment 1 — Role declaration and top-level task instruction."""
    return (
        f"你是一个专业的反思分析师，擅长深度思考和系统性分析。\n\n"
        f"请对以下【{reflection_type_name}】进行深度反思分析。"
    )


def _build_subject_segment(subject: str) -> str:
    """Segment 2 — The reflection subject / event being analysed."""
    clean = _preprocess_subject(subject)
    return f"## 反思主题\n\n{clean}"


def _build_context_segment(context: Dict[str, Any]) -> str:
    """Segment 3 — Preprocessed context / evidence block."""
    clean_ctx = _preprocess_context(context)
    ctx_text = _serialize_context(clean_ctx)
    return f"## 上下文信息\n\n{ctx_text}"


def _build_dimensions_segment() -> str:
    """Segment 4 — Fixed analysis dimensions the LLM must address."""
    return (
        "## 分析维度（必须全部覆盖）\n\n"
        "1. **核心洞察 (insights)** — 发现的关键洞见和深层理解（至少 2-3 条）\n"
        "2. **经验教训 (lessons)** — 可复用的经验和教训（至少 1-2 条）\n"
        "3. **潜在风险 (risks)** — 可能存在的风险和隐患（无风险时返回空数组）\n"
        "4. **改进建议 (improvements)** — 具体可行的改进方案（至少 1-2 条）\n"
        "5. **置信度 (confidence)** — 本次分析的信心程度（0–1 浮点数）\n"
        "6. **影响力评分 (impact_score)** — 本次反思的重要性（0–1 浮点数）\n"
        "7. **可操作性 (actionability)** — 建议的可执行程度（0–1 浮点数）"
    )


def _build_output_rules_segment() -> str:
    """Segment 5 — Quality and format rules for the LLM's answer."""
    return (
        "## 输出质量要求\n\n"
        "- 洞察必须深入，不得停留在表面现象或重复上下文已有描述\n"
        "- 每条洞察/教训/建议必须结合上下文中的具体数据或事实，不得空泛\n"
        "- 改进建议必须具体、可立即执行，避免【加强管理】等无操作路径的表述\n"
        "- 保持客观和专业，用中文回答\n"
        "- 不得在 JSON 之外输出任何解释文字"
    )


def _build_output_schema_segment() -> str:
    """Segment 6 — The exact JSON schema the LLM must return."""
    return (
        "## 返回格式（严格 JSON）\n\n"
        "```json\n"
        "{\n"
        '  "summary": "反思摘要（一句话，不超过100字）",\n'
        '  "insights": ["洞察1（不超过150字）", "洞察2", "..."],\n'
        '  "lessons": ["教训1（不超过150字）", "..."],\n'
        '  "risks": ["风险1（不超过150字）", "..."],\n'
        '  "improvements": ["建议1（不超过200字）", "..."],\n'
        '  "confidence": 0.0,\n'
        '  "impact_score": 0.0,\n'
        '  "actionability": 0.0\n'
        "}\n"
        "```"
    )


def _build_guidance_segment(guidance: str) -> str:
    """Segment 7 — Optional type-specific professional guidance."""
    if not guidance or not guidance.strip():
        return ""
    clean = guidance.strip()
    if len(clean) > _MAX_GUIDANCE_CHARS:
        clean = clean[:_MAX_GUIDANCE_CHARS] + "\n\n// [专业指导过长，已截断]"
    return f"## 专业分析指导\n\n{clean}"


# ---------------------------------------------------------------------------
# Content preprocessing helpers
# ---------------------------------------------------------------------------

def _preprocess_subject(subject: str) -> str:
    """Truncate and sanitise the reflection subject."""
    if not subject or not subject.strip():
        return "[未提供反思主题]"
    s = subject.strip()
    if len(s) > _MAX_SUBJECT_CHARS:
        s = s[:_MAX_SUBJECT_CHARS] + "…（已截断）"
    return s


def _preprocess_context(context: Dict[str, Any]) -> Dict[str, Any]:
    """Clean and truncate a context dict before serialisation.

    Rules:
    - None values → "[未提供]"
    - Strings exceeding _MAX_FIELD_CHARS → truncated with note
    - Nested dicts/lists processed recursively (max depth 3)
    - Keys prefixed with "_" (internal details) are dropped
    """
    if not isinstance(context, dict):
        return {"raw": _truncate_value(str(context))}

    return {
        key: _truncate_value(value)
        for key, value in context.items()
        if not str(key).startswith("_")
    }


def _truncate_value(value: Any, depth: int = 0) -> Any:
    """Recursively truncate a value to prevent oversized context injection."""
    if value is None:
        return "[未提供]"
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        if len(value) > _MAX_FIELD_CHARS:
            return value[:_MAX_FIELD_CHARS] + f"…（已截断，原长 {len(value)} 字符）"
        return value
    if isinstance(value, dict):
        if depth >= 3:
            return f"[嵌套对象，已省略，共 {len(value)} 个字段]"
        return {
            k: _truncate_value(v, depth + 1)
            for k, v in value.items()
            if not str(k).startswith("_")
        }
    if isinstance(value, (list, tuple)):
        if depth >= 3:
            return f"[列表，已省略，共 {len(value)} 项]"
        truncated = [_truncate_value(item, depth + 1) for item in value[:20]]
        if len(value) > 20:
            truncated.append(f"…（还有 {len(value) - 20} 项已省略）")
        return truncated
    # Fallback for datetime, UUID, etc.
    return str(value)


def _serialize_context(context: Dict[str, Any]) -> str:
    """Serialise preprocessed context to JSON, capped at _MAX_CONTEXT_JSON_CHARS."""
    try:
        serialised = json.dumps(context, ensure_ascii=False, indent=2, default=str)
    except Exception as exc:
        logger.warning("reflection llm_prompt: context serialisation failed: %s", exc)
        serialised = str(context)

    if len(serialised) <= _MAX_CONTEXT_JSON_CHARS:
        return serialised

    # Try compact form first
    try:
        compact = json.dumps(context, ensure_ascii=False, separators=(",", ":"), default=str)
    except Exception:
        compact = serialised

    if len(compact) <= _MAX_CONTEXT_JSON_CHARS:
        return compact

    return serialised[:_MAX_CONTEXT_JSON_CHARS] + "\n\n// [上下文过长，已截断，后续内容已省略]"


# ---------------------------------------------------------------------------
# Type-specific guidance builders
# ---------------------------------------------------------------------------

def _guidance_decision(context: Dict[str, Any]) -> str:
    decision = context.get("decision") or {}
    alternatives = context.get("alternatives") or []

    lines = [
        "### 决策反思的专业分析要点",
        "",
        "**1. 决策质量评估**",
        "   - 决策依据是否充分、可验证？",
        "   - 是否系统性地考察了备选方案？",
        "   - 风险评估是否覆盖高影响、低概率场景？",
        "",
        "**2. 决策过程分析**",
        "   - 是否存在确认偏误或可用性偏误？",
        "   - 时间压力或信息不完整对决策质量的影响？",
        "   - 决策权归属与责任边界是否清晰？",
        "",
        "**3. 结果对比**",
        "   - 实际结果与预期的偏差及根本原因？",
        "   - 未选方案在事后评估中的可能结果？",
        "",
        "**4. 长期影响**",
        "   - 该决策是否收窄了未来的决策空间？",
        "   - 是否存在不可逆或高撤销成本的副作用？",
    ]

    if alternatives:
        lines.append(
            f"\n> **注意**：本次决策共考察了 {len(alternatives)} 个备选方案，"
            "请评估数量是否充分、筛选标准是否合理。"
        )
    if isinstance(decision, dict) and decision.get("risk_level"):
        lines.append(
            f"\n> **注意**：决策风险等级为 **{decision['risk_level']}**，"
            "请重点分析风险控制措施的充分性。"
        )

    return "\n".join(lines)


def _guidance_error(context: Dict[str, Any]) -> str:
    error_data = context.get("error") or {}

    lines = [
        "### 错误反思的专业分析要点",
        "",
        "**1. 根本原因分析（5-Why）**",
        "   - 直接触发原因是什么？",
        "   - 每一层背后的深层原因是什么？",
        "   - 是否存在可预防的系统性缺陷？",
        "",
        "**2. 影响评估**",
        "   - 对用户/业务/数据的实际影响范围？",
        "   - 是否产生了隐性的连锁失效？",
        "   - 恢复成本（时间、资源、信誉）？",
        "",
        "**3. 预防机制**",
        "   - 哪些监控或断路器本可提前预警？",
        "   - 是否需要补充防御性设计（幂等、回滚、限流）？",
        "   - 如何将此错误纳入测试/验收体系？",
        "",
        "**4. 知识沉淀**",
        "   - 如何形成可检索的最佳实践？",
        "   - 是否适合在团队或跨模块层面推广？",
    ]

    if isinstance(error_data, dict) and error_data.get("severity"):
        lines.append(
            f"\n> **注意**：错误严重程度为 **{error_data['severity']}**，"
            "请相应调整根因分析的深度与预防措施的优先级。"
        )

    return "\n".join(lines)


def _guidance_success(context: Dict[str, Any]) -> str:
    lines = [
        "### 成功反思的专业分析要点",
        "",
        "**1. 成功因素识别**",
        "   - 哪些因素是决定性的，哪些只是锦上添花？",
        "   - 运气成分与能力成分如何区分？",
        "   - 关键决策节点在哪里？",
        "",
        "**2. 可复制性分析**",
        "   - 成功经验在其他场景下的适用前提条件？",
        "   - 哪些依赖条件难以复现？",
        "   - 如何降低复制的门槛？",
        "",
        "**3. 优化空间**",
        "   - 即使成功，是否还有显著的效率或质量提升空间？",
        "   - 是否存在被忽视的更优路径？",
        "",
        "**4. 标准化与推广**",
        "   - 如何将成功经验抽象为可操作的 SOP？",
        "   - 是否具备向相邻场景推广的价值？",
    ]
    return "\n".join(lines)


def _guidance_action(context: Dict[str, Any]) -> str:
    execution = context.get("execution") or {}

    lines = [
        "### 行动反思的专业分析要点",
        "",
        "**1. 执行质量**",
        "   - 与计划的偏差点及成因？",
        "   - 资源（时间、计算、人力）利用是否合理？",
        "   - 执行过程中的关键判断节点？",
        "",
        "**2. 效率评估**",
        "   - 哪些步骤可以并行或省略？",
        "   - 自动化或工具化的机会？",
        "   - 信息传递效率是否是瓶颈？",
        "",
        "**3. 协作效果**",
        "   - 责任分工是否清晰、无盲区？",
        "   - 沟通节点是否足够及时和精准？",
        "",
        "**4. 改进路径**",
        "   - 下次执行的具体改进方案（可操作，非泛泛而谈）？",
        "   - 需要什么工具或流程变更支撑？",
    ]

    if isinstance(execution, dict) and execution.get("duration"):
        lines.append(
            f"\n> **注意**：执行耗时 **{execution['duration']} 分钟**，"
            "请具体评估每个阶段的时间分配是否合理。"
        )

    return "\n".join(lines)


def _guidance_generic() -> str:
    lines = [
        "### 通用分析要点",
        "",
        "**1. 全面性** — 是否覆盖了所有有实质影响的方面？",
        "**2. 深度** — 分析是否触及本质，而非停留在现象描述？",
        "**3. 实用性** — 结论和建议是否有直接的行动价值？",
        "**4. 前瞻性** — 是否考虑了中长期影响和二阶效应？",
    ]
    return "\n".join(lines)
