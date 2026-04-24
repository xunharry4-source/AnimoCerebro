import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import Q5Detail from "./Q5Detail";
import * as api from "../nineQuestionsApi";

vi.mock("../nineQuestionsApi", async () => {
  const actual = await vi.importActual("../nineQuestionsApi");
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

describe("Q5Detail functional tests", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders Q5 recovery plan and workflow button from structured execution diagnosis", async () => {
    vi.mocked(api.fetchNineQuestionSummary).mockResolvedValue({ status: "degraded", question_id: "q5" } as any);
    vi.mocked(api.fetchNineQuestionEvidence).mockResolvedValue({} as any);
    vi.mocked(api.fetchNineQuestionInference).mockResolvedValue({} as any);
    vi.mocked(api.fetchNineQuestionTracePayload).mockResolvedValue({} as any);
    vi.mocked(api.fetchNineQuestionModules).mockResolvedValue({ status: { status: "degraded" } } as any);
    vi.mocked(api.fetchNineQuestionRaw).mockResolvedValue({
      trace_id: "trace-q5-recovery",
      tool_id: "nine_questions.q5",
      context_updates: {
        q5_execution_diagnosis: {
          authenticity_status: "degraded",
          diagnosis_message: "Q5 relies on snapshot-only policy sources.",
          used_fallback: true,
          recovery_plan: {
            retriable: true,
            rollback_available: false,
            partial_retry_available: true,
            partial_replace_available: false,
            actions: [
              {
                action_id: "q5-rerun-question",
                label: "重跑 Q5 及下游",
                kind: "retry",
                executable: true,
                scope: "question_downstream",
                target: "q5",
              },
            ],
          },
        },
      },
      llm_trace_payload: { provider_name: "provider-tools-default" },
    } as any);

    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q5"]}>
        <Routes>
          <Route path="/console/nine-questions/q5" element={<Q5Detail />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("q5-recovery-plan")).toBeInTheDocument();
    });

    expect(screen.getByTestId("q5-recovery-action-q5-rerun-question")).toHaveTextContent(
      "重跑 Q5 及下游 | retry | question_downstream | executable | q5",
    );
    expect(screen.getByTestId("q5-workflow-nav-button")).toHaveAttribute("href", "/console/nine-questions/q5/workflow");
  });

  it("renders downstream integration modules from committed module outputs", async () => {
    vi.mocked(api.fetchNineQuestionSummary).mockResolvedValue({ status: "completed", question_id: "q5" } as any);
    vi.mocked(api.fetchNineQuestionEvidence).mockResolvedValue({} as any);
    vi.mocked(api.fetchNineQuestionInference).mockResolvedValue({} as any);
    vi.mocked(api.fetchNineQuestionTracePayload).mockResolvedValue({} as any);
    vi.mocked(api.fetchNineQuestionRaw).mockResolvedValue({
      trace_id: "trace-q5-integrations",
      tool_id: "nine_questions.q5",
      context_updates: {},
      llm_trace_payload: {},
    } as any);
    vi.mocked(api.fetchNineQuestionModules).mockResolvedValue({
      status: { status: "completed" },
      modules: {
        q5_audit_integration: { status: "completed", data: { module_kind: "audit", summary: "audit recorded" } },
        q5_memory_integration: { status: "completed", data: { module_kind: "memory", summary: "memory recorded" } },
        q5_reflection_integration: { status: "completed", data: { module_kind: "reflection", summary: "reflection recorded" } },
        q5_learning_integration: { status: "completed", data: { module_kind: "learning", summary: "learning recorded" } },
      },
    } as any);

    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q5"]}>
        <Routes>
          <Route path="/console/nine-questions/q5" element={<Q5Detail />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("q5-integration-audit")).toBeInTheDocument();
    });

    expect(screen.getByTestId("q5-integration-row-q5_audit_integration")).toHaveTextContent("audit recorded");
    expect(screen.getByTestId("q5-integration-row-q5_memory_integration")).toHaveTextContent("memory");
    expect(screen.getByTestId("q5-integration-row-q5_reflection_integration")).toHaveTextContent("reflection recorded");
    expect(screen.getByTestId("q5-integration-row-q5_learning_integration")).toHaveTextContent("learning");
  });
});
