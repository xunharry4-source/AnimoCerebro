import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import Q1Detail from "./q1/Q1Detail";
import Q9Detail from "./q9/Q9Detail";

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

describe("Nine-question incomplete snapshots", () => {
  beforeEach(() => {
    mockFetch.mockReset();
  });

  it("renders a fallback instead of crashing when q1 has evidence but no inference", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      text: async () =>
        JSON.stringify({
          question_id: "q1",
          title: "我在哪",
          tool_id: "nine_questions.q1",
          summary: "raw snapshot only",
          confidence: 0.3,
          trace_id: "trace-q1-incomplete",
          timestamp: "2026-04-16T10:00:00Z",
          cache_status: "已缓存",
          provider_name: "provider-tools-default",
          preprocessed_evidence: {
            physical_and_environment: {
              environment_event: {},
              physical_host_state: {},
              memory_pressure_status: "unknown",
              network_health_status: "unknown",
              environment_summary: [],
            },
            workspace_structure: {
              top_level_dirs: [],
              suffix_distribution: {},
              high_frequency_filename_keywords: {},
              candidate_groups: [],
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
          },
          inference_result: null,
          result: { error: "missing_inference" },
          context_updates: { error: "missing_inference" },
        }),
    } as Response);

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
    expect(screen.getByText(/Q1 返回了不完整结果/)).toBeInTheDocument();
    expect(screen.getAllByText(/missing_inference/)).toHaveLength(2);
    expect(screen.getByText(/后端 `result`/)).toBeInTheDocument();
    expect(screen.getByText(/后端 `context_updates`/)).toBeInTheDocument();
  });

  it("renders a fallback instead of crashing when q9 has evidence but no inference", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      text: async () =>
        JSON.stringify({
          question_id: "q9",
          title: "我应该如何行动",
          tool_id: "nine_questions.q9",
          summary: "raw snapshot only",
          confidence: 0.2,
          trace_id: "trace-q9-incomplete",
          timestamp: "2026-04-16T10:00:00Z",
          cache_status: "已缓存",
          provider_name: "provider-tools-default",
          preprocessed_evidence: {
            cognitive_snapshot: {
              q1_to_q8_snapshot: {},
              uncertainty_count: 1,
              absolute_red_line_count: 2,
            },
            self_model: {
              cognitive_load: "high",
              stability_level: "unstable",
              confidence_drift: 0.4,
              recent_weaknesses: [],
            },
            reasoning_budget: {
              compute_remaining_ratio: 0.2,
              token_remaining_ratio: 0.1,
              time_remaining_ratio: 0.3,
              budget_pressure: "critical",
            },
          },
          inference_result: null,
          result: { error: "missing_posture" },
          context_updates: { error: "missing_posture" },
        }),
    } as Response);

    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q9"]}>
        <Routes>
          <Route path="/console/nine-questions/q9" element={<Q9Detail />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("q9-detail-root")).toBeInTheDocument();
    });
    expect(screen.getByText(/Q9 返回了不完整结果/)).toBeInTheDocument();
    expect(screen.getAllByText(/missing_posture/)).toHaveLength(2);
    expect(screen.getByText(/后端 `result`/)).toBeInTheDocument();
    expect(screen.getByText(/后端 `context_updates`/)).toBeInTheDocument();
  });
});
