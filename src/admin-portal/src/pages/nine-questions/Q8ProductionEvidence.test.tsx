import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import React from "react";

import Q8Detail from "./q8/Q8Detail";
import * as api from "./nineQuestionsApi";

vi.mock("./nineQuestionsApi", async () => {
  const actual = await vi.importActual("./nineQuestionsApi");
  return {
    ...actual,
    fetchNineQuestionSummary: vi.fn(),
    fetchNineQuestionEvidence: vi.fn(),
    fetchNineQuestionInference: vi.fn(),
    fetchNineQuestionTracePayload: vi.fn(),
    fetchNineQuestionRaw: vi.fn(),
    fetchNineQuestionModules: vi.fn(),
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
      { item_id: "T-01", title: "Wait for deployment auth", status: "blocked", blocker_reason: "Awaiting DBA signoff" },
    ],
    cognitive_agenda: [
      { item_id: "C-01", title: "Investigate latency", status: "overdue", delay_risk_score: 95, next_review_condition: "When CPU > 80%" },
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

describe("【Q8 决策审计物理隔离与证据全景测试】", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      value: {
        getItem: vi.fn(() => null),
        setItem: vi.fn(),
        removeItem: vi.fn(),
      },
    });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false }));
  });

  it("任务 1: 断言 Q8 详情页绑定独立分区接口与物理路由隔离", async () => {
    vi.mocked(api.fetchNineQuestionSummary).mockResolvedValue({ status: "completed", question_id: "q8" } as any);
    vi.mocked(api.fetchNineQuestionEvidence).mockResolvedValue(mockEvidence as any);
    vi.mocked(api.fetchNineQuestionInference).mockResolvedValue(mockInference as any);
    vi.mocked(api.fetchNineQuestionTracePayload).mockResolvedValue({
      provider_name: "anthropic-claude-3-sonnet",
      elapsed_ms: 3200,
    } as any);
    vi.mocked(api.fetchNineQuestionRaw).mockResolvedValue({
      trace_id: "trace-prod-q8-stu",
      tool_id: "nine_questions.q8",
      context_updates: {},
      llm_trace_payload: {
        provider_name: "anthropic-claude-3-sonnet",
        elapsed_ms: 3200,
      },
    } as any);
    vi.mocked(api.fetchNineQuestionModules).mockResolvedValue({ status: { status: "completed" }, modules: {} } as any);

    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q8"]}>
        <Routes>
          <Route path="/console/nine-questions/q8" element={<Q8Detail />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(api.fetchNineQuestionSummary).toHaveBeenCalledWith("q8");
      expect(api.fetchNineQuestionEvidence).toHaveBeenCalledWith("q8");
      expect(api.fetchNineQuestionInference).toHaveBeenCalledWith("q8");
      expect(api.fetchNineQuestionTracePayload).toHaveBeenCalledWith("q8");
      expect(api.fetchNineQuestionRaw).toHaveBeenCalledWith("q8");
      expect(api.fetchNineQuestionModules).toHaveBeenCalledWith("q8");
    });

    expect(screen.getByTestId("q8-detail-root")).toBeInTheDocument();
    expect(screen.getByText(/Q8_What_Should_I_Do_Now 正式审计页/)).toBeInTheDocument();
  });

  it("任务 2: 前置约束聚合面板与 LLM 溯源默认闭合断言", async () => {
    vi.mocked(api.fetchNineQuestionSummary).mockResolvedValue({ status: "completed", question_id: "q8" } as any);
    vi.mocked(api.fetchNineQuestionEvidence).mockResolvedValue(mockEvidence as any);
    vi.mocked(api.fetchNineQuestionInference).mockResolvedValue(mockInference as any);
    vi.mocked(api.fetchNineQuestionTracePayload).mockResolvedValue({
      provider_name: "anthropic-claude-3-sonnet",
      elapsed_ms: 3200,
    } as any);
    vi.mocked(api.fetchNineQuestionRaw).mockResolvedValue({
      trace_id: "trace-prod-q8-stu",
      tool_id: "nine_questions.q8",
      context_updates: {},
      llm_trace_payload: {
        provider_name: "anthropic-claude-3-sonnet",
        elapsed_ms: 3200,
      },
    } as any);
    vi.mocked(api.fetchNineQuestionModules).mockResolvedValue({ status: { status: "completed" }, modules: {} } as any);

    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q8"]}>
        <Routes>
          <Route path="/console/nine-questions/q8" element={<Q8Detail />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("q8-trace-chip")).toHaveTextContent("trace: trace-prod-q8-stu");
    });

    expect(screen.getByTestId("q8-context-accordion-summary")).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByTestId("llm-trace-prompt-accordion").querySelector(".MuiAccordionSummary-root")).toHaveAttribute(
      "aria-expanded",
      "false",
    );
  });

  it("任务 3: Q8 异常降级人话提示强断言 (404 场景)", async () => {
    vi.mocked(api.fetchNineQuestionSummary).mockRejectedValue(new Error("尚无快照记录"));
    vi.mocked(api.fetchNineQuestionEvidence).mockRejectedValue(new Error("尚无快照记录"));
    vi.mocked(api.fetchNineQuestionInference).mockRejectedValue(new Error("尚无快照记录"));
    vi.mocked(api.fetchNineQuestionTracePayload).mockRejectedValue(new Error("尚无快照记录"));
    vi.mocked(api.fetchNineQuestionRaw).mockRejectedValue(new Error("尚无快照记录"));
    vi.mocked(api.fetchNineQuestionModules).mockRejectedValue(new Error("尚无快照记录"));

    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q8"]}>
        <Routes>
          <Route path="/console/nine-questions/q8" element={<Q8Detail />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("q8-error-boundary")).toBeInTheDocument();
    });

    expect(screen.getByText("Q8 尚未产生终局决策")).toBeInTheDocument();
    expect(screen.getByText(/主决策引擎快照为空/)).toBeInTheDocument();
  });
});
