from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal


FieldType = Literal["text", "list_text", "structured", "number", "boolean"]


@dataclass(frozen=True)
class FieldContract:
    field_name: str
    intent: str
    required: bool
    max_chars: int | None = None
    max_items: int | None = None
    field_type: FieldType = "text"
    drift_smell: str | None = None


@dataclass(frozen=True)
class QuestionInputContract:
    source_question: str
    fields: tuple[str, ...]


@dataclass(frozen=True)
class QuestionContract:
    question_id: str
    purpose: str
    inputs: tuple[QuestionInputContract, ...]
    outputs: tuple[FieldContract, ...]
    max_total_prompt_chars: int
    anti_drift_directives: tuple[str, ...]
    prompt_builder_symbol: str
    prompt_file_path: str


def _field(
    name: str,
    intent: str,
    *,
    required: bool = True,
    max_chars: int | None = None,
    max_items: int | None = None,
    field_type: FieldType = "text",
    drift_smell: str | None = None,
) -> FieldContract:
    return FieldContract(
        field_name=name,
        intent=intent,
        required=required,
        max_chars=max_chars,
        max_items=max_items,
        field_type=field_type,
        drift_smell=drift_smell,
    )


def _input(source_question: str, *fields: str) -> QuestionInputContract:
    return QuestionInputContract(source_question=source_question, fields=tuple(fields))


_SRC_ROOT = Path(__file__).resolve().parents[2]


def _src_file(relative_path: str) -> str:
    return str(_SRC_ROOT / relative_path)


Q1_CONTRACT = QuestionContract(
    question_id="q1",
    purpose="识别当前环境状态与本轮用户意图，提供下游 Q 的事实锚点。",
    inputs=(),
    outputs=(
        _field("primary_domain", "当前 workspace 或用户输入所属的主环境域。", max_chars=120),
        _field("secondary_domains", "可能相关的次级环境域，最多 4 个。", required=False, max_items=4, max_chars=80, field_type="list_text"),
        _field("confidence", "环境识别置信度，范围 0..1。", max_chars=12, field_type="number"),
        _field("reasoning_summary", "基于本地证据的短摘要。", max_chars=300, drift_smell="哲学化分析或无证据推测"),
        _field("uncertainties", "仍不确定的事实或环境信号。", max_items=5, max_chars=160, field_type="list_text"),
        _field("suggested_first_step", "面向下游的下一步事实澄清建议。", max_chars=220),
    ),
    max_total_prompt_chars=2500,
    anti_drift_directives=(
        "只识别可观察环境事实，不做任务规划。",
        "不确定时必须输出 uncertainties，不得强行确定。",
        "不要输出环境哲学分析或自我评论。",
    ),
    prompt_builder_symbol="plugins.nine_questions.q1_where_am_i.llm_prompt.build_q1_llm_request",
    prompt_file_path=_src_file("plugins/nine_questions/q1_where_am_i/llm_prompt.py"),
)

Q2_CONTRACT = QuestionContract(
    question_id="q2",
    purpose="基于 Q1 环境和身份内核，确定本轮任务角色、使命边界和身份约束。",
    inputs=(_input("q1", "primary_domain", "secondary_domains", "uncertainties", "suggested_first_step"),),
    outputs=(
        _field("role_profile", "本轮身份角色结构。", field_type="structured"),
        _field("mission_boundary", "当前使命、优先职责和连续性边界。", field_type="structured", drift_smell="长篇身份叙事或人格化自述"),
        _field("identity_constraints", "本轮不可绕过的身份约束。", required=False, max_items=5, max_chars=180, field_type="list_text"),
    ),
    max_total_prompt_chars=2400,
    anti_drift_directives=(
        "只输出本轮角色和使命边界，不写人格化身份叙事。",
        "mission_boundary 必须能追溯到 Q1 环境信号。",
        "不得削弱 identity kernel 的不可绕过约束。",
    ),
    prompt_builder_symbol="plugins.nine_questions.q2_asset_inventory.llm_prompt.build_q2_llm_request",
    prompt_file_path=_src_file("plugins/nine_questions/q2_asset_inventory/llm_prompt.py"),
)

