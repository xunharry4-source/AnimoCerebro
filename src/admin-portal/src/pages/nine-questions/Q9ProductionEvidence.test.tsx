import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import React from 'react';

import Q9Detail from "./q9/Q9Detail";
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
  cognitive_snapshot: {
    uncertainty_count: 0,
    absolute_red_line_count: 3,
    q1_to_q8_snapshot: { Q1: "nominal", Q6: "redline_detected" },
  },
  self_model: {
    cognitive_load: "low",
    stability_level: "high",
    confidence_drift: 0.02,
    recent_weaknesses: [
      { pattern_type: "latency_sensitivity", severity: "medium", frequency: 2 }
    ],
  },
  reasoning_budget: {
    compute_remaining_ratio: 0.95,
    token_remaining_ratio: 0.8,
    time_remaining_ratio: 0.9,
    budget_pressure: "low",
  },
};

const mockInference = {
  evaluation_style: "balanced",
  risk_tolerance: "low_risk",
  action_rhythm: "metered",
  confirmation_strategy: "Human in the loop for high risk",
  evolution_direction: "Optimize for data throughput",
};

const mockQuestionItem = {
  question_id: "q9",
  title: "我现在的行动姿态是什么",
  tool_id: "nine_questions.q9",
  summary: "行动姿态定调完成，系统自愈能力良好。",
  confidence: 0.99,
  trace_id: "trace-prod-q9-vwx",
  timestamp: "2026-04-05T09:00:00Z",
  result: {},
  context_updates: {},
  cache_status: "已就绪",
  provider_name: "openai-gpt-4o",
  mounted_plugins: [{ plugin_id: "posture_analyzer", description: "Posture Analyzer", version: "1.2", status: "active", source_kind: "base" }],
  preprocessed_evidence: mockEvidence,
  inference_result: mockInference,
  llm_trace_payload: {
    provider_name: "openai-gpt-4o",
    model: "gpt-4o",
    system_prompt: "You are a cognitive posture analyst...",
    prompt: "Evaluating action posture...",
    context_data: {},
    raw_response: {},
    token_usage: { input_tokens: 400, output_tokens: 200, total_tokens: 600 },
    elapsed_ms: 2100,
  },
};

describe("【Q9 姿态审计物理隔离与证据全景测试】", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("任务 1: 断言 Q9 详情页独立 API 绑定与物理路由隔离", async () => {
    vi.mocked(api.fetchNineQuestionDetail).mockResolvedValue(mockQuestionItem as any);

    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q9"]}>
        <Routes>
          <Route path="/console/nine-questions/q9" element={<Q9Detail />} />
        </Routes>
      </MemoryRouter>
    );

    // 强断言：必须调用 Q9 的独立 REST 端点
    await waitFor(() => {
      expect(api.fetchNineQuestionDetail).toHaveBeenCalledWith("q9");
    });

    expect(screen.getByTestId("q9-detail-root")).toBeInTheDocument();
    expect(screen.getByText(/Q9_How_Should_I_Act 正式审计页/)).toBeInTheDocument();
  });

  it("任务 2: 认知快照聚合面板与 LLM 溯源默认闭合断言", async () => {
    vi.mocked(api.fetchNineQuestionDetail).mockResolvedValue(mockQuestionItem as any);

    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q9"]}>
        <Routes>
          <Route path="/console/nine-questions/q9" element={<Q9Detail />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByTestId("q9-trace-chip")).toHaveTextContent("trace: trace-prod-q9-vwx");
    });

    // 强断言：认知快照与 LLM 溯源面板默认闭合
    const snapshotAccordion = screen.getByTestId("q9-snapshot-accordion");
    const traceAccordion = screen.getByTestId("llm-trace-prompt-accordion");

    expect(snapshotAccordion.querySelector(".MuiAccordionSummary-root")).toHaveAttribute("aria-expanded", "false");
    expect(traceAccordion.querySelector(".MuiAccordionSummary-root")).toHaveAttribute("aria-expanded", "false");
  });

  it("任务 3: Q9 异常降级人话提示强断言 (503 场景)", async () => {
    vi.mocked(api.fetchNineQuestionDetail).mockRejectedValue(new Error("状态机未挂载"));

    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q9"]}>
        <Routes>
          <Route path="/console/nine-questions/q9" element={<Q9Detail />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByTestId("q9-error-boundary")).toBeInTheDocument();
    });

    expect(screen.getByText("后端推演引擎未就绪")).toBeInTheDocument();
    expect(screen.getByText(/NineQuestionState 未挂载/)).toBeInTheDocument();
  });
});
