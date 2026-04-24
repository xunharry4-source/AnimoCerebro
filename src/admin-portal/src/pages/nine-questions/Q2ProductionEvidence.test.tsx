import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import React from 'react';

import Q2Detail from "./q2/Q2Detail";
import Q2Test from "./q2/Q2Test";
import * as api from "./nineQuestionsApi";

// Mock API 模块，确保测试独立性
vi.mock("./nineQuestionsApi", async () => {
  const actual = await vi.importActual("./nineQuestionsApi");
  return {
    ...actual,
    fetchNineQuestionDetail: vi.fn(),
    fetchNineQuestionEvidence: vi.fn(),
    fetchNineQuestionInference: vi.fn(),
    fetchNineQuestionModules: vi.fn(),
    fetchNineQuestionRaw: vi.fn(),
    fetchNineQuestionSummary: vi.fn(),
    fetchNineQuestionTracePayload: vi.fn(),
    runNineQuestionSandboxTest: vi.fn(),
  };
});

const mockEvidence = {
  q1_summary: {
    primary_domain: "trading_system",
    secondary_domains: ["order_management"],
    uncertainties: ["low_liquidity_regime"],
    risk_summary: "High volatility detected.",
  },
  identity_kernel: {
    meta_motivation: "Maximize risk-adjusted returns.",
    values_prohibition: "No market manipulation.",
    non_bypassable_constraints: ["Daily loss limit: 2%"],
  },
  manual_intervention: {
    latest_manual_role_modification: "Switch to conservative hunter",
    applied_at: "2026-04-05T00:00:00Z",
  },
};

const mockInference = {
  role_profile: {
    identity_role: "Autonomous Portfolio Manager",
    active_role: "Liquidity Provider",
    task_role: "Order Executor",
  },
  mission_boundary: {
    current_mission: "Maintain neutral delta exposition.",
    priority_duties: ["Rebalance every 15m", "Monitor news feeds"],
    continuity_boundaries: ["Min cash reserve: 10%"],
  },
};

const mockQuestionItem = {
  question_id: "q2",
  title: "我是谁",
  tool_id: "nine_questions.q2",
  summary: "身份内核审计通过，目标使命明确。",
  confidence: 1.0,
  trace_id: "trace-prod-q2-abc",
  timestamp: "2026-04-05T02:00:00Z",
  result: {},
  context_updates: {},
  cache_status: "已就绪",
  provider_name: "claude-3-opus",
  mounted_plugins: [{ plugin_id: "identity_core_v1", description: "Identity Auditor", version: "1.0", status: "active", source_kind: "base" }],
  preprocessed_evidence: mockEvidence,
  inference_result: mockInference,
  llm_trace_payload: {
    provider_name: "claude-3-opus",
    model: "claude-3-opus",
    system_prompt: "You are an identity auditor...",
    prompt: "Auditing current state...",
    context_data: {},
    raw_response: {},
    token_usage: { input_tokens: 100, output_tokens: 50, total_tokens: 150 },
    elapsed_ms: 1200,
  },
};

