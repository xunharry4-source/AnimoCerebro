import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import NineQuestionDetailPage from "./NineQuestionDetailPage";
import NineQuestionSandboxPage from "./NineQuestionSandboxPage";

const mockFetch = vi.fn();
global.fetch = mockFetch;

const q8Evidence = {
  aggregated_context: {
    q1_to_q7_snapshot: {
      q1: { primary_domain: "billing_workspace", uncertainties: ["OCR drift"] },
      q5: { explicitly_forbidden_actions: ["delete_invoice"] },
      q6: { absolute_red_lines: ["NO_FAKE_STATE", "NO_HIDDEN_FAILURE"] },
    },
    absolute_red_line_count: 3,
    capability_ceiling_count: 2,
  },
  runtime_state: {
    persistent_task_state: [
      { item_id: "todo-1", title: "Inspect invoice batch", status: "todo", priority: 80 },
      { item_id: "blocked-1", title: "Push production patch", status: "blocked", blocker_reason: "waiting for human approval" },
    ],
    cognitive_agenda: [
      { item_id: "agenda-1", title: "Review OCR drift", status: "overdue", priority: 100, next_review_condition: "needs_manual_validation", delay_risk_score: 0.92 },
    ],
  },
};

const q8Inference = {
  objective_profile: {
    current_primary_objective: "Stabilize OCR evidence pipeline",
    current_phase_tasks: ["sample invoices", "verify OCR drift"],
    priority_order: ["sample invoices", "verify OCR drift"],
  },
  task_queue: {
    next_self_tasks: [{ id: "next-1", title: "sample invoices" }],
    blocked_self_tasks: [{ id: "blocked-1", title: "push production patch", reason: "waiting for human approval" }],
    proactive_actions: [{ id: "pro-1", title: "notify operator" }],
  },
};

const q9Evidence = {
  cognitive_snapshot: {
    q1_to_q8_snapshot: {
      q1: { uncertainties: ["gateway jitter"] },
      q5: { explicitly_forbidden_actions: ["bypass_confirm"] },
      q6: { absolute_red_lines: ["NO_FAKE_TEST_RESULT"] },
      q8: { current_primary_objective: "stabilize pipeline" },
    },
    uncertainty_count: 1,
    absolute_red_line_count: 2,
  },
  self_model: {
    cognitive_load: "high",
    stability_level: "unstable",
    confidence_drift: 0.61,
    recent_weaknesses: [{ pattern_id: "weak-1", pattern_type: "overconfidence", frequency: 2, severity: "high" }],
  },
  reasoning_budget: {
    compute_remaining_ratio: 0.25,
    token_remaining_ratio: 0.18,
    time_remaining_ratio: 0.42,
    budget_pressure: "critical",
  },
};

const q9Inference = {
  evaluation_style: "evidence_first",
  risk_tolerance: "zero_tolerance",
  action_rhythm: "step-by-step with checkpoint",
  confirmation_strategy: "wait for human confirmation before risky step",
  evolution_direction: "reduce OCR drift before execution",
};

