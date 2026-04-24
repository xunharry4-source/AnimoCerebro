import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import Q6Detail from "./Q6Detail";
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

describe("Q6Detail functional tests", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false }));
  });

  it("renders Q6 recovery plan and workflow button from structured execution diagnosis", async () => {
    vi.mocked(api.fetchNineQuestionSummary).mockResolvedValue({ status: "degraded", question_id: "q6" } as any);
    vi.mocked(api.fetchNineQuestionEvidence).mockResolvedValue({} as any);
    vi.mocked(api.fetchNineQuestionInference).mockResolvedValue({} as any);
    vi.mocked(api.fetchNineQuestionTracePayload).mockResolvedValue({} as any);
    vi.mocked(api.fetchNineQuestionModules).mockResolvedValue({ status: { status: "degraded" } } as any);
    vi.mocked(api.fetchNineQuestionRaw).mockResolvedValue({
      trace_id: "trace-q6-recovery",
      tool_id: "nine_questions.q6",
      context_updates: {
        q6_execution_diagnosis: {
          authenticity_status: "degraded",
          diagnosis_message: "Q6 currently relies on static baseline only.",
          recovery_plan: {
            retriable: true,
            rollback_available: false,
            partial_retry_available: true,
            partial_replace_available: false,
            actions: [
              {
                action_id: "q6-rerun-question",
                label: "重跑 Q6 及下游",
                kind: "retry",
                executable: true,
                scope: "question_downstream",
                target: "q6",
              },
            ],
          },
        },
      },
      llm_trace_payload: { provider_name: "provider-tools-default" },
    } as any);

    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q6"]}>
        <Routes>
          <Route path="/console/nine-questions/q6" element={<Q6Detail />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("q6-recovery-plan")).toBeInTheDocument();
    });

    expect(screen.getByTestId("q6-recovery-action-q6-rerun-question")).toHaveTextContent(
      "重跑 Q6 及下游 | retry | question_downstream | executable | q6",
    );
    expect(screen.getByTestId("q6-workflow-nav-button")).toHaveAttribute("href", "/console/nine-questions/q6/workflow");
  });

  it("renders downstream integration modules from committed module outputs", async () => {
    vi.mocked(api.fetchNineQuestionSummary).mockResolvedValue({ status: "completed", question_id: "q6" } as any);
    vi.mocked(api.fetchNineQuestionEvidence).mockResolvedValue({} as any);
    vi.mocked(api.fetchNineQuestionInference).mockResolvedValue({} as any);
    vi.mocked(api.fetchNineQuestionTracePayload).mockResolvedValue({} as any);
    vi.mocked(api.fetchNineQuestionRaw).mockResolvedValue({
      trace_id: "trace-q6-integrations",
      tool_id: "nine_questions.q6",
      context_updates: {},
      llm_trace_payload: {},
    } as any);
    vi.mocked(api.fetchNineQuestionModules).mockResolvedValue({
      status: { status: "completed" },
      modules: {
        q6_audit_integration: { status: "completed", data: { module_kind: "audit", summary: "audit recorded" } },
        q6_memory_integration: { status: "completed", data: { module_kind: "memory", summary: "memory recorded" } },
        q6_reflection_integration: { status: "completed", data: { module_kind: "reflection", summary: "reflection recorded" } },
        q6_learning_integration: { status: "completed", data: { module_kind: "learning", summary: "learning recorded" } },
      },
    } as any);

    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q6"]}>
        <Routes>
          <Route path="/console/nine-questions/q6" element={<Q6Detail />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("q6-integration-audit")).toBeInTheDocument();
    });

    expect(screen.getByTestId("q6-integration-row-q6_audit_integration")).toHaveTextContent("audit recorded");
    expect(screen.getByTestId("q6-integration-row-q6_memory_integration")).toHaveTextContent("memory");
    expect(screen.getByTestId("q6-integration-row-q6_reflection_integration")).toHaveTextContent("reflection recorded");
    expect(screen.getByTestId("q6-integration-row-q6_learning_integration")).toHaveTextContent("learning");
  });
});
