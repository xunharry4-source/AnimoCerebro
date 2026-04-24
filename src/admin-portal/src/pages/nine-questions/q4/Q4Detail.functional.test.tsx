import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import Q4Detail from "./Q4Detail";
import * as api from "../nineQuestionsApi";

vi.mock("../nineQuestionsApi", async () => {
  const actual = await vi.importActual("../nineQuestionsApi");
  return {
    ...actual,
    fetchNineQuestionDetail: vi.fn(),
    fetchNineQuestionEvidence: vi.fn(),
    fetchNineQuestionInference: vi.fn(),
    fetchNineQuestionModules: vi.fn(),
    fetchNineQuestionRaw: vi.fn(),
    fetchNineQuestionSummary: vi.fn(),
    fetchNineQuestionTrace: vi.fn(),
    fetchNineQuestionTracePayload: vi.fn(),
  };
});

describe("Q4Detail functional tests", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders Q4 as a partitioned module audit surface with partial failure recovery evidence", async () => {
    vi.mocked(api.fetchNineQuestionSummary).mockResolvedValue({ status: "partial_failed" });
    vi.mocked(api.fetchNineQuestionEvidence).mockResolvedValue({
      q1_context: { scene_model: { primary_domain: "audit_console" } },
      q2_context: { role_profile: { active_role: "capability_auditor" } },
      q3_inventory: {
        available_cognitive_tools: ["CodeAnalyzer"],
        available_execution_tools: [],
        connected_agents: [],
        active_execution_domains: [],
      },
    });
    vi.mocked(api.fetchNineQuestionInference).mockResolvedValue({
      capability_upper_limits: ["read_workspace_state"],
      actionable_space: [],
      executable_strategies: [],
    });
    vi.mocked(api.fetchNineQuestionTracePayload).mockResolvedValue({
      provider_name: "provider-tools-default",
      elapsed_ms: 88,
      context_data: {},
      token_usage: { input_tokens: 1, output_tokens: 1, total_tokens: 2 },
    });
    vi.mocked(api.fetchNineQuestionModules).mockResolvedValue({
      status: { status: "partial_failed" },
      module_runs: [
        { module_id: "q4_inventory_validation", status: "completed" },
        {
          module_id: "q4_execution_capability_verification",
          status: "degraded",
          error_code: "execution_domains_missing",
          error_message: "No validated execution domains are available.",
        },
      ],
      plugin_runs: [
        {
          plugin_id: "capability-plugin",
          feature_code: "nine_questions.q4",
          status: "failed",
          error_code: "capability_plugin_failed",
        },
      ],
      upstream_dependencies: [
        { dependency_id: "q3", required: true, status: "completed" },
      ],
    });
    vi.mocked(api.fetchNineQuestionRaw).mockResolvedValue({
      question_id: "q4",
      tool_id: "nine_questions.q4",
      trace_id: "trace-q4-partial",
      context_updates: {
        q4_execution_diagnosis: {
          authenticity_status: "degraded",
          diagnosis_message: "Q4 capability boundary completed with degraded execution-domain evidence.",
          used_fallback: true,
          module_runs: [
            { module_id: "q4_inventory_validation", status: "completed" },
            { module_id: "q4_execution_capability_verification", status: "degraded" },
          ],
          plugin_runs: [{ plugin_id: "capability-plugin", status: "failed" }],
          upstream_dependencies: [{ dependency_id: "q3", required: true, status: "completed" }],
          recovery_plan: {
            retriable: true,
            rollback_available: false,
            partial_retry_available: true,
            partial_replace_available: false,
            actions: [
              {
                action_id: "q4-refresh-capability-inputs",
                label: "刷新 Q4 能力输入模块",
                kind: "partial_retry",
                executable: true,
                scope: "module",
                target: "q4_execution_capability_verification",
                path: "/api/web/nine-questions/q4/modules/q4_execution_capability_verification/retry",
              },
            ],
          },
        },
      },
    });

    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q4"]}>
        <Routes>
          <Route path="/console/nine-questions/q4" element={<Q4Detail />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByTestId("q4-detail-root")).toBeInTheDocument();
    expect(api.fetchNineQuestionSummary).toHaveBeenCalledWith("q4");
    expect(api.fetchNineQuestionModules).toHaveBeenCalledWith("q4");
    expect(api.fetchNineQuestionDetail).not.toHaveBeenCalled();
    expect(screen.getByText("Q4 真实性状态：降级/部分失败")).toBeInTheDocument();
    expect(screen.getByText("Q4 当前只拿到了部分分区数据，页面已按可用结果降级展示。")).toBeInTheDocument();
    expect(screen.getByTestId("q4-recovery-plan")).toHaveTextContent("局部重试：是");
    expect(screen.getByTestId("q4-recovery-action-q4-refresh-capability-inputs")).toHaveTextContent(
      "刷新 Q4 能力输入模块 | partial_retry | module | executable | q4_execution_capability_verification",
    );
    expect(screen.getByTestId("q4-module-audit")).toHaveTextContent("模块数：2");
    expect(screen.getByTestId("q4-module-audit")).toHaveTextContent("插件数：1");
    expect(screen.getByTestId("q4-module-audit")).toHaveTextContent("依赖数：1");
    expect(screen.getByText("q4_execution_capability_verification")).toBeInTheDocument();
    expect(screen.getByText("execution_domains_missing")).toBeInTheDocument();
  });

  it("renders Q4 recovery plan from structured execution diagnosis", async () => {
    vi.mocked(api.fetchNineQuestionSummary).mockResolvedValue({ status: "degraded" });
    vi.mocked(api.fetchNineQuestionEvidence).mockResolvedValue({});
    vi.mocked(api.fetchNineQuestionInference).mockResolvedValue(null as any);
    vi.mocked(api.fetchNineQuestionTracePayload).mockResolvedValue({ context_data: {}, token_usage: { input_tokens: 0, output_tokens: 0, total_tokens: 0 } });
    vi.mocked(api.fetchNineQuestionModules).mockResolvedValue({ status: { status: "degraded" }, module_runs: [], plugin_runs: [], upstream_dependencies: [] });
    vi.mocked(api.fetchNineQuestionRaw).mockResolvedValue({
      question_id: "q4",
      title: "我能做什么",
      tool_id: "nine_questions.q4",
      summary: "q4 summary",
      confidence: 0.9,
      trace_id: "trace-q4-recovery",
      cache_status: "已就绪",
      provider_name: "provider-tools-default",
      mounted_plugins: [],
      preprocessed_evidence: null,
      inference_result: null,
      llm_trace_payload: {},
      result: { error: "missing execution domains" },
      context_updates: {
        q4_execution_diagnosis: {
          authenticity_status: "degraded",
          diagnosis_message: "Q4 capability boundary completed with degraded asset or execution-domain evidence.",
          recovery_plan: {
            retriable: true,
            rollback_available: false,
            partial_retry_available: true,
            partial_replace_available: false,
            actions: [
              {
                action_id: "q4-rerun-question",
                label: "重跑 Q4 及下游",
                kind: "retry",
                executable: true,
                scope: "question_downstream",
                target: "q4",
              },
            ],
          },
        },
      },
    } as any);

    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q4"]}>
        <Routes>
          <Route path="/console/nine-questions/q4" element={<Q4Detail />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("q4-recovery-plan")).toBeInTheDocument();
    });

    expect(screen.getByTestId("q4-recovery-plan")).toHaveTextContent("可重试：是");
    expect(screen.getByTestId("q4-recovery-action-q4-rerun-question")).toHaveTextContent(
      "重跑 Q4 及下游 | retry | question_downstream | executable | q4",
    );
  });

  it("renders downstream integration modules from committed module outputs", async () => {
    vi.mocked(api.fetchNineQuestionSummary).mockResolvedValue({ status: "completed" } as any);
    vi.mocked(api.fetchNineQuestionEvidence).mockResolvedValue({} as any);
    vi.mocked(api.fetchNineQuestionInference).mockResolvedValue({} as any);
    vi.mocked(api.fetchNineQuestionTracePayload).mockResolvedValue({
      context_data: {},
      token_usage: { input_tokens: 0, output_tokens: 0, total_tokens: 0 },
    } as any);
    vi.mocked(api.fetchNineQuestionRaw).mockResolvedValue({
      trace_id: "trace-q4-integrations",
      tool_id: "nine_questions.q4",
      context_updates: {},
      llm_trace_payload: {},
      mounted_plugins: [],
    } as any);
    vi.mocked(api.fetchNineQuestionModules).mockResolvedValue({
      status: { status: "completed" },
      modules: {
        q4_audit_integration: { status: "completed", data: { module_kind: "audit", summary: "audit recorded" } },
        q4_memory_integration: { status: "completed", data: { module_kind: "memory", summary: "memory recorded" } },
        q4_reflection_integration: { status: "completed", data: { module_kind: "reflection", summary: "reflection recorded" } },
        q4_learning_integration: { status: "completed", data: { module_kind: "learning", summary: "learning recorded" } },
      },
      module_runs: [],
      plugin_runs: [],
      upstream_dependencies: [],
    } as any);

    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q4"]}>
        <Routes>
          <Route path="/console/nine-questions/q4" element={<Q4Detail />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("q4-integration-audit")).toBeInTheDocument();
    });

    expect(screen.getByTestId("q4-integration-row-q4_audit_integration")).toHaveTextContent("audit recorded");
    expect(screen.getByTestId("q4-integration-row-q4_memory_integration")).toHaveTextContent("memory");
    expect(screen.getByTestId("q4-integration-row-q4_reflection_integration")).toHaveTextContent("reflection recorded");
    expect(screen.getByTestId("q4-integration-row-q4_learning_integration")).toHaveTextContent("learning");
  });
});
