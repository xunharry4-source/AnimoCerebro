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

describe("Q1Detail business tests", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows business values from partitioned Q1 results and exposes malformed evidence as warnings instead of crashing", async () => {
    vi.mocked(api.fetchNineQuestionDetail).mockRejectedValue(new Error("legacy detail endpoint should not be used"));
    vi.mocked(api.fetchNineQuestionSummary).mockResolvedValue({
      status: "completed",
      question_id: "q1",
    } as any);
    vi.mocked(api.fetchNineQuestionEvidence).mockResolvedValue({
      physical_and_environment: {
        environment_event: "bad-event-type",
        physical_host_state: 123,
        memory_pressure_status: "healthy",
        network_health_status: "healthy",
        environment_summary: ["hostname=prod-q1"],
      },
      workspace_structure: {
        top_level_dirs: ["src", "docs"],
        suffix_distribution: { ".ts": 12 },
        high_frequency_filename_keywords: { service: 3 },
        candidate_groups: ["typescript_backend"],
        obvious_risk_files: [],
        directory_tree_rows: [],
        candidate_group_details: [],
        obvious_risk_file_details: [],
        analyzer_snapshot: "bad-snapshot-type",
      },
      workspace_content_sampling: {
        sampled_file_summaries: [],
        log_anomaly_snippets: [],
        long_text_evidence: [],
        sample_count: 1,
        anomaly_count: 0,
        sampler_snapshot: [],
      },
    } as any);
    vi.mocked(api.fetchNineQuestionInference).mockResolvedValue({
      primary_domain: "production_server",
      secondary_domains: ["api_gateway"],
      confidence: 0.91,
      reasoning_summary: "Workspace shape matches production server layout.",
      uncertainties: ["Cloud metadata unavailable"],
      suggested_first_step: "Verify ingress and runtime health",
    } as any);
    vi.mocked(api.fetchNineQuestionTracePayload).mockResolvedValue({
      provider_name: "provider-tools-default",
      elapsed_ms: 88,
      token_usage: { input_tokens: 10, output_tokens: 5, total_tokens: 15 },
      context_data: {},
    } as any);
    vi.mocked(api.fetchNineQuestionRaw).mockResolvedValue({
      trace_id: "trace-q1-business",
      tool_id: "nine_questions.q1",
      mounted_plugins: [],
    } as any);
    vi.mocked(api.fetchNineQuestionModules).mockResolvedValue({
      status: { status: "completed" },
    } as any);

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

    expect(screen.getByTestId("q1-primary-domain-chip")).toHaveTextContent("production_server");
    expect(screen.getByText(/✅ 已推断主领域: production_server/)).toBeInTheDocument();
    expect(screen.getAllByText(/Workspace shape matches production server layout/).length).toBeGreaterThan(0);
    expect(screen.getByText(/environment_event 字段类型异常/)).toBeInTheDocument();
    expect(screen.getByText(/physical_host_state 字段类型异常/)).toBeInTheDocument();
    expect(screen.getByText(/Q1 原始字段诊断/)).toBeInTheDocument();
  });
});