Q3_CONTRACT = QuestionContract(
    question_id="q3",
    purpose="盘点当前真实可用资产、工具、执行域、Agent，并为每类资产输出来源、置信度和有效期。",
    inputs=(_input("q1", "primary_domain", "reasoning_summary"), _input("q2", "role_profile", "mission_boundary")),
    outputs=(
        _field("asset_inventory", "严格 AssetInventory：workspace_files、permission_boundaries、long_term_memories、available_tools、connected_agents、reusable_strategy_patches、question_driver_refs。", field_type="structured", drift_smell="捏造资产、权限或 Agent"),
    ),
    max_total_prompt_chars=3200,
    anti_drift_directives=(
        "只盘点真实存在的资产和工具。",
        "禁止把不存在的能力写成可用资源。",
        "每类资产必须带 source、confidence、valid_until。",
        "禁止让 LLM 输出旧的 unified_asset_inventory/resource_evaluation 顶层合约。",
    ),
    prompt_builder_symbol="plugins.nine_questions.q3_role_inference.llm_prompt.build_q3_llm_request",
    prompt_file_path=_src_file("plugins/nine_questions/q3_role_inference/llm_prompt.py"),
)

Q4_CONTRACT = QuestionContract(
    question_id="q4",
    purpose="从 Q3 真实资产、Q2 角色和当前执行域推导可行动能力边界。",
    inputs=(_input("q2", "role_profile", "mission_boundary"), _input("q3", "unified_asset_inventory", "resource_evaluation")),
    outputs=(
        _field("capability_boundary_profile", "能力上限、可行动作空间和可执行策略。", field_type="structured", drift_smell="把不可执行概念写成行动能力"),
        _field("permission_profile", "执行域和权限轮廓。", required=False, field_type="structured"),
    ),
    max_total_prompt_chars=3000,
    anti_drift_directives=(
        "能力结论必须来自 Q3 资产和执行域。",
        "不得推导权限或红线结论，权限交给 Q5，红线交给 Q6。",
        "actionable_space 必须是当前真实可做动作。",
    ),
    prompt_builder_symbol="plugins.nine_questions.q4_what_can_i_do.internal.llm_prompt.build_q4_internal_llm_request",
    prompt_file_path=_src_file("plugins/nine_questions/q4_what_can_i_do/internal/llm_prompt.py"),
)

Q5_CONTRACT = QuestionContract(
    question_id="q5",
    purpose="从身份内核、Q4 能力和组织/租户/协作政策中推导正式授权边界。",
    inputs=(_input("q2", "identity_kernel", "role_profile"), _input("q4", "capability_boundary_profile", "permission_profile")),
    outputs=(
        _field("authorization_boundary", "严格根对象 AuthorizationBoundary：current_authorization_scope、communication_policy、organizational_boundary、allowed_operations、forbidden_operations。", field_type="structured", drift_smell="输出 Q4 未给出的新动作或绕过组织边界"),
    ),
    max_total_prompt_chars=3000,
    anti_drift_directives=(
        "Q5 allowed_operations 必须是 Q4 actionable_space 的子集。",
        "禁止发明 Q4 没有给出的动作。",
        "必须区分物理可做与正式授权允许。",
        "必须输出跨脑联系策略和组织/租户边界。",
    ),
    prompt_builder_symbol="plugins.nine_questions.q5_what_am_i_allowed_to_do.llm_prompt.build_q5_llm_request",
    prompt_file_path=_src_file("plugins/nine_questions/q5_what_am_i_allowed_to_do/llm_prompt.py"),
)

Q6_CONTRACT = QuestionContract(
    question_id="q6",
    purpose="评估 What if I do it：动作后果、代价、可逆性、缓解要求和停止条件。",
    inputs=(
        _input("q4", "capability_boundary_profile"),
        _input("q5", "authorization_boundary_profile", "forbidden_action_space"),
    ),
    outputs=(
        _field("ConsequenceAssessment", "评估动作、直接后果、传导后果、严重度和可逆性。", field_type="structured", drift_smell="只输出风险口号而没有具体后果"),
        _field("CostImpactProfile", "操作成本、安全合规影响、用户信任影响、缓解要求和停止条件。", field_type="structured", drift_smell="遗漏缓解要求或停止条件"),
    ),
    max_total_prompt_chars=3000,
    anti_drift_directives=(
        "Q6 不得重新拥有 Q5 的禁止动作裁剪职责。",
        "ConsequenceAssessment 必须明确 action_under_review。",
        "CostImpactProfile 必须包含 mitigation_requirements 和 stop_conditions。",
        "连续失败时必须提高 consequence_severity 并增强缓解/停止要求。",
    ),
    prompt_builder_symbol="plugins.nine_questions.q6_what_should_i_not_do.llm_prompt.build_q6_llm_request",
    prompt_file_path=_src_file("plugins/nine_questions/q6_what_should_i_not_do/llm_prompt.py"),
)

