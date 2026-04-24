import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import Q3Detail from "./Q3Detail";
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

describe("Q3Detail functional tests", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("keeps the Q3 page layout available when evidence and inference sections fail but base partitions load", async () => {
    vi.mocked(api.fetchNineQuestionSummary).mockResolvedValue({
      status: "partial_failed",
      question_id: "q3",
    } as any);
    vi.mocked(api.fetchNineQuestionRaw).mockResolvedValue({
      trace_id: "trace-q3-functional",
      tool_id: "nine_questions.q3",
      llm_trace_payload: {
        provider_name: "provider-tools-default",
        elapsed_ms: 64,
      },
    } as any);
    vi.mocked(api.fetchNineQuestionModules).mockResolvedValue({
      status: { status: "partial_failed" },
    } as any);
    vi.mocked(api.fetchNineQuestionEvidence).mockRejectedValue(new Error("Q3 evidence unavailable"));
    vi.mocked(api.fetchNineQuestionInference).mockRejectedValue(new Error("Q3 inference unavailable"));
    vi.mocked(api.fetchNineQuestionTracePayload).mockRejectedValue(new Error("Q3 trace unavailable"));

    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q3"]}>
        <Routes>
          <Route path="/console/nine-questions/q3" element={<Q3Detail />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("q3-detail-root")).toBeInTheDocument();
    });

    expect(screen.getByText(/Q3 当前只拿到了部分分区数据/)).toBeInTheDocument();
    expect(screen.getByText(/Q3 evidence unavailable/)).toBeInTheDocument();
    expect(screen.getByText(/Q3 inference unavailable/)).toBeInTheDocument();
    expect(screen.getByText(/结构化资源与工具证据/)).toBeInTheDocument();
  });

  it("renders Q3 recovery plan from structured execution diagnosis", async () => {
    vi.mocked(api.fetchNineQuestionSummary).mockResolvedValue({
      status: "degraded",
      question_id: "q3",
    } as any);
    vi.mocked(api.fetchNineQuestionRaw).mockResolvedValue({
      trace_id: "trace-q3-recovery",
      tool_id: "nine_questions.q3",
      llm_trace_payload: {
        provider_name: "provider-tools-default",
        elapsed_ms: 64,
      },
      context_updates: {
        q3_execution_diagnosis: {
          authenticity_status: "degraded",
          diagnosis_message: "Q3 inventory completed with degraded runtime sources.",
          used_fallback: true,
          recovery_plan: {
            retriable: true,
            rollback_available: false,
            partial_retry_available: true,
            partial_replace_available: false,
            actions: [
              {
                action_id: "q3-rerun-question",
                label: "重跑 Q3 及下游",
                kind: "retry",
                executable: true,
                scope: "question_downstream",
                target: "q3",
              },
            ],
          },
        },
      },
    } as any);
    vi.mocked(api.fetchNineQuestionModules).mockResolvedValue({
      status: { status: "degraded" },
    } as any);
    vi.mocked(api.fetchNineQuestionEvidence).mockResolvedValue({} as any);
    vi.mocked(api.fetchNineQuestionInference).mockResolvedValue({} as any);
    vi.mocked(api.fetchNineQuestionTracePayload).mockResolvedValue({} as any);

    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q3"]}>
        <Routes>
          <Route path="/console/nine-questions/q3" element={<Q3Detail />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("q3-recovery-plan")).toBeInTheDocument();
    });

    expect(screen.getByTestId("q3-recovery-plan")).toHaveTextContent("可重试：是");
    expect(screen.getByTestId("q3-recovery-action-q3-rerun-question")).toHaveTextContent(
      "重跑 Q3 及下游 | retry | question_downstream | executable | q3",
    );
  });

  it("renders downstream integration modules from committed module outputs", async () => {
    vi.mocked(api.fetchNineQuestionSummary).mockResolvedValue({ status: "completed", question_id: "q3" } as any);
    vi.mocked(api.fetchNineQuestionEvidence).mockResolvedValue({} as any);
    vi.mocked(api.fetchNineQuestionInference).mockResolvedValue({} as any);
    vi.mocked(api.fetchNineQuestionTracePayload).mockResolvedValue({} as any);
    vi.mocked(api.fetchNineQuestionRaw).mockResolvedValue({
      trace_id: "trace-q3-integrations",
      tool_id: "nine_questions.q3",
      context_updates: {},
      llm_trace_payload: {},
    } as any);
    vi.mocked(api.fetchNineQuestionModules).mockResolvedValue({
      status: { status: "completed" },
      modules: {
        q3_audit_integration: { status: "completed", data: { module_kind: "audit", summary: "audit recorded" } },
        q3_memory_integration: { status: "completed", data: { module_kind: "memory", summary: "memory recorded" } },
        q3_reflection_integration: { status: "completed", data: { module_kind: "reflection", summary: "reflection recorded" } },
        q3_learning_integration: { status: "completed", data: { module_kind: "learning", summary: "learning recorded" } },
      },
    } as any);

    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q3"]}>
        <Routes>
          <Route path="/console/nine-questions/q3" element={<Q3Detail />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("q3-integration-audit")).toBeInTheDocument();
    });

    expect(screen.getByTestId("q3-integration-row-q3_audit_integration")).toHaveTextContent("audit recorded");
    expect(screen.getByTestId("q3-integration-row-q3_memory_integration")).toHaveTextContent("memory");
    expect(screen.getByTestId("q3-integration-row-q3_reflection_integration")).toHaveTextContent("reflection recorded");
    expect(screen.getByTestId("q3-integration-row-q3_learning_integration")).toHaveTextContent("learning");
  });
});