describe("Q8/Q9 structured evidence rendering", () => {
  beforeEach(() => {
    mockFetch.mockReset();
  });

  it("renders Q8 production detail with aggregated accordion, DataGrid queue and llm trace", async () => {
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          session_id: "q8-session",
          last_turn_id: "turn-1",
          snapshot_version: 1,
          revision: 1,
          refreshed_at: "2026-04-05T10:00:00Z",
          last_refresh_reason: "unit_test",
          question_driver_refs: ["seed:q8"],
          questions: [
            {
              question_id: "q8",
              title: "我现在应该做什么",
              tool_id: "nine_questions.q8",
              summary: "当前主目标是验证发票 OCR 偏差并暂停危险写操作。",
              confidence: 0.94,
              result: {},
              context_updates: {},
              trace_id: "trace-q8-1",
              timestamp: "2026-04-05T10:00:00Z",
              cache_status: "已就绪",
              provider_name: "gpt-4-o",
              preprocessed_evidence: q8Evidence,
              inference_result: q8Inference,
            },
          ],
        }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          trace_id: "trace-q8-1",
          prompt: "PROMPT_Q8",
          context: {},
          result: q8Inference,
          invocation_phase: "nine_question_q8_decision",
          provider_name: "gpt-4-o",
          preprocessed_evidence: q8Evidence,
          inference_result: q8Inference,
          llm_trace_payload: {
            provider_name: "gpt-4-o",
            model: "gpt-4-o",
            system_prompt: "SYSTEM_Q8",
            prompt: "PROMPT_Q8",
            context_data: { q1_q7_snapshot: { q1: { primary_domain: "billing_workspace" } } },
            raw_response: { id: "raw-q8" },
            token_usage: { input_tokens: 188, output_tokens: 77, total_tokens: 265 },
            elapsed_ms: 640,
          },
        }),
      } as Response);

    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q8"]}>
        <Routes>
          <Route path="/console/nine-questions/:q_id" element={<NineQuestionDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText("Q8_What_Should_I_Do_Now")).toBeInTheDocument();
    });

    expect(screen.getByText(/【Q1-Q7 前置约束聚合区】/)).toBeInTheDocument();
    expect(screen.getByText("【运行时状态与内部待办区 (State Machine & Agenda)】")).toBeInTheDocument();
    expect(screen.getByText("Inspect invoice batch")).toBeInTheDocument();
    expect(screen.getByText("Review OCR drift")).toBeInTheDocument();
    expect(screen.getByText("【终极目标与执行队列区 (LLM Objective & Task Queue)】")).toBeInTheDocument();
    expect(screen.getByText("Stabilize OCR evidence pipeline")).toBeInTheDocument();
    expect(screen.getAllByText("waiting for human approval").length).toBeGreaterThan(0);
    expect(screen.getByText("大模型交互溯源区")).toBeInTheDocument();
    const llmPromptAccordion = screen.getByTestId("llm-trace-prompt-accordion");
    const llmPromptButton = within(llmPromptAccordion).getByRole("button", { name: "输入 Prompt" });
    expect(llmPromptButton).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(llmPromptButton);
    expect(await screen.findByText(/PROMPT_Q8/)).toBeInTheDocument();
  });

  it("renders Q8 sandbox result with the same four sections", async () => {
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          session_id: "q8-session",
          last_turn_id: "turn-1",
          snapshot_version: 1,
          revision: 1,
          refreshed_at: "2026-04-05T10:00:00Z",
          last_refresh_reason: "unit_test",
          question_driver_refs: ["seed:q8"],
          questions: [{ question_id: "q8", title: "我现在应该做什么", tool_id: "nine_questions.q8", summary: "", confidence: 0.94, result: {}, context_updates: {}, trace_id: "trace-q8-1", timestamp: "", cache_status: "已就绪", provider_name: "gpt-4-o" }],
        }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          question_id: "q8",
          title: "我现在应该做什么",
          tool_id: "nine_questions.q8",
          summary: "Sandbox Q8",
          confidence: 0.94,
          trace_id: "sandbox-q8",
          elapsed_ms: 500,
          provider_name: "gpt-4-o",
          prompt: "PROMPT_Q8_SANDBOX",
          context: {},
          result: q8Inference,
          context_updates: {},
          preprocessed_evidence: q8Evidence,
          inference_result: q8Inference,
          llm_trace_payload: {
            provider_name: "gpt-4-o",
            model: "gpt-4-o",
            system_prompt: "SYSTEM_Q8",
            prompt: "PROMPT_Q8_SANDBOX",
            context_data: { q1_q7_snapshot: { q1: { primary_domain: "billing_workspace" } } },
            raw_response: { id: "raw-q8-sandbox" },
            token_usage: { input_tokens: 100, output_tokens: 30, total_tokens: 130 },
            elapsed_ms: 500,
          },
        }),
      } as Response);

    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q8/sandbox"]}>
        <Routes>
          <Route path="/console/nine-questions/:q_id/sandbox" element={<NineQuestionSandboxPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText(/Q8_What_Should_I_Do_Now 沙箱测试/)).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText("执行测试"));
    await waitFor(() => {
      expect(screen.getByText("Stabilize OCR evidence pipeline")).toBeInTheDocument();
    });
    expect(screen.getByText("大模型交互溯源区")).toBeInTheDocument();
  });

  it("renders Q9 production detail with budget pressure and zero_tolerance posture", async () => {
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          session_id: "q9-session",
          last_turn_id: "turn-1",
          snapshot_version: 1,
          revision: 1,
          refreshed_at: "2026-04-05T10:00:00Z",
          last_refresh_reason: "unit_test",
          question_driver_refs: ["seed:q9"],
          questions: [
            {
              question_id: "q9",
              title: "我应该如何行动",
              tool_id: "nine_questions.q9",
              summary: "当前行动姿态应保持零容忍、证据优先与逐步确认。",
              confidence: 0.97,
              result: {},
              context_updates: {},
              trace_id: "trace-q9-1",
              timestamp: "2026-04-05T10:00:00Z",
              cache_status: "已就绪",
              provider_name: "gpt-4-o",
              preprocessed_evidence: q9Evidence,
              inference_result: q9Inference,
            },
          ],
        }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          trace_id: "trace-q9-1",
          prompt: "PROMPT_Q9",
          context: {},
          result: q9Inference,
          invocation_phase: "nine_question_q9_posture",
          provider_name: "gpt-4-o",
          preprocessed_evidence: q9Evidence,
          inference_result: q9Inference,
          llm_trace_payload: {
            provider_name: "gpt-4-o",
            model: "gpt-4-o",
            system_prompt: "SYSTEM_Q9",
            prompt: "PROMPT_Q9",
            context_data: { q1_q8_snapshot: { q1: { uncertainties: ["gateway jitter"] } } },
            raw_response: { id: "raw-q9" },
            token_usage: { input_tokens: 145, output_tokens: 48, total_tokens: 193 },
            elapsed_ms: 510,
          },
        }),
      } as Response);

    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q9"]}>
        <Routes>
          <Route path="/console/nine-questions/:q_id" element={<NineQuestionDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText("Q9_How_Should_I_Act")).toBeInTheDocument();
    });

    expect(screen.getByText("【Q1-Q8 认知快照聚合区】")).toBeInTheDocument();
    expect(screen.getByText("【自我模型与预算压力区】")).toBeInTheDocument();
    expect(screen.getAllByText("high").length).toBeGreaterThan(0);
    expect(screen.getByText(/overconfidence/i)).toBeInTheDocument();
    expect(screen.getByText("【终极行动姿态定调区】")).toBeInTheDocument();
    expect(screen.getByTestId("q9-risk-tolerance-chip")).toHaveTextContent("zero_tolerance");
    expect(screen.getByTestId("q9-confirmation-strategy-alert")).toHaveTextContent("wait for human confirmation before risky step");
    fireEvent.click(screen.getByText("输入 Prompt"));
    expect(await screen.findByText(/PROMPT_Q9/)).toBeInTheDocument();
  });

  it("renders Q9 sandbox result with llm trace", async () => {
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          session_id: "q9-session",
          last_turn_id: "turn-1",
          snapshot_version: 1,
          revision: 1,
          refreshed_at: "2026-04-05T10:00:00Z",
          last_refresh_reason: "unit_test",
          question_driver_refs: ["seed:q9"],
          questions: [{ question_id: "q9", title: "我应该如何行动", tool_id: "nine_questions.q9", summary: "", confidence: 0.97, result: {}, context_updates: {}, trace_id: "trace-q9-1", timestamp: "", cache_status: "已就绪", provider_name: "gpt-4-o" }],
        }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          question_id: "q9",
          title: "我应该如何行动",
          tool_id: "nine_questions.q9",
          summary: "Sandbox Q9",
          confidence: 0.97,
          trace_id: "sandbox-q9",
          elapsed_ms: 410,
          provider_name: "gpt-4-o",
          prompt: "PROMPT_Q9_SANDBOX",
          context: {},
          result: q9Inference,
          context_updates: {},
          preprocessed_evidence: q9Evidence,
          inference_result: q9Inference,
          llm_trace_payload: {
            provider_name: "gpt-4-o",
            model: "gpt-4-o",
            system_prompt: "SYSTEM_Q9",
            prompt: "PROMPT_Q9_SANDBOX",
            context_data: { q1_q8_snapshot: { q1: { uncertainties: ["gateway jitter"] } } },
            raw_response: { id: "raw-q9-sandbox" },
            token_usage: { input_tokens: 80, output_tokens: 22, total_tokens: 102 },
            elapsed_ms: 410,
          },
        }),
      } as Response);

    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q9/sandbox"]}>
        <Routes>
          <Route path="/console/nine-questions/:q_id/sandbox" element={<NineQuestionSandboxPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText(/Q9_How_Should_I_Act 沙箱测试/)).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText("执行测试"));
    await waitFor(() => {
      expect(screen.getAllByText("zero_tolerance").length).toBeGreaterThan(0);
    });
    expect(screen.getByText("大模型交互溯源区")).toBeInTheDocument();
  });
});
