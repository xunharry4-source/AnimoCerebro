import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import Q2Detail from "./Q2Detail";
import * as api from "../nineQuestionsApi";

vi.mock("../nineQuestionsApi", async () => {
  const actual = await vi.importActual("../nineQuestionsApi");
  return {
    ...actual,
    fetchNineQuestionDetail: vi.fn(),
    fetchNineQuestionSummary: vi.fn(),
    fetchNineQuestionEvidence: vi.fn(),
    fetchNineQuestionInference: vi.fn(),
    fetchNineQuestionTracePayload: vi.fn(),
    fetchNineQuestionRaw: vi.fn(),
    fetchNineQuestionModules: vi.fn(),
    executeNineQuestionRecoveryAction: vi.fn(),
  };
});

describe("Q2Detail functional tests", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("recovers Q1 summary from raw context updates when the Q2 evidence partition is empty", async () => {
    vi.mocked(api.fetchNineQuestionSummary).mockResolvedValue({
      status: "degraded",
      question_id: "q2",
    } as any);
    vi.mocked(api.fetchNineQuestionRaw).mockResolvedValue({
      trace_id: "trace-q2-q1-fallback",
      tool_id: "nine_questions.q2",
      mounted_plugins: [],
      context_updates: {
        workspace_domain_inference: {
          primary_domain: "production_server",
          secondary_domains: ["admin_console"],
          uncertainties: ["runtime_state_stale"],
          reasoning_summary: "Q1 identified a production server admin console.",
        },
        q1_scene_model: {
          primary_domain: "production_server",
          secondary_domains: ["admin_console"],
        },
        q1_uncertainty_profile: {
          risk_sources: ["runtime_state_stale"],
          risk_summary: "Runtime state may be stale.",
        },
        identity_kernel_snapshot: {
          meta_motivation: "Preserve continuity.",
          values_prohibition: "Do not fake state.",
          non_bypassable_constraints: ["NO_FAKE_RUNTIME_STATE"],
        },
      },
    } as any);
    vi.mocked(api.fetchNineQuestionModules).mockResolvedValue({ status: { status: "degraded" } } as any);
    vi.mocked(api.fetchNineQuestionEvidence).mockResolvedValue({} as any);
    vi.mocked(api.fetchNineQuestionInference).mockResolvedValue({
      role_profile: {
        identity_role: "Zentex Operator",
        active_role: "Runtime Auditor",
        task_role: "Q2 Identity Auditor",
      },
      mission_boundary: {
        current_mission: "Recover Q1 context display.",
        priority_duties: ["show upstream context"],
        continuity_boundaries: ["no fake completion"],
      },
    } as any);
    vi.mocked(api.fetchNineQuestionTracePayload).mockResolvedValue({} as any);

    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q2"]}>
        <Routes>
          <Route path="/console/nine-questions/q2" element={<Q2Detail />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("q2-detail-root")).toBeInTheDocument();
    });

    expect(screen.getByText(/production_server/)).toBeInTheDocument();
    expect(screen.getByText(/admin_console/)).toBeInTheDocument();
    expect(screen.queryByText(/Q1 context missing/i)).not.toBeInTheDocument();
  });

  it("recovers Q1 summary from raw result.context_updates when top-level raw context is empty", async () => {
    vi.mocked(api.fetchNineQuestionSummary).mockResolvedValue({
      status: "degraded",
      question_id: "q2",
    } as any);
    vi.mocked(api.fetchNineQuestionRaw).mockImplementation(async (questionId: string) => {
      if (questionId === "q1") {
        return {};
      }
      return {
        trace_id: "trace-q2-result-context-fallback",
        tool_id: "nine_questions.q2",
        mounted_plugins: [],
        context_updates: {},
        result: {
          context_updates: {
            workspace_domain_inference: {
              primary_domain: "ops_console",
              secondary_domains: ["incident_center"],
              uncertainties: ["signal_delay"],
              reasoning_summary: "Q1 was only written into result.context_updates.",
            },
            q1_scene_model: {
              primary_domain: "ops_console",
              secondary_domains: ["incident_center"],
            },
            q1_uncertainty_profile: {
              risk_sources: ["signal_delay"],
              risk_summary: "Signals may be delayed.",
            },
          },
        },
      };
    });
    vi.mocked(api.fetchNineQuestionModules).mockResolvedValue({ status: { status: "degraded" } } as any);
    vi.mocked(api.fetchNineQuestionEvidence).mockResolvedValue({} as any);
    vi.mocked(api.fetchNineQuestionInference).mockImplementation(async (questionId: string) => {
      if (questionId === "q1") return {};
      return {
        role_profile: {
          identity_role: "Zentex Operator",
          active_role: "Runtime Auditor",
          task_role: "Q2 Identity Auditor",
        },
        mission_boundary: {
          current_mission: "Recover Q1 context display.",
          priority_duties: ["show upstream context"],
          continuity_boundaries: ["no fake completion"],
        },
      } as any;
    });
    vi.mocked(api.fetchNineQuestionTracePayload).mockResolvedValue({} as any);

    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q2"]}>
        <Routes>
          <Route path="/console/nine-questions/q2" element={<Q2Detail />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("q2-detail-root")).toBeInTheDocument();
    });

    expect(screen.getByText(/ops_console/)).toBeInTheDocument();
    expect(screen.getByText(/incident_center/)).toBeInTheDocument();
  });

  it("keeps the Q2 page layout available when evidence and inference sections fail but base partitions load", async () => {
    vi.mocked(api.fetchNineQuestionDetail).mockRejectedValue(new Error("legacy detail endpoint should not be used"));
    vi.mocked(api.fetchNineQuestionSummary).mockResolvedValue({
      status: "partial_failed",
      question_id: "q2",
    } as any);
    vi.mocked(api.fetchNineQuestionRaw).mockResolvedValue({
      trace_id: "trace-q2-functional",
      tool_id: "nine_questions.q2",
      llm_trace_payload: {
        provider_name: "provider-tools-default",
        elapsed_ms: 31,
      },
      mounted_plugins: [],
    } as any);
    vi.mocked(api.fetchNineQuestionModules).mockResolvedValue({
      status: { status: "partial_failed" },
    } as any);
    vi.mocked(api.fetchNineQuestionEvidence).mockRejectedValue(new Error("Q2 evidence unavailable"));
    vi.mocked(api.fetchNineQuestionInference).mockRejectedValue(new Error("Q2 inference unavailable"));
    vi.mocked(api.fetchNineQuestionTracePayload).mockRejectedValue(new Error("Q2 trace unavailable"));

    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q2"]}>
        <Routes>
          <Route path="/console/nine-questions/q2" element={<Q2Detail />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("q2-detail-root")).toBeInTheDocument();
    });

    expect(api.fetchNineQuestionSummary).toHaveBeenCalledWith("q2");
    expect(api.fetchNineQuestionRaw).toHaveBeenCalledWith("q2");
    expect(api.fetchNineQuestionModules).toHaveBeenCalledWith("q2");
    expect(screen.getByText(/Q2 当前只拿到了部分分区数据/)).toBeInTheDocument();
    expect(screen.getByText(/Q2 数据详情/)).toBeInTheDocument();
    expect(screen.getByText(/Q2 结构化证据/)).toBeInTheDocument();
    expect(screen.getByText(/Q2 evidence unavailable/)).toBeInTheDocument();
    expect(screen.getByText(/Q2 inference unavailable/)).toBeInTheDocument();
  });

  it("renders Q2 recovery plan from structured execution diagnosis", async () => {
    vi.mocked(api.fetchNineQuestionSummary).mockResolvedValue({
      status: "degraded",
      question_id: "q2",
    } as any);
    vi.mocked(api.fetchNineQuestionRaw).mockResolvedValue({
      trace_id: "trace-q2-recovery",
      tool_id: "nine_questions.q2",
      llm_trace_payload: {
        provider_name: "provider-tools-default",
        elapsed_ms: 31,
      },
      mounted_plugins: [],
      context_updates: {
        q2_execution_diagnosis: {
          authenticity_status: "degraded",
          diagnosis_message: "Q2 used degraded upstream identity context.",
          used_fallback: true,
          recovery_plan: {
            retriable: true,
            rollback_available: true,
            partial_retry_available: true,
            partial_replace_available: false,
            actions: [
              {
                action_id: "q2-rerun-question",
                label: "重跑 Q2 及下游",
                kind: "retry",
                executable: true,
                scope: "question_downstream",
                target: "q2",
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
      <MemoryRouter initialEntries={["/console/nine-questions/q2"]}>
        <Routes>
          <Route path="/console/nine-questions/q2" element={<Q2Detail />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("q2-recovery-plan")).toBeInTheDocument();
    });

    expect(screen.getByTestId("q2-recovery-plan")).toHaveTextContent("可重试：是");
    expect(screen.getByTestId("q2-recovery-action-q2-rerun-question")).toHaveTextContent(
      "重跑 Q2 及下游 | retry | question_downstream | executable | q2",
    );
    expect(screen.getByTestId("q2-recovery-action-button-q2-rerun-question")).toBeInTheDocument();
  });

  it("executes Q2 recovery actions from the monitoring page", async () => {
    vi.mocked(api.fetchNineQuestionSummary).mockResolvedValue({ status: "degraded", question_id: "q2" } as any);
    vi.mocked(api.fetchNineQuestionRaw).mockResolvedValue({
      trace_id: "trace-q2-recovery-action",
      tool_id: "nine_questions.q2",
      mounted_plugins: [],
      context_updates: {
        q2_execution_diagnosis: {
          authenticity_status: "degraded",
          diagnosis_message: "Q2 used degraded upstream identity context.",
          recovery_plan: {
            retriable: true,
            rollback_available: true,
            partial_retry_available: true,
            partial_replace_available: false,
            actions: [
              {
                action_id: "q2-rollback-previous-success",
                label: "回滚到上一份成功快照",
                kind: "rollback",
                executable: true,
                scope: "record",
                target: "q2",
                path: "/api/web/nine-questions/q2/rollback",
              },
            ],
          },
        },
      },
    } as any);
    vi.mocked(api.fetchNineQuestionModules).mockResolvedValue({ status: { status: "degraded" } } as any);
    vi.mocked(api.fetchNineQuestionEvidence).mockResolvedValue({} as any);
    vi.mocked(api.fetchNineQuestionInference).mockResolvedValue({} as any);
    vi.mocked(api.fetchNineQuestionTracePayload).mockResolvedValue({} as any);
    vi.mocked(api.executeNineQuestionRecoveryAction).mockResolvedValue({
      started: true,
      trace_id: "trace-q2",
      refresh_reason: "single_nine_question_rolled_back:q2",
      snapshot_version: 3,
      revision: 1,
    } as any);

    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q2"]}>
        <Routes>
          <Route path="/console/nine-questions/q2" element={<Q2Detail />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("q2-recovery-action-button-q2-rollback-previous-success")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("q2-recovery-action-button-q2-rollback-previous-success"));

    await waitFor(() => {
      expect(api.executeNineQuestionRecoveryAction).toHaveBeenCalledWith(
        expect.objectContaining({
          action_id: "q2-rollback-previous-success",
          path: "/api/web/nine-questions/q2/rollback",
        }),
      );
    });
  });

  it("renders downstream integration modules from committed module outputs", async () => {
    vi.mocked(api.fetchNineQuestionSummary).mockResolvedValue({ status: "completed", question_id: "q2" } as any);
    vi.mocked(api.fetchNineQuestionEvidence).mockResolvedValue({} as any);
    vi.mocked(api.fetchNineQuestionInference).mockImplementation(async (questionId: string) => {
      if (questionId === "q1") return {};
      return {} as any;
    });
    vi.mocked(api.fetchNineQuestionTracePayload).mockResolvedValue({} as any);
    vi.mocked(api.fetchNineQuestionRaw).mockImplementation(async (questionId: string) => {
      if (questionId === "q1") return {};
      return {
        trace_id: "trace-q2-integrations",
        tool_id: "nine_questions.q2",
        context_updates: {},
        llm_trace_payload: {},
        mounted_plugins: [],
      } as any;
    });
    vi.mocked(api.fetchNineQuestionModules).mockResolvedValue({
      status: { status: "completed" },
      modules: {
        q2_audit_integration: { status: "completed", data: { module_kind: "audit", summary: "audit recorded" } },
        q2_memory_integration: { status: "completed", data: { module_kind: "memory", summary: "memory recorded" } },
        q2_reflection_integration: { status: "completed", data: { module_kind: "reflection", summary: "reflection recorded" } },
        q2_learning_integration: { status: "completed", data: { module_kind: "learning", summary: "learning recorded" } },
      },
    } as any);

    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q2"]}>
        <Routes>
          <Route path="/console/nine-questions/q2" element={<Q2Detail />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("q2-integration-audit")).toBeInTheDocument();
    });

    expect(screen.getByTestId("q2-integration-row-q2_audit_integration")).toHaveTextContent("audit recorded");
    expect(screen.getByTestId("q2-integration-row-q2_memory_integration")).toHaveTextContent("memory");
    expect(screen.getByTestId("q2-integration-row-q2_reflection_integration")).toHaveTextContent("reflection recorded");
    expect(screen.getByTestId("q2-integration-row-q2_learning_integration")).toHaveTextContent("learning");
  });
});
