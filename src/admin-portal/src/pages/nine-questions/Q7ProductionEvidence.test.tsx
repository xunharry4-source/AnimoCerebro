import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import React from 'react';

import Q7Detail from "./q7/Q7Detail";
import * as api from "./nineQuestionsApi";

// Mock API 模块
vi.mock("./nineQuestionsApi", async () => {
  const actual = await vi.importActual("./nineQuestionsApi");
  return {
    ...actual,
    fetchNineQuestionDetail: vi.fn(),
  };
});

const mockEvidence = {
  resource_bottlenecks: ["CPU_LIMIT", "API_QUOTA_EXCEEDED"],
  capability_limits: ["CANNOT_SEND_SMS"],
  permission_boundaries: ["READ_ONLY"],
  absolute_red_lines: ["NO_UNAUTHORIZED_EXTERNAL_CALLS"],
  historical_failure_patches: [
    "2024-05: Fallback to local mode when external API is down."
  ],
};

const mockInference = {
  degradation_strategies: ["Switch to cached data", "Disable real-time updates"],
  exploratory_actions: ["Ping fallback server"],
  fallback_plans: ["Manual review queue"],
  collaboration_switches: [
    { target_agent: "safety_bot", reason: "Escalate for manual override" }
  ],
};

const mockQuestionItem = {
  question_id: "q7",
  title: "我还可以做什么",
  tool_id: "nine_questions.q7",
  summary: "降级预案已建立，安全冗余 100%。",
  confidence: 0.95,
  trace_id: "trace-prod-q7-pqr",
  timestamp: "2026-04-05T07:00:00Z",
  result: {},
  context_updates: {},
  cache_status: "已就绪",
  provider_name: "anthropic-claude-3-opus",
  mounted_plugins: [{ plugin_id: "fallback_orchestrator", description: "Fallback Orchestrator", version: "2.1", status: "active", source_kind: "base" }],
  preprocessed_evidence: mockEvidence,
  inference_result: mockInference,
  llm_trace_payload: {
    provider_name: "anthropic-claude-3-opus",
    model: "claude-3-opus",
    system_prompt: "You are a fallback planner...",
    prompt: "Calculating fallback paths...",
    context_data: {},
    raw_response: {},
    token_usage: { input_tokens: 300, output_tokens: 150, total_tokens: 450 },
    elapsed_ms: 2500,
  },
};

describe("【Q7 降级审计物理隔离与证据全景测试】", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("任务 1: 断言 Q7 详情页独立 API 绑定与物理路由隔离", async () => {
    vi.mocked(api.fetchNineQuestionDetail).mockResolvedValue(mockQuestionItem as any);

    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q7"]}>
        <Routes>
          <Route path="/console/nine-questions/q7" element={<Q7Detail />} />
        </Routes>
      </MemoryRouter>
    );

    // 强断言：必须调用 Q7 的独立 REST 端点
    await waitFor(() => {
      expect(api.fetchNineQuestionDetail).toHaveBeenCalledWith("q7");
    });

    expect(screen.getByTestId("q7-detail-root")).toBeInTheDocument();
    expect(screen.getByText(/Q7_What_Else_Can_I_Do 正式审计页/)).toBeInTheDocument();
  });

  it("任务 2: LLM 溯源与历史补丁 Accordion 默认闭合断言", async () => {
    vi.mocked(api.fetchNineQuestionDetail).mockResolvedValue(mockQuestionItem as any);

    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q7"]}>
        <Routes>
          <Route path="/console/nine-questions/q7" element={<Q7Detail />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByTestId("q7-trace-chip")).toHaveTextContent("trace: trace-prod-q7-pqr");
    });

    // 强断言：历史补丁与 LLM 溯源面板默认闭合
    const patchAccordion = screen.getByTestId("q7-historical-patch-accordion");
    const traceAccordion = screen.getByTestId("llm-trace-prompt-accordion");

    expect(patchAccordion.querySelector(".MuiAccordionSummary-root")).toHaveAttribute("aria-expanded", "false");
    expect(traceAccordion.querySelector(".MuiAccordionSummary-root")).toHaveAttribute("aria-expanded", "false");
  });

  it("任务 3: Q7 异常降级人话提示强断言 (503 场景)", async () => {
    vi.mocked(api.fetchNineQuestionDetail).mockRejectedValue(new Error("状态机未挂载"));

    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q7"]}>
        <Routes>
          <Route path="/console/nine-questions/q7" element={<Q7Detail />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByTestId("q7-error-boundary")).toBeInTheDocument();
    });

    expect(screen.getByText("后端推演引擎未就绪")).toBeInTheDocument();
    expect(screen.getByText(/NineQuestionState 未挂载/)).toBeInTheDocument();
  });
});
