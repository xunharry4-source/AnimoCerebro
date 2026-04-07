import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import React from 'react';

import Q5Detail from "./q5/Q5Detail";
import * as api from "./nineQuestionsApi";

// Mock API 模块，确保测试独立性
vi.mock("./nineQuestionsApi", async () => {
  const actual = await vi.importActual("./nineQuestionsApi");
  return {
    ...actual,
    fetchNineQuestionDetail: vi.fn(),
  };
});

const mockEvidence = {
  permission_boundary: {
    explicit_allow: ["READ_MARKET_DATA", "WRITE_SIGNAL_FILE"],
    explicit_deny: ["MODIFY_ALGO_CODE", "DELETE_TRADING_LOGS"],
    boundary_violations: [],
  },
  compliance_check: {
    status: "compliant",
    g31a_status: "passed",
    audit_trail_id: "audit-v123",
  },
};

const mockInference = {
  execution_tier: "standard",
  interaction_scope: "workspace_local",
  requires_human_confirmation: false,
  requires_cloud_audit: true,
  explicitly_forbidden_actions: ["DELETE_SYSTEM_LOGS", "MODIFY_ROOT_CONFIG"],
  compliance_risks: ["Limited audit trail on legacy tools"],
  allowed_delegation_targets: ["risk_service", "notification_bot"],
};

const mockQuestionItem = {
  question_id: "q5",
  title: "我能被允许做什么",
  tool_id: "nine_questions.q5",
  summary: "权限审计通过，合规性 100%。",
  confidence: 1.0,
  trace_id: "trace-prod-q5-jkl",
  timestamp: "2026-04-05T05:00:00Z",
  result: {},
  context_updates: {},
  cache_status: "已就绪",
  provider_name: "claude-3-sonnet",
  mounted_plugins: [{ plugin_id: "permission_guard", description: "Permission Guard", version: "1.5", status: "active", source_kind: "base" }],
  preprocessed_evidence: mockEvidence,
  inference_result: mockInference,
  llm_trace_payload: {
    provider_name: "claude-3-sonnet",
    model: "claude-3-sonnet",
    system_prompt: "You are a permission auditor...",
    prompt: "Checking access rights...",
    context_data: {},
    raw_response: {},
    token_usage: { input_tokens: 120, output_tokens: 60, total_tokens: 180 },
    elapsed_ms: 1100,
  },
};

describe("【Q5 权限审计物理隔离与证据全景测试】", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("任务 1: 断言 Q5 详情页独立 API 绑定与路由隔离", async () => {
    vi.mocked(api.fetchNineQuestionDetail).mockResolvedValue(mockQuestionItem as any);

    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q5"]}>
        <Routes>
          <Route path="/console/nine-questions/q5" element={<Q5Detail />} />
        </Routes>
      </MemoryRouter>
    );

    // 强断言：必须调用 Q5 的独立 REST 端点
    await waitFor(() => {
      expect(api.fetchNineQuestionDetail).toHaveBeenCalledWith("q5");
    });

    expect(screen.getByTestId("q5-detail-root")).toBeInTheDocument();
    expect(screen.getByText(/Q5_What_Am_I_Allowed_To_Do 正式审计页/)).toBeInTheDocument();
    expect(screen.getByTestId("q5-sandbox-nav-button")).toBeInTheDocument();
    
    // 验证警戒提示存在
    expect(screen.getByText(/Q5 审计已划定认知动作的终极禁区/)).toBeInTheDocument();
  });

  it("任务 2: LLM 溯源折叠面板默认闭合与物理快照断言", async () => {
    vi.mocked(api.fetchNineQuestionDetail).mockResolvedValue(mockQuestionItem as any);

    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q5"]}>
        <Routes>
          <Route path="/console/nine-questions/q5" element={<Q5Detail />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByTestId("q5-trace-chip")).toHaveTextContent("trace: trace-prod-q5-jkl");
    });

    // 强断言：大模型交互面板必须默认闭合
    const promptAccordion = screen.getByTestId("llm-trace-prompt-accordion");
    expect(promptAccordion.querySelector(".MuiAccordionSummary-root")).toHaveAttribute("aria-expanded", "false");
  });

  it("任务 3: Q5 异常降级人话提示强断言 (503 场景)", async () => {
    vi.mocked(api.fetchNineQuestionDetail).mockRejectedValue(new Error("状态机未挂载到运行时"));

    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q5"]}>
        <Routes>
          <Route path="/console/nine-questions/q5" element={<Q5Detail />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByTestId("q5-error-boundary")).toBeInTheDocument();
    });

    // 强断言：展示后端引擎未就绪建议
    expect(screen.getByText("后端推演引擎未就绪")).toBeInTheDocument();
    expect(screen.getByText(/NineQuestionState 未挂载/)).toBeInTheDocument();
  });
});
