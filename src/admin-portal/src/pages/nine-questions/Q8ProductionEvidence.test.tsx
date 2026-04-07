import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import React from 'react';

import Q8Detail from "./q8/Q8Detail";
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
  aggregated_context: {
    absolute_red_line_count: 5,
    capability_ceiling_count: 12,
    q1_to_q7_snapshot: { summary: "All systems go within boundaries." },
  },
  runtime_state: {
    persistent_task_state: [
      { item_id: "T-01", title: "Wait for deployment auth", status: "blocked", blocker_reason: "Awaiting DBA signoff" }
    ],
    cognitive_agenda: [
      { item_id: "C-01", title: "Investigate latency", status: "overdue", delay_risk_score: 95, next_review_condition: "When CPU > 80%" }
    ],
  },
};

const mockInference = {
  task_queue: {
    next_self_tasks: [{ title: "Run diagnostic" }],
    blocked_self_tasks: [{ title: "Deploy to Prod", reason: "Missing approval" }],
    proactive_actions: [{ title: "Check logs" }],
  },
  objective_profile: {
    current_primary_objective: "ENSURE_STABILITY_AND_PERFORMANCE",
    current_phase_tasks: ["Analysis", "Verification", "Execution"],
  },
};

const mockQuestionItem = {
  question_id: "q8",
  title: "我现在应该做什么",
  tool_id: "nine_questions.q8",
  summary: "终局决策锁定，执行队列已排布。",
  confidence: 1.0,
  trace_id: "trace-prod-q8-stu",
  timestamp: "2026-04-05T08:00:00Z",
  result: {},
  context_updates: {},
  cache_status: "已就绪",
  provider_name: "anthropic-claude-3-sonnet",
  mounted_plugins: [{ plugin_id: "decision_arbitrator", description: "Decision Arbitrator", version: "4.0", status: "active", source_kind: "base" }],
  preprocessed_evidence: mockEvidence,
  inference_result: mockInference,
  llm_trace_payload: {
    provider_name: "anthropic-claude-3-sonnet",
    model: "claude-3-sonnet",
    system_prompt: "You are the primary decision engine...",
    prompt: "Calculating final objective...",
    context_data: {},
    raw_response: {},
    token_usage: { input_tokens: 500, output_tokens: 250, total_tokens: 750 },
    elapsed_ms: 3200,
  },
};

describe("【Q8 决策审计物理隔离与证据全景测试】", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("任务 1: 断言 Q8 详情页独立 API 绑定与物理路由隔离", async () => {
    vi.mocked(api.fetchNineQuestionDetail).mockResolvedValue(mockQuestionItem as any);

    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q8"]}>
        <Routes>
          <Route path="/console/nine-questions/q8" element={<Q8Detail />} />
        </Routes>
      </MemoryRouter>
    );

    // 强断言：必须调用 Q8 的独立 REST 端点
    await waitFor(() => {
      expect(api.fetchNineQuestionDetail).toHaveBeenCalledWith("q8");
    });

    expect(screen.getByTestId("q8-detail-root")).toBeInTheDocument();
    expect(screen.getByText(/Q8_What_Should_I_Do_Now 正式审计页/)).toBeInTheDocument();
  });

  it("任务 2: 前置约束聚合面板与 LLM 溯源默认闭合断言", async () => {
    vi.mocked(api.fetchNineQuestionDetail).mockResolvedValue(mockQuestionItem as any);

    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q8"]}>
        <Routes>
          <Route path="/console/nine-questions/q8" element={<Q8Detail />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByTestId("q8-trace-chip")).toHaveTextContent("trace: trace-prod-q8-stu");
    });

    // 强断言：Q1-Q7 聚合上下文与 LLM 溯源面板默认闭合
    const contextAccordionHeader = screen.getByTestId("q8-context-accordion-summary");
    const traceAccordion = screen.getByTestId("llm-trace-prompt-accordion");

    expect(contextAccordionHeader).toHaveAttribute("aria-expanded", "false");
    expect(traceAccordion.querySelector(".MuiAccordionSummary-root")).toHaveAttribute("aria-expanded", "false");
  });

  it("任务 3: Q8 异常降级人话提示强断言 (404 场景)", async () => {
    vi.mocked(api.fetchNineQuestionDetail).mockRejectedValue(new Error("尚无快照记录"));

    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q8"]}>
        <Routes>
          <Route path="/console/nine-questions/q8" element={<Q8Detail />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByTestId("q8-error-boundary")).toBeInTheDocument();
    });

    expect(screen.getByText("Q8 尚未产生终局决策")).toBeInTheDocument();
    expect(screen.getByText(/主决策引擎快照为空/)).toBeInTheDocument();
  });
});
