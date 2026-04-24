import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import Q1Detail from "./Q1Detail";
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
  };
});

describe("Q1Detail functional tests", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("keeps the Q1 page layout available when inference and evidence sections fail but base partitions load", async () => {
    vi.mocked(api.fetchNineQuestionDetail).mockRejectedValue(new Error("legacy detail endpoint should not be used"));
    vi.mocked(api.fetchNineQuestionSummary).mockResolvedValue({
      status: "partial_failed",
      question_id: "q1",
    } as any);
    vi.mocked(api.fetchNineQuestionRaw).mockResolvedValue({
      trace_id: "trace-q1-functional",
      tool_id: "nine_questions.q1",
      llm_trace_payload: {
        provider_name: "provider-tools-default",
        elapsed_ms: 42,
      },
    } as any);
    vi.mocked(api.fetchNineQuestionModules).mockResolvedValue({
      status: {
        status: "partial_failed",
        error_message: "Inference stage failed",
        source_summary: {
          physical_and_environment: "runtime_telemetry",
          workspace_structure: "workspace_structure_analysis",
          workspace_content_sampling: "workspace_content_samples",
          domain_inference: "unavailable_due_to_failure",
          reused_previous_success: false,
          display_origin_explanation: "当前页面只展示本次仍可确认的 Q1 证据；未沿用旧结果，本次推断结论不可用。",
        },
      },
      modules: {
        domain_inference: {
          status: "failed",
          error: "Inference stage failed",
        },
      },
    } as any);
    vi.mocked(api.fetchNineQuestionEvidence).mockRejectedValue(new Error("Q1 evidence unavailable"));
    vi.mocked(api.fetchNineQuestionInference).mockRejectedValue(new Error("Q1 inference unavailable"));
    vi.mocked(api.fetchNineQuestionTracePayload).mockRejectedValue(new Error("Q1 trace unavailable"));

    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q1"]}>
        <Routes>
          <Route path="/console/nine-questions/q1" element={<Q1Detail />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("q1-detail-root")).toBeInTheDocument();
    });

    expect(api.fetchNineQuestionSummary).toHaveBeenCalledWith("q1");
    expect(api.fetchNineQuestionRaw).toHaveBeenCalledWith("q1");
    expect(api.fetchNineQuestionModules).toHaveBeenCalledWith("q1");
    expect(screen.getByTestId("q1-status-guidance")).toHaveTextContent("Q1 本次推演部分失败");
    expect(screen.getByTestId("q1-source-guidance")).toHaveTextContent("未沿用旧结果");
    expect(screen.getByTestId("q1-source-guidance")).toHaveTextContent("inference: unavailable_due_to_failure");
    expect(screen.getByTestId("q1-failed-modules-alert")).toHaveTextContent("domain inference: Inference stage failed");
    expect(screen.getByText(/Q1 当前只拿到了部分分区数据/)).toBeInTheDocument();
    expect(screen.getByText(/Q1 数据详情/)).toBeInTheDocument();
    expect(screen.getByText(/Q1 结构化证据/)).toBeInTheDocument();
    expect(screen.getByText(/Q1 evidence unavailable/)).toBeInTheDocument();
    expect(screen.getByText(/Q1 inference unavailable/)).toBeInTheDocument();
  });

  it("explains stale Q1 records as hidden half-written results instead of pretending they are normal data", async () => {
    vi.mocked(api.fetchNineQuestionDetail).mockRejectedValue(new Error("legacy detail endpoint should not be used"));
    vi.mocked(api.fetchNineQuestionSummary).mockResolvedValue({
      status: "stale",
      question_id: "q1",
    } as any);
    vi.mocked(api.fetchNineQuestionRaw).mockResolvedValue({
      trace_id: "trace-q1-stale",
      tool_id: "nine_questions.q1",
    } as any);
    vi.mocked(api.fetchNineQuestionModules).mockResolvedValue({
      status: { status: "stale", error_message: "question record is not committed" },
    } as any);
    vi.mocked(api.fetchNineQuestionEvidence).mockResolvedValue({} as any);
    vi.mocked(api.fetchNineQuestionInference).mockResolvedValue({} as any);
    vi.mocked(api.fetchNineQuestionTracePayload).mockResolvedValue({} as any);

    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q1"]}>
        <Routes>
          <Route path="/console/nine-questions/q1" element={<Q1Detail />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("q1-detail-root")).toBeInTheDocument();
    });

    expect(screen.getByTestId("q1-status-guidance")).toHaveTextContent("Q1 结果未提交完成");
    expect(screen.getByTestId("q1-status-guidance")).toHaveTextContent("question record is not committed");
  });

  it("shows reused previous Q1 inference together with current failure explanation", async () => {
    vi.mocked(api.fetchNineQuestionDetail).mockRejectedValue(new Error("legacy detail endpoint should not be used"));
    vi.mocked(api.fetchNineQuestionSummary).mockResolvedValue({
      status: "partial_failed",
      question_id: "q1",
    } as any);
    vi.mocked(api.fetchNineQuestionRaw).mockResolvedValue({
      trace_id: "trace-q1-reused",
      tool_id: "nine_questions.q1",
    } as any);
    vi.mocked(api.fetchNineQuestionModules).mockResolvedValue({
      status: {
        status: "partial_failed",
        error_message: "Inference stage failed",
        source_summary: {
          physical_and_environment: "runtime_telemetry",
          workspace_structure: "workspace_structure_analysis",
          workspace_content_sampling: "workspace_content_samples",
          domain_inference: "previous_committed_success",
          reused_previous_success: true,
          display_origin_explanation: "当前页面沿用上一份 Q1 成功推断结果；本次推断失败，但环境证据仍来自本次快照。",
        },
      },
      modules: {
        domain_inference: {
          status: "stale",
          error: "Inference stage failed",
          data: {
            primary_domain: "production_server",
          },
        },
      },
    } as any);
    vi.mocked(api.fetchNineQuestionEvidence).mockResolvedValue({
      physical_and_environment: {
        environment_event: {},
        physical_host_state: { hostname: "prod-host" },
        memory_pressure_status: "healthy",
        network_health_status: "healthy",
        environment_summary: ["hostname=prod-host"],
      },
      workspace_structure: {
        top_level_dirs: ["src"],
        suffix_distribution: { ".py": 8 },
        high_frequency_filename_keywords: { test: 1 },
        candidate_groups: ["python_backend"],
        obvious_risk_files: [],
        directory_tree_rows: [],
        candidate_group_details: [],
        obvious_risk_file_details: [],
        analyzer_snapshot: {},
      },
      workspace_content_sampling: {
        sampled_file_summaries: [],
        log_anomaly_snippets: [],
        long_text_evidence: [],
        sample_count: 0,
        anomaly_count: 0,
        sampler_snapshot: {},
      },
    } as any);
    vi.mocked(api.fetchNineQuestionInference).mockResolvedValue({
      primary_domain: "production_server",
      secondary_domains: ["api_gateway"],
      confidence: 0.91,
      reasoning_summary: "Previous successful inference.",
      uncertainties: ["Cloud metadata unavailable"],
      suggested_first_step: "Verify ingress",
    } as any);
    vi.mocked(api.fetchNineQuestionTracePayload).mockResolvedValue({} as any);

    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q1"]}>
        <Routes>
          <Route path="/console/nine-questions/q1" element={<Q1Detail />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("q1-detail-root")).toBeInTheDocument();
    });

    expect(screen.getByTestId("q1-status-guidance")).toHaveTextContent("Q1 本次推演部分失败");
    expect(screen.getByTestId("q1-source-guidance")).toHaveTextContent("沿用上一份 Q1 成功推断结果");
    expect(screen.getByTestId("q1-source-guidance")).toHaveTextContent("inference: previous_committed_success");
    expect(screen.getByTestId("q1-primary-domain-chip")).toHaveTextContent("production_server");
  });

  it("keeps workflow access in a dedicated page instead of rendering the internal workflow inline", async () => {
    vi.mocked(api.fetchNineQuestionDetail).mockRejectedValue(new Error("legacy detail endpoint should not be used"));
    vi.mocked(api.fetchNineQuestionSummary).mockResolvedValue({
      status: "degraded",
      question_id: "q1",
    } as any);
    vi.mocked(api.fetchNineQuestionEvidence).mockResolvedValue({
      physical_and_environment: {
        environment_event: { summary: "Observed local workspace signal" },
        physical_host_state: { hostname: "devbox" },
        memory_pressure_status: "healthy",
        network_health_status: "healthy",
        environment_summary: ["hostname=devbox"],
      },
      workspace_structure: {
        top_level_dirs: ["src", "docs"],
        suffix_distribution: { ".py": 8, ".md": 2 },
        high_frequency_filename_keywords: { test: 1 },
        candidate_groups: ["python_backend"],
        obvious_risk_files: [],
        directory_tree_rows: [],
        candidate_group_details: [],
        obvious_risk_file_details: [],
        analyzer_snapshot: {},
      },
      workspace_content_sampling: {
        sampled_file_summaries: [{ path: "src/app.py", summary: "main service entry" }],
        log_anomaly_snippets: ["ERROR database disconnected"],
        long_text_evidence: [],
        sample_count: 1,
        anomaly_count: 1,
        sampler_snapshot: {},
      },
    } as any);
    vi.mocked(api.fetchNineQuestionInference).mockResolvedValue({
      primary_domain: "backend_development",
      secondary_domains: ["api_design"],
      confidence: 0.87,
      reasoning_summary: "Workspace looks like a backend project.",
      uncertainties: ["deployment target unclear"],
      suggested_first_step: "Inspect src/app.py",
    } as any);
    vi.mocked(api.fetchNineQuestionTracePayload).mockResolvedValue({} as any);
    vi.mocked(api.fetchNineQuestionRaw).mockResolvedValue({
      trace_id: "trace-q1-workflow",
      tool_id: "nine_questions.q1",
      context_updates: {
        q1_execution_diagnosis: {
          functional_chain_status: "partial",
          environment_service_status: "completed",
          snapshot_fallback_used: true,
          overall_authenticity: "degraded_chain_incomplete",
          plugin_runs: [
            {
              plugin_id: "sensory_webhook",
              status: "completed",
              output_summary: "raw_signal len=32",
            },
            {
              plugin_id: "sensory_environment",
              status: "failed",
              error_message: "get_environment_awareness missing",
            },
          ],
        },
      },
    } as any);
    vi.mocked(api.fetchNineQuestionModules).mockResolvedValue({
      status: { status: "degraded" },
      modules: {
        dependency_check: { status: "ready", data: { enabled_functional_plugins: 4 } },
        functional_plugin_chain: {
          status: "degraded",
          data: {
            status: "partial",
            plugin_runs: [
              {
                plugin_id: "sensory_webhook",
                status: "completed",
                output_summary: "raw_signal len=32",
              },
            ],
          },
        },
        environment_service: { status: "ready", data: { status: "completed" } },
        environment_scan: { status: "ready", data: { environment_summary: ["hostname=devbox"] } },
        workspace_structure_scan: { status: "ready", data: { top_level_dirs: ["src", "docs"] } },
        content_sampling: { status: "ready", data: { sample_count: 1, anomaly_count: 1 } },
        domain_inference: { status: "ready", data: { primary_domain: "backend_development", confidence: 0.87 } },
        state_write: { status: "degraded", data: { overall_authenticity: "degraded_chain_incomplete" } },
      },
    } as any);

    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q1"]}>
        <Routes>
          <Route path="/console/nine-questions/q1" element={<Q1Detail />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("q1-workflow-nav-button")).toBeInTheDocument();
    });

    expect(screen.getByTestId("q1-workflow-nav-button")).toHaveAttribute("href", "/console/nine-questions/q1/workflow");
    expect(screen.queryByTestId("q1-workflow-panel")).not.toBeInTheDocument();
    expect(screen.queryByText("Q1 内部工作流")).not.toBeInTheDocument();
  });

  it("renders downstream integration modules from committed module outputs", async () => {
    vi.mocked(api.fetchNineQuestionSummary).mockResolvedValue({ status: "completed", question_id: "q1" } as any);
    vi.mocked(api.fetchNineQuestionEvidence).mockResolvedValue({} as any);
    vi.mocked(api.fetchNineQuestionInference).mockResolvedValue({} as any);
    vi.mocked(api.fetchNineQuestionTracePayload).mockResolvedValue({} as any);
    vi.mocked(api.fetchNineQuestionRaw).mockResolvedValue({
      trace_id: "trace-q1-integrations",
      tool_id: "nine_questions.q1",
      context_updates: {},
      llm_trace_payload: {},
      mounted_plugins: [],
    } as any);
    vi.mocked(api.fetchNineQuestionModules).mockResolvedValue({
      status: { status: "completed" },
      modules: {
        q1_audit_integration: { status: "completed", data: { module_kind: "audit", summary: "audit recorded" } },
        q1_memory_integration: { status: "completed", data: { module_kind: "memory", summary: "memory recorded" } },
        q1_reflection_integration: { status: "completed", data: { module_kind: "reflection", summary: "reflection recorded" } },
        q1_learning_integration: { status: "completed", data: { module_kind: "learning", summary: "learning recorded" } },
      },
    } as any);

    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q1"]}>
        <Routes>
          <Route path="/console/nine-questions/q1" element={<Q1Detail />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("q1-integration-audit")).toBeInTheDocument();
    });

    expect(screen.getByTestId("q1-integration-row-q1_audit_integration")).toHaveTextContent("audit recorded");
    expect(screen.getByTestId("q1-integration-row-q1_memory_integration")).toHaveTextContent("memory");
    expect(screen.getByTestId("q1-integration-row-q1_reflection_integration")).toHaveTextContent("reflection recorded");
    expect(screen.getByTestId("q1-integration-row-q1_learning_integration")).toHaveTextContent("learning");
  });
});
