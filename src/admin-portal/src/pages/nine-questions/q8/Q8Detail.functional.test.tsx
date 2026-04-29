import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { Q8Detail } from "./Q8Detail";
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

describe("Q8Detail functional tests", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    const storage = new Map<string, string>();
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      value: {
        getItem: vi.fn((key: string) => storage.get(key) ?? null),
        setItem: vi.fn((key: string, value: string) => {
          storage.set(key, value);
        }),
        removeItem: vi.fn((key: string) => {
          storage.delete(key);
        }),
      },
    });
  });

  it("renders downstream integration modules from committed module outputs", async () => {
    vi.mocked(api.fetchNineQuestionSummary).mockResolvedValue({ status: "completed", question_id: "q8" } as any);
    vi.mocked(api.fetchNineQuestionEvidence).mockResolvedValue({} as any);
    vi.mocked(api.fetchNineQuestionInference).mockResolvedValue({} as any);
    vi.mocked(api.fetchNineQuestionTracePayload).mockResolvedValue({} as any);
    vi.mocked(api.fetchNineQuestionRaw).mockResolvedValue({
      trace_id: "trace-q8-integrations",
      tool_id: "nine_questions.q8",
      context_updates: {},
      llm_trace_payload: {},
    } as any);
    vi.mocked(api.fetchNineQuestionModules).mockResolvedValue({
      status: { status: "completed" },
      modules: {
        q8_audit_integration: { status: "completed", data: { module_kind: "audit", summary: "audit recorded" } },
        q8_memory_integration: { status: "completed", data: { module_kind: "memory", summary: "memory recorded" } },
        q8_reflection_integration: { status: "completed", data: { module_kind: "reflection", summary: "reflection recorded" } },
        q8_learning_integration: { status: "completed", data: { module_kind: "learning", summary: "learning recorded" } },
      },
    } as any);

    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q8"]}>
        <Routes>
          <Route path="/console/nine-questions/q8" element={<Q8Detail />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("q8-integration-audit")).toBeInTheDocument();
    });

    expect(screen.getByTestId("q8-integration-row-q8_audit_integration")).toHaveTextContent("audit recorded");
    expect(screen.getByTestId("q8-integration-row-q8_memory_integration")).toHaveTextContent("memory");
    expect(screen.getByTestId("q8-integration-row-q8_reflection_integration")).toHaveTextContent("reflection recorded");
    expect(screen.getByTestId("q8-integration-row-q8_learning_integration")).toHaveTextContent("learning");
  });

  it("does not keep the page in loading state when workspace goals fetch hangs", async () => {
    window.localStorage.setItem("currentWorkspaceId", "workspace-q8-hang");
    vi.stubGlobal("fetch", vi.fn(() => new Promise(() => {})));

    vi.mocked(api.fetchNineQuestionSummary).mockResolvedValue({ status: "completed", question_id: "q8" } as any);
    vi.mocked(api.fetchNineQuestionEvidence).mockResolvedValue({
      aggregated_context: {
        absolute_red_line_count: 1,
        capability_ceiling_count: 2,
        q1_to_q7_snapshot: {},
      },
      runtime_state: {
        persistent_task_state: [],
        cognitive_agenda: [],
      },
    } as any);
    vi.mocked(api.fetchNineQuestionInference).mockResolvedValue({
      task_queue: { next_self_tasks: [], blocked_self_tasks: [], proactive_actions: [] },
      objective_profile: { current_primary_objective: "stabilize", current_phase_tasks: [] },
    } as any);
    vi.mocked(api.fetchNineQuestionTracePayload).mockResolvedValue({} as any);
    vi.mocked(api.fetchNineQuestionRaw).mockResolvedValue({
      trace_id: "trace-q8-hang",
      tool_id: "nine_questions.q8",
      context_updates: {},
      llm_trace_payload: {},
    } as any);
    vi.mocked(api.fetchNineQuestionModules).mockResolvedValue({
      status: { status: "completed" },
      modules: {},
    } as any);

    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q8"]}>
        <Routes>
          <Route path="/console/nine-questions/q8" element={<Q8Detail />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("q8-detail-root")).toBeInTheDocument();
    }, { timeout: 300 });
  });

  it("shows evidence data by default when inference is missing but upstream context exists", async () => {
    vi.mocked(api.fetchNineQuestionSummary).mockResolvedValue({ status: "partial_failed", question_id: "q8" } as any);
    vi.mocked(api.fetchNineQuestionEvidence).mockResolvedValue({
      aggregated_context: {
        absolute_red_line_count: 0,
        capability_ceiling_count: 7,
        q1_to_q7_snapshot: {
          q1: {},
          q2: {},
          q3: {},
          q4: {},
          q5: {},
          q6: {},
          q7: {},
        },
      },
      runtime_state: {
        persistent_task_state: [],
        cognitive_agenda: [],
      },
    } as any);
    vi.mocked(api.fetchNineQuestionInference).mockResolvedValue({} as any);
    vi.mocked(api.fetchNineQuestionTracePayload).mockResolvedValue({} as any);
    vi.mocked(api.fetchNineQuestionRaw).mockResolvedValue({
      trace_id: "trace-q8-no-inference",
      tool_id: "nine_questions.q8",
      context_updates: {
        q8_execution_diagnosis: {
          authenticity_status: "partial_failed",
          diagnosis_message: "Q8 inference failed but upstream evidence remains available.",
        },
      },
      llm_trace_payload: {},
    } as any);
    vi.mocked(api.fetchNineQuestionModules).mockResolvedValue({
      status: { status: "partial_failed" },
      modules: {
        q8_decision_projection: {
          status: "failed",
          data: {
            error_code: "q8_execution_failed",
            error_message: "Remote provider timeout or network failure for ollama",
          },
        },
      },
    } as any);

    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q8"]}>
        <Routes>
          <Route path="/console/nine-questions/q8" element={<Q8Detail />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText("Q1-Q7聚合上下文")).toBeInTheDocument();
    });

    expect(screen.getByText("7 个字段")).toBeInTheDocument();
    expect(screen.getByText("7 项")).toBeInTheDocument();
  });

  it("renders V1.0 evidence gates from the real Q8 raw payload without marking missing evidence as complete", async () => {
    vi.mocked(api.fetchNineQuestionSummary).mockResolvedValue({ status: "partial_failed", question_id: "q8" } as any);
    vi.mocked(api.fetchNineQuestionEvidence).mockResolvedValue({
      aggregated_context: {
        absolute_red_line_count: 0,
        capability_ceiling_count: 1,
        q1_to_q7_snapshot: {},
      },
      runtime_state: {
        persistent_task_state: [],
        cognitive_agenda: [],
      },
    } as any);
    vi.mocked(api.fetchNineQuestionInference).mockResolvedValue({
      task_queue: { next_self_tasks: [], blocked_self_tasks: [], proactive_actions: [] },
      objective_profile: { current_primary_objective: "complete V1", current_phase_tasks: [] },
    } as any);
    vi.mocked(api.fetchNineQuestionTracePayload).mockResolvedValue({} as any);
    vi.mocked(api.fetchNineQuestionRaw).mockResolvedValue({
      trace_id: "trace-q8-v1-gates",
      tool_id: "nine_questions.q8",
      context_updates: {
        v1_evidence_gates: {
          production_history: {
            status: "waiting_real_evidence",
            reason: "真实生产历史数据尚未接入",
          },
          phase_m_living_self_model: {
            status: "completed",
            reason: "LivingSelfModel 快照已写入后查询确认",
          },
        },
      },
      llm_trace_payload: {},
    } as any);
    vi.mocked(api.fetchNineQuestionModules).mockResolvedValue({
      status: { status: "partial_failed" },
      modules: {},
    } as any);

    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q8"]}>
        <Routes>
          <Route path="/console/nine-questions/q8" element={<Q8Detail />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("q8-v1-evidence-gates")).toBeInTheDocument();
    });

    expect(screen.getByTestId("q8-v1-gate-production_history")).toHaveTextContent("waiting_real_evidence");
    expect(screen.getByTestId("q8-v1-gate-production_history")).toHaveTextContent("真实生产历史数据尚未接入");
    expect(screen.getByTestId("q8-v1-gate-phase_m_living_self_model")).toHaveTextContent("completed");
    expect(screen.queryByText("V1.0 已完成")).not.toBeInTheDocument();
  });
});
