import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import React from 'react';

import Q6Detail from "./q6/Q6Detail";
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
  actionable_space: ["CRITICAL_WRITE", "DEPLOY_TO_PROD"],
  authorization_boundaries: ["DEV_ONLY"],
  non_bypassable_constraints: ["MUST_HAVE_HUMAN_APPROVAL_FOR_PROD"],
  historical_strategy_patches: [
    "2025-01-01: Auto-deploy to prod failed catastrophically. Added strict requirement to never deploy without manual ticket linked."
  ],
};

const mockInference = {
  absolute_red_lines: ["NO_UNAUTHENTICATED_TRADES", "NO_DATA_LEAKAGE"],
  prohibited_strategies: ["grid_with_no_stop_loss"],
  performance_tradeoff_bans: ["Latency for safety"],
  contamination_risks: ["None detected"],
};

const mockQuestionItem = {
  question_id: "q6",
  title: "我即使能做也不该做什么",
  tool_id: "nine_questions.q6",
  summary: "禁区审计完成，红线清晰。",
  confidence: 0.98,
  trace_id: "trace-prod-q6-mno",
  timestamp: "2026-04-05T06:00:00Z",
  result: {},
  context_updates: {},
  cache_status: "已就绪",
  provider_name: "gpt-4-turbo",
  mounted_plugins: [{ plugin_id: "redline_gatekeeper", description: "Redline Gatekeeper", version: "3.0", status: "active", source_kind: "base" }],
  preprocessed_evidence: mockEvidence,
  inference_result: mockInference,
  llm_trace_payload: {
    provider_name: "gpt-4-turbo",
    model: "gpt-4-turbo",
    system_prompt: "You are a safety officer...",
    prompt: "Evaluating risks...",
    context_data: {},
    raw_response: {},
    token_usage: { input_tokens: 200, output_tokens: 100, total_tokens: 300 },
    elapsed_ms: 1800,
  },
};

describe("【Q6 禁区审计物理隔离与证据全景测试】", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("任务 1: 断言 Q6 详情页独立 API 绑定与物理路由隔离", async () => {
    vi.mocked(api.fetchNineQuestionDetail).mockResolvedValue(mockQuestionItem as any);

    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q6"]}>
        <Routes>
          <Route path="/console/nine-questions/q6" element={<Q6Detail />} />
        </Routes>
      </MemoryRouter>
    );

    // 强断言：必须调用 Q6 的独立 REST 端点
    await waitFor(() => {
      expect(api.fetchNineQuestionDetail).toHaveBeenCalledWith("q6");
    });

    expect(screen.getByTestId("q6-detail-root")).toBeInTheDocument();
    expect(screen.getByText(/Q6_What_Should_I_Not_Do 正式审计页/)).toBeInTheDocument();
  });

  it("任务 2: LLM 溯源与历史补丁 Accordion 默认闭合断言", async () => {
    vi.mocked(api.fetchNineQuestionDetail).mockResolvedValue(mockQuestionItem as any);

    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q6"]}>
        <Routes>
          <Route path="/console/nine-questions/q6" element={<Q6Detail />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByTestId("q6-trace-chip")).toHaveTextContent("trace: trace-prod-q6-mno");
    });

    // 强断言：历史补丁与 LLM 溯源面板默认闭合
    const patchAccordion = screen.getByTestId("q6-historical-patch-accordion");
    const traceAccordion = screen.getByTestId("llm-trace-prompt-accordion");

    expect(patchAccordion.querySelector(".MuiAccordionSummary-root")).toHaveAttribute("aria-expanded", "false");
    expect(traceAccordion.querySelector(".MuiAccordionSummary-root")).toHaveAttribute("aria-expanded", "false");
  });

  it("任务 3: Q6 异常降级人话提示强断言 (404 场景)", async () => {
    vi.mocked(api.fetchNineQuestionDetail).mockRejectedValue(new Error("尚无快照记录"));

    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q6"]}>
        <Routes>
          <Route path="/console/nine-questions/q6" element={<Q6Detail />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByTestId("q6-error-boundary")).toBeInTheDocument();
    });

    expect(screen.getByText("Q6 尚未产生推断结果")).toBeInTheDocument();
    expect(screen.getByText(/请在 Zentex Brain Runtime 中重新触发推演/)).toBeInTheDocument();
  });
});