Q7_CONTRACT = QuestionContract(
    question_id="q7",
    purpose="在 Q8 行动目标生成前评估当前红线、拒绝记录、禁令来源和不可绕过约束。",
    inputs=(
        _input("q2", "identity_kernel_snapshot", "non_bypassable_constraints"),
        _input("q5", "authorization_boundary_profile", "forbidden_action_space"),
        _input("g12_g30", "safety_rejection_history"),
        _input("g38", "procedural_memory_constraints"),
    ),
    outputs=(
        _field("red_line_assessment", "RedLineAssessment：当前红线命中、拒绝记录、禁令来源、不可绕过约束和引用来源。", field_type="structured", drift_smell="简化字段或遗漏禁令来源"),
        _field("non_bypassable_constraints", "不可绕过底线列表。", max_items=16, max_chars=220, field_type="list_text"),
    ),
    max_total_prompt_chars=3200,
    anti_drift_directives=(
        "必须说明每个 RedLineAssessment 字段含义并输出所有字段。",
        "不得输出备选动作或主目标优先级。",
        "non_bypassable_constraints 不能被效率、探索或动态目标覆盖。",
    ),
    prompt_builder_symbol="plugins.nine_questions.q7_what_else_can_i_do.llm_prompt.build_q7_llm_request",
    prompt_file_path=_src_file("plugins/nine_questions/q7_what_else_can_i_do/llm_prompt.py"),
)

Q8_CONTRACT = QuestionContract(
    question_id="q8",
    purpose="综合 Q1-Q7 与任务状态，决定当前主目标和任务队列。",
    inputs=(
        _input("q1", "primary_domain", "suggested_first_step"),
        _input("q2", "role_profile", "mission_boundary", "identity_constraints"),
        _input("q3", "unified_asset_inventory", "resource_evaluation"),
        _input("q4", "capability_boundary_profile", "permission_profile"),
        _input("q5", "authorization_boundary_profile", "allowed_action_space", "forbidden_action_space"),
        _input("q6", "forbidden_zone_profile", "absolute_red_lines"),
        _input("q7", "red_line_assessment", "non_bypassable_constraints", "current_red_line_hits"),
    ),
    outputs=(
        _field("objective_profile", "当前使命、主次目标、完成/暂停/升级条件和优先级。", field_type="structured", drift_smell="输出空泛目标而非当前可执行任务"),
        _field("task_queue", "next/blocked/proactive 三类任务队列。", field_type="structured"),
    ),
    max_total_prompt_chars=4000,
    anti_drift_directives=(
        "只生成当前应做的任务，不生成姿态、评估 profile 或自我反思。",
        "所有任务必须服从 Q5 授权和 Q6 红线。",
        "任务必须有可验证结果或明确阻塞原因。",
    ),
    prompt_builder_symbol="plugins.nine_questions.q8_what_should_i_do_now.llm_prompt.build_q8_llm_request",
    prompt_file_path=_src_file("plugins/nine_questions/q8_what_should_i_do_now/llm_prompt.py"),
)

Q9_CONTRACT = QuestionContract(
    question_id="q9",
    purpose="基于 Q8 目标画像、Q4 已验证能力和 Q5/Q7 边界导出 ActionPlan。",
    inputs=(
        _input("q1", "primary_domain", "uncertainties"),
        _input("q2", "role_profile", "mission_boundary"),
        _input("q3", "resource_evaluation"),
        _input("q4", "capability_boundary_profile"),
        _input("q5", "authorization_boundary_profile"),
        _input("q6", "forbidden_zone_profile"),
        _input("q7", "red_line_assessment", "non_bypassable_constraints"),
        _input("q8", "objective_profile", "task_queue"),
    ),
    outputs=(
        _field("current_action_plan", "为了达成 Q8 目标需要执行的具体步骤序列。", field_type="list_text", drift_smell="退回 Q8 task_queue 或过程解说"),
        _field("method_selection", "说明为什么选择该方法或工具链。", field_type="text"),
        _field("required_resources", "执行计划必须依赖的已验证插件、Agent 或内部预算。", field_type="list_text"),
        _field("risk_assessment", "评估执行副作用、安全闸门或云审计拦截风险。", field_type="text"),
        _field("expected_outcome", "行动成功后的确切物理或认知结果。", field_type="text"),
        _field("alternative_candidates", "主计划失败或被安全拦截时的降级备选方案。", field_type="list_text"),
        _field("question_driver_refs", "计划引用的前置 Q1-Q8 依据映射。", field_type="list_text"),
    ),
    max_total_prompt_chars=4200,
    anti_drift_directives=(
        "Q9 只选择如何行动，不生成、修改、删除或重排任务队列。",
        "必须且只能输出 ActionPlan 七字段 JSON。",
        "所有动作必须限制在 Q4 verified_capabilities 范围内。",
        "不得输出 markdown、解释文字或 Q8 结构。",
    ),
    prompt_builder_symbol="plugins.nine_questions.q9_how_should_i_act.llm_prompt.build_q9_llm_request",
    prompt_file_path=_src_file("plugins/nine_questions/q9_how_should_i_act/llm_prompt.py"),
)


