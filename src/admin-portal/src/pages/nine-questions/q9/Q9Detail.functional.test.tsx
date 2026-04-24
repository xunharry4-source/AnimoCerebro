import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import Q9Detail from "./Q9Detail";
import * as api from "../nineQuestionsApi";

vi.mock("../nineQuestionsApi", async () => {
  const actual = await vi.importActual("../nineQuestionsApi");
  return {
    ...actual,
    fetchNineQuestionDetail: vi.fn(),
    fetchNineQuestionModules: vi.fn(),
  };
});

describe("Q9Detail functional tests", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders Q9 recovery plan and workflow button from structured execution diagnosis", async () => {
    vi.mocked(api.fetchNineQuestionDetail).mockResolvedValue({
      question_id: "q9",
      title: "我应该如何行动",
      tool_id: "nine_questions.q9",
      cache_status: "degraded",
      provider_name: "provider-tools-default",
      trace_id: "trace-q9-recovery",
      context_updates: {
        q9_execution_diagnosis: {
          authenticity_status: "degraded",
          diagnosis_message: "Q9 posture output relies on incomplete self-model evidence.",
          recovery_plan: {
            retriable: true,
            rollback_available: false,
            partial_retry_available: true,
            partial_replace_available: false,
            actions: [
              {
                action_id: "q9-rerun-question",
                label: "重跑 Q9",
                kind: "retry",
                executable: true,
                scope: "question",
                target: "q9",
              },
            ],
          },
        },
      },
      preprocessed_evidence: null,
      inference_result: null,
      llm_trace_payload: {},
      result: {},
    } as any);

    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q9"]}>
        <Routes>
          <Route path="/console/nine-questions/q9" element={<Q9Detail />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("q9-recovery-plan")).toBeInTheDocument();
    });

    expect(screen.getByTestId("q9-recovery-action-q9-rerun-question")).toHaveTextContent(
      "重跑 Q9 | retry | question | executable | q9",
    );
    expect(screen.getByTestId("q9-workflow-nav-button")).toHaveAttribute("href", "/console/nine-questions/q9/workflow");
  });

  it("renders degraded Q9 evidence without dropping self-model and budget data", async () => {
    vi.mocked(api.fetchNineQuestionDetail).mockResolvedValue({
      question_id: "q9",
      title: "我应该如何行动",
      tool_id: "nine_questions.q9",
      cache_status: "degraded",
      provider_name: "provider-tools-default",
      trace_id: "trace-q9-degraded",
      context_updates: {
        q9_execution_diagnosis: {
          authenticity_status: "degraded",
          diagnosis_message: "Q9 posture output relies on incomplete projection evidence.",
        },
      },
      preprocessed_evidence: {
        cognitive_snapshot: {
          q1_to_q8_snapshot: {
            q1: { q1_uncertainty_profile: { uncertainties: ["unknown dependency"] } },
            q6: { forbidden_zone_profile: { absolute_red_lines: ["no fake green"] } },
          },
          uncertainty_count: 1,
          absolute_red_line_count: 1,
        },
        self_model: {
          cognitive_load: "medium",
          stability_level: "stable",
          confidence_drift: 0.02,
          recent_weaknesses: [
            { pattern_type: "overconfidence", severity: "warning", frequency: 2 },
          ],
        },
        reasoning_budget: {
          compute_remaining_ratio: 0.8,
          token_remaining_ratio: 0.7,
          time_remaining_ratio: 0.6,
          budget_pressure: "low",
        },
      },
      inference_result: {
        evaluation_style: "balanced",
        risk_tolerance: "low_risk",
        action_rhythm: "metered",
        confirmation_strategy: "wait for confirmation",
        evolution_direction: "inspect workflow",
      },
      llm_trace_payload: {},
      result: {},
    } as any);

    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q9"]}>
        <Routes>
          <Route path="/console/nine-questions/q9" element={<Q9Detail />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText(/Q9 真实性状态：降级\/部分失败/)).toBeInTheDocument();
    });

    expect(screen.getByText("medium")).toBeInTheDocument();
    expect(screen.getByText(/stable/)).toBeInTheDocument();
    expect(screen.getByText(/80.0%/)).toBeInTheDocument();
    expect(screen.getByText(/70.0%/)).toBeInTheDocument();
    expect(screen.getByText(/60.0%/)).toBeInTheDocument();
    expect(screen.getByText(/overconfidence/i)).toBeInTheDocument();
  });

  it("renders downstream integration modules from committed module outputs", async () => {
    vi.mocked(api.fetchNineQuestionDetail).mockResolvedValue({
      question_id: "q9",
      title: "我应该如何行动",
      tool_id: "nine_questions.q9",
      cache_status: "completed",
      provider_name: "provider-tools-default",
      trace_id: "trace-q9-integrations",
      context_updates: {},
      preprocessed_evidence: null,
      inference_result: null,
      llm_trace_payload: {},
      result: {},
    } as any);
    vi.mocked(api.fetchNineQuestionModules).mockResolvedValue({
      status: { status: "completed" },
      modules: {
        q9_audit_integration: { status: "completed", data: { module_kind: "audit", summary: "audit recorded" } },
        q9_memory_integration: { status: "completed", data: { module_kind: "memory", summary: "memory recorded" } },
        q9_reflection_integration: { status: "completed", data: { module_kind: "reflection", summary: "reflection recorded" } },
        q9_learning_integration: { status: "completed", data: { module_kind: "learning", summary: "learning recorded" } },
      },
    } as any);

    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q9"]}>
        <Routes>
          <Route path="/console/nine-questions/q9" element={<Q9Detail />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("q9-integration-audit")).toBeInTheDocument();
    });

    expect(screen.getByTestId("q9-integration-row-q9_audit_integration")).toHaveTextContent("audit recorded");
    expect(screen.getByTestId("q9-integration-row-q9_memory_integration")).toHaveTextContent("memory");
    expect(screen.getByTestId("q9-integration-row-q9_reflection_integration")).toHaveTextContent("reflection recorded");
    expect(screen.getByTestId("q9-integration-row-q9_learning_integration")).toHaveTextContent("learning");
  });
});
