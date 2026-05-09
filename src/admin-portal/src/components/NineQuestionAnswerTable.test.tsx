import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import NineQuestionAnswerTable from "./NineQuestionAnswerTable";

const cases = [
  {
    questionId: "q1",
    inference: {
      primary_domain: "software_project",
      secondary_domains: ["backend", "frontend"],
      confidence: 0.87,
      reasoning_summary: "当前环境是 Zentex 控制台代码仓库。",
      uncertainties: ["部署环境变量未完全确认"],
      suggested_first_step: "先运行真实接口回归测试。",
    },
    expected: ["当前环境主领域", "software_project", "LLM 分析结论", "Zentex 控制台代码仓库"],
  },
  {
    questionId: "q2",
    inference: {
      asset_inventory: {
        inventory_summary: "当前资产特征指向控制台研发和代码审计领域",
        cognitive_and_functional_tools: [{ asset_name: "已注册真实工具链" }],
        connected_agents: [],
      },
      sufficiency_assessment: {
        resource_status: "sufficient",
        missing_critical_assets: [],
        bottleneck_node: "none",
      },
    },
    expected: ["资产领域侧写", "代码审计领域", "资源状态", "sufficient", "可用工具", "已注册真实工具链"],
  },
  {
    questionId: "q3",
    inference: {
      role_profile: {
        identity_role: "真实性审计者",
        active_role: "前端控制台维护者",
        inferred_reference_role: "后端链路审计者",
        role_alignment_gap: "前端角色与后端审计需求存在职责偏差。",
        task_role: "修复九问展示缺陷",
      },
      mission_boundary: {
        current_mission: "补齐页面回答结果",
        priority_duties: ["禁止假测试"],
        continuity_boundaries: ["不能隐藏错误"],
      },
    },
    expected: ["身份角色", "真实性审计者", "系统推断参考角色", "后端链路审计者", "当前使命", "补齐页面回答结果"],
  },
  {
    questionId: "q4",
    inference: {
      capability_upper_limits: ["只能修改当前工作区"],
      actionable_space: ["补齐表格展示"],
      executable_strategies: ["组件复用"],
    },
    expected: ["能力上限", "只能修改当前工作区", "可行动空间", "补齐表格展示"],
  },
  {
    questionId: "q5",
    inference: {
      execution_tier: "workspace_write",
      interaction_scope: "admin_portal",
      requires_human_confirmation: false,
      requires_cloud_audit: false,
      explicitly_forbidden_actions: ["写入测试数据到运行时代码"],
      compliance_risks: ["虚假通过"],
      allowed_delegation_targets: ["本地测试"],
    },
    expected: ["执行层级", "workspace_write", "明确禁止操作", "写入测试数据到运行时代码"],
  },
  {
    questionId: "q6",
    inference: {
      absolute_red_lines: ["禁止吞异常"],
      performance_tradeoff_bans: ["不能用空态掩盖失败"],
      prohibited_strategies: ["隐藏错误信息"],
      contamination_risks: ["旧快照污染真实 trace"],
    },
    expected: ["绝对红线", "禁止吞异常", "污染风险", "旧快照污染真实 trace"],
  },
  {
    questionId: "q7",
    inference: {
      current_red_line_hits: ["外部写入会绕过确认"],
      rejected_operation_records: ["G12 拒绝强制写入"],
      ban_source_explanations: ["来自 IdentityKernel 与 G12"],
      non_bypassable_constraints: ["禁止绕过云审计"],
      question_driver_refs: ["Q5", "IdentityKernel"],
    },
    expected: ["当前红线命中", "外部写入会绕过确认", "不可绕过约束", "禁止绕过云审计"],
  },
  {
    questionId: "q9",
    inference: {
      evaluation_style: "strict",
      risk_tolerance: "low",
      action_rhythm: "stepwise",
      confirmation_strategy: "真实接口复查",
      evolution_direction: "减少假测试盲区",
    },
    expected: ["评估风格", "strict", "确认策略", "真实接口复查"],
  },
];

describe("NineQuestionAnswerTable", () => {
  it.each(cases)("renders concrete business answer rows for $questionId", ({ questionId, inference, expected }) => {
    render(<NineQuestionAnswerTable questionId={questionId} inference={inference} />);

    const table = screen.getByTestId(`${questionId}-answer-table`);
    for (const text of expected) {
      expect(table).toHaveTextContent(text);
    }
  });

  it("renders a clear empty state instead of pretending a missing answer is normal", () => {
    render(<NineQuestionAnswerTable questionId="q1" inference={null} />);

    expect(screen.getByTestId("q1-answer-table-empty")).toHaveTextContent("当前没有可展示的问题回答结果");
    expect(screen.queryByTestId("q1-answer-table")).not.toBeInTheDocument();
  });
});
