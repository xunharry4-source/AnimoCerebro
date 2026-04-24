import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import Q1Detail from "./q1/Q1Detail";
import Q2Detail from "./q2/Q2Detail";
import Q3Detail from "./q3/Q3Detail";
import Q4Detail from "./q4/Q4Detail";
import Q5Detail from "./q5/Q5Detail";
import Q6Detail from "./q6/Q6Detail";
import Q7Detail from "./q7/Q7Detail";
import Q8Detail from "./q8/Q8Detail";
import Q9Detail from "./q9/Q9Detail";

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

describe("Nine-question incomplete snapshots", () => {
  beforeEach(() => {
    mockFetch.mockReset();
  });

  it("keeps Q1 detail usable when evidence exists but inference is missing", async () => {
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
    expect(screen.queryByText(/Q1 返回了不完整结果/)).not.toBeInTheDocument();
    expect(screen.getByText(/Q1 实际数据详情/)).toBeInTheDocument();
    expect(screen.getAllByText(/工作区领域归类/).length).toBeGreaterThan(0);
    expect(screen.getByText(/❌ 未完成/)).toBeInTheDocument();
    expect(screen.getByText("nineQuestions.q1.structuredEvidence")).toBeInTheDocument();
  });

  it("keeps Q2 detail usable when evidence exists but inference is missing", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      text: async () =>
        JSON.stringify({
          question_id: "q2",
          title: "我是谁",
          tool_id: "nine_questions.q2",
          summary: "raw snapshot only",
          confidence: 0.3,
          trace_id: "trace-q2-incomplete",
          timestamp: "2026-04-16T10:00:00Z",
          cache_status: "已缓存",
          provider_name: "provider-tools-default",
          preprocessed_evidence: {
            q1_context: {},
            identity_inputs: {},
            role_constraints: {},
          },
          inference_result: null,
          result: { error: "missing_identity_inference" },
          context_updates: { error: "missing_identity_inference" },
        }),
    } as Response);

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
    expect(screen.queryByText(/Q2 返回了不完整结果/)).not.toBeInTheDocument();
    expect(screen.getByText(/Q2 实际数据详情/)).toBeInTheDocument();
    expect(screen.getAllByText(/身份内核与使命连续性证明/).length).toBeGreaterThan(0);
  });

  it("keeps Q9 detail usable when evidence exists but inference is missing", async () => {
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
    expect(screen.queryByText(/Q9 返回了不完整结果/)).not.toBeInTheDocument();
    expect(screen.getByText(/Q9 实际数据详情/)).toBeInTheDocument();
    expect(screen.getAllByText(/行动姿态定调/).length).toBeGreaterThan(0);
    expect(screen.getByText(/❌ 未定调/)).toBeInTheDocument();
    expect(screen.getByText(/结构化行动姿态证据/)).toBeInTheDocument();
  });

  it("keeps Q3-Q8 detail pages usable when only sparse evidence exists", async () => {
    const sparsePayloads = [
      {
        path: "/console/nine-questions/q3",
        testId: "q3-detail-root",
        emptyAlert: /Q3 返回了不完整结果/,
        visibleText: /Q3 实际数据详情/,
        element: <Q3Detail />,
        body: {
          question_id: "q3",
          title: "我有什么",
          tool_id: "nine_questions.q3",
          summary: "raw snapshot only",
          confidence: 0.1,
          trace_id: "trace-q3-incomplete",
          timestamp: "2026-04-16T10:00:00Z",
          cache_status: "已缓存",
          provider_name: "provider-tools-default",
          preprocessed_evidence: {
            workspace_permission: {},
            tools_agents: {},
            memory_strategy: {},
          },
          inference_result: null,
        },
      },
      {
        path: "/console/nine-questions/q4",
        testId: "q4-detail-root",
        emptyAlert: /Q4 返回了不完整结果/,
        visibleText: /结构化能力边界证据/,
        element: <Q4Detail />,
        body: {
          question_id: "q4",
          title: "我能做什么",
          tool_id: "nine_questions.q4",
          summary: "raw snapshot only",
          confidence: 0.1,
          trace_id: "q4:no-trace",
          timestamp: "2026-04-16T10:00:00Z",
          cache_status: "已缓存",
          provider_name: "provider-tools-default",
          preprocessed_evidence: {
            q1_context: {},
            q2_context: {},
            q3_inventory: {},
          },
          inference_result: null,
        },
      },
      {
        path: "/console/nine-questions/q5",
        testId: "q5-detail-root",
        emptyAlert: /Q5 返回了不完整结果/,
        visibleText: /Q5 实际数据详情/,
        element: <Q5Detail />,
        body: {
          question_id: "q5",
          title: "我被允许做什么",
          tool_id: "nine_questions.q5",
          summary: "raw snapshot only",
          confidence: 0.1,
          trace_id: "trace-q5-incomplete",
          timestamp: "2026-04-16T10:00:00Z",
          cache_status: "已缓存",
          provider_name: "provider-tools-default",
          preprocessed_evidence: {},
          inference_result: null,
        },
      },
      {
        path: "/console/nine-questions/q6",
        testId: "q6-detail-root",
        emptyAlert: /Q6 返回了不完整结果/,
        visibleText: /Q6 实际数据详情/,
        element: <Q6Detail />,
        body: {
          question_id: "q6",
          title: "我不该做什么",
          tool_id: "nine_questions.q6",
          summary: "raw snapshot only",
          confidence: 0.1,
          trace_id: "trace-q6-incomplete",
          timestamp: "2026-04-16T10:00:00Z",
          cache_status: "已缓存",
          provider_name: "provider-tools-default",
          preprocessed_evidence: {},
          inference_result: null,
        },
      },
      {
        path: "/console/nine-questions/q7",
        testId: "q7-detail-root",
        emptyAlert: /Q7 返回了不完整结果/,
        visibleText: /Q7 实际数据详情/,
        element: <Q7Detail />,
        body: {
          question_id: "q7",
          title: "我还可以做什么",
          tool_id: "nine_questions.q7",
          summary: "raw snapshot only",
          confidence: 0.1,
          trace_id: "trace-q7-incomplete",
          timestamp: "2026-04-16T10:00:00Z",
          cache_status: "已缓存",
          provider_name: "provider-tools-default",
          preprocessed_evidence: {},
          inference_result: null,
        },
      },
      {
        path: "/console/nine-questions/q8",
        testId: "q8-detail-root",
        emptyAlert: /Q8 返回了不完整结果/,
        visibleText: /Q8 实际数据详情/,
        element: <Q8Detail />,
        body: {
          question_id: "q8",
          title: "我现在该做什么",
          tool_id: "nine_questions.q8",
          summary: "raw snapshot only",
          confidence: 0.1,
          trace_id: "trace-q8-incomplete",
          timestamp: "2026-04-16T10:00:00Z",
          cache_status: "已缓存",
          provider_name: "provider-tools-default",
          preprocessed_evidence: {
            aggregated_context: {},
            runtime_state: {},
          },
          inference_result: null,
        },
      },
    ];

    for (const item of sparsePayloads) {
      cleanup();
      window.localStorage.removeItem?.("currentWorkspaceId");
      mockFetch.mockReset();
      if (item.body.question_id === "q3" || item.body.question_id === "q4" || item.body.question_id === "q5" || item.body.question_id === "q6" || item.body.question_id === "q7" || item.body.question_id === "q8") {
        mockFetch.mockImplementation(async (input: RequestInfo | URL) => {
          const url = String(input);
          const basePayload = item.body as Record<string, any>;
          const sectionPayloads: Record<string, any> = {
            summary: {
              question_id: basePayload.question_id,
              summary: basePayload.summary,
              confidence: basePayload.confidence,
              status: "partial",
              timestamp: basePayload.timestamp,
            },
            evidence: basePayload.preprocessed_evidence,
            inference: basePayload.inference_result,
            trace: {},
            raw: {
              question_id: basePayload.question_id,
              tool_id: basePayload.tool_id,
              trace_id: basePayload.trace_id,
              timestamp: basePayload.timestamp,
              result: basePayload.result ?? {},
              context_updates: basePayload.context_updates ?? {},
              llm_trace_payload: {},
            },
            modules: {
              question_id: basePayload.question_id,
              status: { status: "partial", module_statuses: {} },
              modules: {},
            },
          };
          const section = Object.keys(sectionPayloads).find((key) => url.endsWith(`/${key}`));
          const payload = section ? sectionPayloads[section] : basePayload;
          return {
            ok: true,
            text: async () => JSON.stringify(payload),
          } as Response;
        });
      } else {
        mockFetch.mockResolvedValue({
          ok: true,
          text: async () => JSON.stringify(item.body),
        } as Response);
      }

      render(
        <MemoryRouter initialEntries={[item.path]}>
          <Routes>
            <Route path={item.path} element={item.element} />
          </Routes>
        </MemoryRouter>,
      );

      await waitFor(() => {
        expect(screen.getByTestId(item.testId)).toBeInTheDocument();
      });
      expect(screen.queryByText(item.emptyAlert)).not.toBeInTheDocument();
      expect(screen.getByText(item.visibleText)).toBeInTheDocument();
    }
  });
});
