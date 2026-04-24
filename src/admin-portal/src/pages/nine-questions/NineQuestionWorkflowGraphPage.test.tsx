import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import NineQuestionWorkflowGraphPage from "./NineQuestionWorkflowGraphPage";
import * as api from "./nineQuestionsApi";

vi.mock("./nineQuestionsApi", async () => {
  const actual = await vi.importActual("./nineQuestionsApi");
  return {
    ...actual,
    fetchNineQuestionSummary: vi.fn(),
    fetchNineQuestionRaw: vi.fn(),
    fetchNineQuestionModules: vi.fn(),
    executeNineQuestionRecoveryAction: vi.fn(),
    rollbackNineQuestionModule: vi.fn(),
  };
});

describe("NineQuestionWorkflowGraphPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders per-question workflow nodes in multi-lane workflow board", async () => {
    vi.mocked(api.fetchNineQuestionSummary).mockResolvedValue({ status: "degraded", question_id: "q5" } as any);
    vi.mocked(api.fetchNineQuestionRaw).mockResolvedValue({
      trace_id: "trace-q5-workflow",
      context_updates: {
        q5_execution_diagnosis: {
          authenticity_status: "degraded",
          diagnosis_message: "Q5 relies on snapshot-only policy sources.",
          used_fallback: true,
          module_runs: [
            { module_id: "q5_q4_boundary_validation", status: "completed", source: "plugins.nine_questions.q5" },
            { module_id: "q5_contact_policy_validation", status: "missing", error_message: "Contact policy is not available." },
          ],
          plugin_runs: [
            {
              plugin_id: "authorization-policy-plugin",
              feature_code: "nine_questions.q5",
              expected: true,
              attempted: true,
              status: "completed",
            },
          ],
          upstream_dependencies: [
            { dependency_id: "q4", required: true, status: "completed", message: "Q4 capability boundary is required." },
          ],
          recovery_plan: {
            question_id: "q5",
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
              {
                action_id: "q5-refresh-contact-policy",
                label: "刷新 contact policy",
                kind: "partial_retry",
                executable: true,
                scope: "module",
                target: "q5_contact_policy_validation",
                path: "/api/web/nine-questions/q5/modules/q5_contact_policy_validation/retry",
              },
            ],
          },
        },
      },
    } as any);
    vi.mocked(api.fetchNineQuestionModules).mockResolvedValue({ status: { status: "degraded" }, modules: {} } as any);

    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q5/workflow"]}>
        <Routes>
          <Route path="/console/nine-questions/:q_id/workflow" element={<NineQuestionWorkflowGraphPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("question-workflow-graph-page")).toBeInTheDocument();
    });

    expect(screen.getByText(/Q5_What_Am_I_Allowed_To_Do 内部工作流图/)).toBeInTheDocument();
    expect(screen.getByTestId("question-workflow-canvas")).toBeInTheDocument();
    expect(screen.getByTestId("question-workflow-node-q5-start")).toHaveTextContent("Q5 Start");
    expect(screen.getByTestId("question-workflow-node-q5-outcome")).toHaveTextContent("Q5 Outcome");
    expect(screen.getByTestId("question-workflow-node-dependency-0")).toHaveTextContent("q4");
    expect(screen.getByTestId("question-workflow-node-module-0")).toHaveTextContent("q5 q4 boundary validation");
    expect(screen.getByTestId("question-workflow-node-module-1")).toHaveTextContent("Contact policy is not available.");
    expect(screen.getByTestId("question-workflow-node-plugin-0")).toHaveTextContent("authorization-policy-plugin");
    expect(screen.getByTestId("question-workflow-node-recovery-0")).toHaveTextContent("question_downstream");
    expect(screen.getByTestId("module-retry-button-q5_contact_policy_validation")).toBeInTheDocument();
    expect(screen.getByTestId("module-rollback-button-q5_contact_policy_validation")).toBeInTheDocument();
  });

  it("executes module rollback from the workflow graph action panel", async () => {
    vi.mocked(api.fetchNineQuestionSummary).mockResolvedValue({ status: "degraded", question_id: "q8" } as any);
    vi.mocked(api.fetchNineQuestionRaw).mockResolvedValue({
      trace_id: "trace-q8-workflow",
      context_updates: {
        q8_execution_diagnosis: {
          authenticity_status: "degraded",
          diagnosis_message: "Q8 generated a suggested queue but did not persist tasks.",
          used_fallback: true,
          module_runs: [
            { module_id: "q8_task_persistence", status: "missing", error_message: "Task persistence is missing." },
          ],
          plugin_runs: [],
          upstream_dependencies: [],
          recovery_plan: null,
        },
      },
    } as any);
    vi.mocked(api.fetchNineQuestionModules).mockResolvedValue({ status: { status: "degraded" }, modules: {} } as any);
    vi.mocked(api.rollbackNineQuestionModule).mockResolvedValue({
      started: true,
      trace_id: "trace-q8",
      refresh_reason: "single_nine_question_module_rolled_back:q8:q8_task_persistence",
      snapshot_version: 2,
      revision: 1,
    } as any);

    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q8/workflow"]}>
        <Routes>
          <Route path="/console/nine-questions/:q_id/workflow" element={<NineQuestionWorkflowGraphPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("module-rollback-button-q8_task_persistence")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("module-rollback-button-q8_task_persistence"));

    await waitFor(() => {
      expect(api.rollbackNineQuestionModule).toHaveBeenCalledWith("q8", "q8_task_persistence");
    });
  });

  it("executes module retry from the workflow graph action panel when recovery plan exposes an executable module action", async () => {
    vi.mocked(api.fetchNineQuestionSummary).mockResolvedValue({ status: "degraded", question_id: "q8" } as any);
    vi.mocked(api.fetchNineQuestionRaw).mockResolvedValue({
      trace_id: "trace-q8-workflow",
      context_updates: {
        q8_execution_diagnosis: {
          authenticity_status: "degraded",
          diagnosis_message: "Q8 generated a suggested queue but did not persist tasks.",
          used_fallback: true,
          module_runs: [
            { module_id: "q8_task_persistence", status: "missing", error_message: "Task persistence is missing." },
          ],
          plugin_runs: [],
          upstream_dependencies: [],
          recovery_plan: {
            question_id: "q8",
            retriable: true,
            rollback_available: false,
            partial_retry_available: true,
            partial_replace_available: true,
            actions: [
              {
                action_id: "q8-recompute-persistence",
                label: "局部重试任务持久化",
                kind: "partial_retry",
                executable: true,
                scope: "module",
                target: "q8_task_persistence",
                path: "/api/web/nine-questions/q8/modules/q8_task_persistence/retry",
              },
            ],
          },
        },
      },
    } as any);
    vi.mocked(api.fetchNineQuestionModules).mockResolvedValue({ status: { status: "degraded" }, modules: {} } as any);
    vi.mocked(api.executeNineQuestionRecoveryAction).mockResolvedValue({
      started: true,
      trace_id: "trace-q8",
      refresh_reason: "single_nine_question_module_retried:q8:q8_task_persistence",
      snapshot_version: 2,
      revision: 1,
    } as any);

    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q8/workflow"]}>
        <Routes>
          <Route path="/console/nine-questions/:q_id/workflow" element={<NineQuestionWorkflowGraphPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("module-retry-button-q8_task_persistence")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("module-retry-button-q8_task_persistence"));

    await waitFor(() => {
      expect(api.executeNineQuestionRecoveryAction).toHaveBeenCalledWith(
        expect.objectContaining({
          action_id: "q8-recompute-persistence",
          target: "q8_task_persistence",
        }),
      );
    });
  });

  it("renders q7 functional alternative retry action when the module is degraded", async () => {
    vi.mocked(api.fetchNineQuestionSummary).mockResolvedValue({ status: "degraded", question_id: "q7" } as any);
    vi.mocked(api.fetchNineQuestionRaw).mockResolvedValue({
      trace_id: "trace-q7-workflow",
      context_updates: {
        q7_execution_diagnosis: {
          authenticity_status: "degraded",
          diagnosis_message: "Q7 suggestions remain unverified.",
          used_fallback: true,
          module_runs: [
            { module_id: "q7_functional_alternative_chain", status: "missing", error_message: "No functional alternative plugins executed." },
          ],
          plugin_runs: [],
          upstream_dependencies: [],
          recovery_plan: {
            question_id: "q7",
            retriable: true,
            rollback_available: false,
            partial_retry_available: true,
            partial_replace_available: false,
            actions: [
              {
                action_id: "q7-refresh-functional-alternatives",
                label: "刷新备选策略插件输入",
                kind: "partial_retry",
                executable: true,
                scope: "module",
                target: "q7_functional_alternative_chain",
                path: "/api/web/nine-questions/q7/modules/q7_functional_alternative_chain/retry",
              },
            ],
          },
        },
      },
    } as any);
    vi.mocked(api.fetchNineQuestionModules).mockResolvedValue({ status: { status: "degraded" }, modules: {} } as any);

    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q7/workflow"]}>
        <Routes>
          <Route path="/console/nine-questions/:q_id/workflow" element={<NineQuestionWorkflowGraphPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("module-retry-button-q7_functional_alternative_chain")).toBeInTheDocument();
    });
  });

  it("renders four downstream integration nodes in fixed order from module_runs", async () => {
    vi.mocked(api.fetchNineQuestionSummary).mockResolvedValue({ status: "completed", question_id: "q9" } as any);
    vi.mocked(api.fetchNineQuestionRaw).mockResolvedValue({
      trace_id: "trace-q9-workflow",
      context_updates: {
        q9_execution_diagnosis: {
          authenticity_status: "completed",
          diagnosis_message: "Q9 downstream integrations completed.",
          used_fallback: false,
          module_runs: [
            { module_id: "q9_audit_integration", status: "completed", source: "plugins.nine_questions.q9" },
            { module_id: "q9_memory_integration", status: "degraded", source: "plugins.nine_questions.q9", error_message: "memory partial" },
            { module_id: "q9_reflection_integration", status: "missing", source: "plugins.nine_questions.q9", error_message: "reflection missing" },
            { module_id: "q9_learning_integration", status: "failed", source: "plugins.nine_questions.q9", error_message: "learning failed" },
          ],
          plugin_runs: [],
          upstream_dependencies: [],
          recovery_plan: null,
        },
      },
    } as any);
    vi.mocked(api.fetchNineQuestionModules).mockResolvedValue({ status: { status: "completed" }, modules: {} } as any);

    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q9/workflow"]}>
        <Routes>
          <Route path="/console/nine-questions/:q_id/workflow" element={<NineQuestionWorkflowGraphPage />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("question-workflow-node-module-0")).toBeInTheDocument();
    });

    expect(screen.getByTestId("question-workflow-node-module-0")).toHaveTextContent("q9 audit integration");
    expect(screen.getByTestId("question-workflow-node-module-1")).toHaveTextContent("q9 memory integration");
    expect(screen.getByTestId("question-workflow-node-module-1")).toHaveTextContent("degraded");
    expect(screen.getByTestId("question-workflow-node-module-2")).toHaveTextContent("q9 reflection integration");
    expect(screen.getByTestId("question-workflow-node-module-2")).toHaveTextContent("missing");
    expect(screen.getByTestId("question-workflow-node-module-3")).toHaveTextContent("q9 learning integration");
    expect(screen.getByTestId("question-workflow-node-module-3")).toHaveTextContent("failed");
  });
});