describe("【Q2 身份审计物理隔离与证据全景测试】", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.fetchNineQuestionSummary).mockResolvedValue({ status: "completed", question_id: "q2" } as any);
    vi.mocked(api.fetchNineQuestionEvidence).mockResolvedValue(mockEvidence as any);
    vi.mocked(api.fetchNineQuestionInference).mockResolvedValue(mockInference as any);
    vi.mocked(api.fetchNineQuestionTracePayload).mockResolvedValue(mockQuestionItem.llm_trace_payload as any);
    vi.mocked(api.fetchNineQuestionRaw).mockResolvedValue(mockQuestionItem as any);
    vi.mocked(api.fetchNineQuestionModules).mockResolvedValue({
      status: { status: "completed" },
      module_runs: [
        { module_id: "q2_identity_kernel", status: "completed" },
        { module_id: "q2_mission_boundary", status: "completed" },
      ],
      plugin_runs: [],
      upstream_dependencies: [{ dependency_id: "q1", required: true, status: "completed" }],
    } as any);
  });

  it("任务 1: 断言 Q2 详情页独立 API 绑定与物理路由隔离", async () => {
    vi.mocked(api.fetchNineQuestionDetail).mockRejectedValue(new Error("legacy detail endpoint should not be used"));

    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q2"]}>
        <Routes>
          <Route path="/console/nine-questions/q2" element={<Q2Detail />} />
        </Routes>
      </MemoryRouter>
    );

    // 强断言：必须调用 Q2 的独立 REST 端点
    await waitFor(() => {
      expect(api.fetchNineQuestionSummary).toHaveBeenCalledWith("q2");
    });
    expect(api.fetchNineQuestionEvidence).toHaveBeenCalledWith("q2");
    expect(api.fetchNineQuestionInference).toHaveBeenCalledWith("q2");
    expect(api.fetchNineQuestionTracePayload).toHaveBeenCalledWith("q2");
    expect(api.fetchNineQuestionRaw).toHaveBeenCalledWith("q2");
    expect(api.fetchNineQuestionModules).toHaveBeenCalledWith("q2");
    expect(api.fetchNineQuestionDetail).not.toHaveBeenCalled();

    expect(screen.getByTestId("q2-detail-root")).toBeInTheDocument();
    expect(screen.getByText(/Q2_Who_Am_I 正式审计页/)).toBeInTheDocument();
    expect(screen.getByTestId("q2-sandbox-nav-button")).toBeInTheDocument();
  });

  it("任务 2: 证据区高密度渲染与折叠面板默认锁定断言", async () => {
    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q2"]}>
        <Routes>
          <Route path="/console/nine-questions/q2" element={<Q2Detail />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByTestId("q2-active-role-chip")).toHaveTextContent("活跃角色: Liquidity Provider");
    });

    // 强断言：LLM 溯源折叠面板必须默认闭合
    const promptAccordion = screen.getByTestId("llm-trace-prompt-accordion");
    const contextAccordion = screen.getByTestId("llm-trace-context-accordion");
    const rawResponseAccordion = screen.getByTestId("llm-trace-raw-response-accordion");

    expect(promptAccordion.querySelector(".MuiAccordionSummary-root")).toHaveAttribute("aria-expanded", "false");
    expect(contextAccordion.querySelector(".MuiAccordionSummary-root")).toHaveAttribute("aria-expanded", "false");
    expect(rawResponseAccordion.querySelector(".MuiAccordionSummary-root")).toHaveAttribute("aria-expanded", "false");

    // 验证状态芯片
    expect(screen.getByTestId("q2-cache-status-chip")).toHaveTextContent("completed");
    expect(screen.getByTestId("q2-trace-chip")).toHaveTextContent("trace: trace-prod-q2-abc");
  });

  it("任务 3: Q2 异常降级人话提示强断言 (404 场景)", async () => {
    // 模拟 Q2 尚未生成记录的 404 场景
    const missingSnapshotError = new Error("Q2 尚无快照记录");
    vi.mocked(api.fetchNineQuestionSummary).mockRejectedValue(missingSnapshotError);
    vi.mocked(api.fetchNineQuestionRaw).mockRejectedValue(missingSnapshotError);
    vi.mocked(api.fetchNineQuestionModules).mockRejectedValue(missingSnapshotError);

    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q2"]}>
        <Routes>
          <Route path="/console/nine-questions/q2" element={<Q2Detail />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByTestId("q2-error-boundary")).toBeInTheDocument();
    });

    // 强断言：提供明确的下一步建议 acción
    expect(screen.getByText("Q2 尚未产生推断结果")).toBeInTheDocument();
    expect(screen.getByText(/触发一次全量九问推断/)).toBeInTheDocument();
  });
});