ALL_CONTRACTS: dict[str, QuestionContract] = {
    contract.question_id: contract
    for contract in (
        Q1_CONTRACT,
        Q2_CONTRACT,
        Q3_CONTRACT,
        Q4_CONTRACT,
        Q5_CONTRACT,
        Q6_CONTRACT,
        Q7_CONTRACT,
        Q8_CONTRACT,
        Q9_CONTRACT,
    )
}


def get_contract(question_id: str) -> QuestionContract:
    key = str(question_id or "").strip().lower()
    if key not in ALL_CONTRACTS:
        raise KeyError(f"No prompt contract registered for {question_id}")
    return ALL_CONTRACTS[key]


def validate_cross_q_consistency(contracts: dict[str, QuestionContract] | None = None) -> list[str]:
    registry = contracts or ALL_CONTRACTS
    errors: list[str] = []
    expected_questions = {f"q{index}" for index in range(1, 10)}
    missing = sorted(expected_questions - set(registry))
    if missing:
        errors.append(f"missing question contracts: {','.join(missing)}")
    for question_id, contract in sorted(registry.items()):
        if not contract.outputs:
            errors.append(f"{question_id} has no output contracts")
        output_names = [field.field_name for field in contract.outputs]
        if len(output_names) != len(set(output_names)):
            errors.append(f"{question_id} has duplicate output field contracts")
        if contract.max_total_prompt_chars <= 0:
            errors.append(f"{question_id} max_total_prompt_chars must be positive")
        if not contract.anti_drift_directives:
            errors.append(f"{question_id} has no anti_drift_directives")
        if not contract.prompt_builder_symbol:
            errors.append(f"{question_id} prompt_builder_symbol missing")
        if not contract.prompt_file_path:
            errors.append(f"{question_id} prompt_file_path missing")
        for dependency in contract.inputs:
            upstream = registry.get(dependency.source_question)
            if upstream is None:
                errors.append(f"{question_id} references missing upstream {dependency.source_question}")
                continue
            upstream_outputs = {field.field_name for field in upstream.outputs}
            for field_name in dependency.fields:
                if field_name not in upstream_outputs:
                    errors.append(
                        f"{question_id} references {dependency.source_question}.{field_name} "
                        "which is not in upstream outputs"
                    )
    return errors


def build_contract_summary() -> dict[str, object]:
    return {
        "contract_status": "passed" if not validate_cross_q_consistency() else "failed",
        "question_count": len(ALL_CONTRACTS),
        "questions": {
            question_id: {
                "purpose": contract.purpose,
                "input_sources": [
                    {
                        "source_question": dependency.source_question,
                        "fields": list(dependency.fields),
                    }
                    for dependency in contract.inputs
                ],
                "output_fields": [
                    {
                        "field_name": field.field_name,
                        "intent": field.intent,
                        "required": field.required,
                        "max_chars": field.max_chars,
                        "max_items": field.max_items,
                        "field_type": field.field_type,
                        "drift_smell": field.drift_smell,
                    }
                    for field in contract.outputs
                ],
                "max_total_prompt_chars": contract.max_total_prompt_chars,
                "anti_drift_directives": list(contract.anti_drift_directives),
                "prompt_builder_symbol": contract.prompt_builder_symbol,
                "prompt_file_path": contract.prompt_file_path,
            }
            for question_id, contract in sorted(ALL_CONTRACTS.items())
        },
        "consistency_errors": validate_cross_q_consistency(),
    }
