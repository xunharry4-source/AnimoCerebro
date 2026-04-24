import { render, screen, waitFor, within } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MemoryRouter } from "react-router-dom";

import NineQuestionsWorkflowPage from "./NineQuestionsWorkflowPage";

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

describe("NineQuestionsWorkflowPage", () => {
  beforeEach(() => {
    mockFetch.mockReset();
  });

  it("renders per-question workflow status and diagnosis in the React Flow overview graph", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      text: async () =>
        JSON.stringify({
          generated_at: "2026-04-19T10:10:00Z",
          event_count: 3,
          summary_counts: {
            completed: 0,
            running: 0,
            failed: 1,
            not_started: 1,
          },
          events: [
            {
              entry_id: "evt-3",
              question_id: "q1",
              question_title: "我在哪",
              trace_id: "trace-q1",
              entry_type: "model_provider_failed",
              phase: "llm",
              phase_status: "failed",
              timestamp: "2026-04-19T10:09:00Z",
              source: "plugins.q1",
              message: "大模型调用失败",
              error_message: "provider timeout",
              payload: {},
            },
          ],
          questions: [
            {
              question_id: "q1",
              question_title: "我在哪",
              current_status: "failed",
              authenticity_status: "partial_failed",
              used_fallback: true,
              latest_trace_id: "trace-q1",
              last_event_at: "2026-04-19T10:09:00Z",
              latest_error: "provider timeout",
              diagnosis_code: "llm_failed",
              diagnosis_message: "provider timeout",
              trace_count: 1,
              module_runs: [
                {
                  module_id: "dependency_check",
                  status: "completed",
                },
                {
                  module_id: "domain_inference",
                  status: "failed",
                  error_code: "llm_failed",
                  error_message: "provider timeout",
                },
              ],
              plugin_runs: [
                {
                  plugin_id: "sensory_environment",
                  feature_code: "q1.sensory",
                  expected: true,
                  attempted: true,
                  status: "completed",
                },
              ],
              upstream_dependencies: [
                {
                  dependency_id: "environment_service",
                  required: true,
                  status: "completed",
                  message: "environment_service completed",
                },
              ],
              recovery_plan: {
                question_id: "q1",
                retriable: true,
                rollback_available: false,
                partial_retry_available: false,
                partial_replace_available: false,
                actions: [
                  {
                    action_id: "q1-rerun-question",
                    label: "重跑 Q1",
                    kind: "retry",
                    executable: true,
                    scope: "question_downstream",
                    target: "q1",
                    reason: "rerun q1",
                  },
                ],
              },
              phase_statuses: [
                {
                  phase: "plugin_execution",
                  status: "completed",
                  updated_at: "2026-04-19T10:08:00Z",
                  message: "九问插件执行完成",
                  error_message: "",
                },
                {
                  phase: "llm",
                  status: "failed",
                  updated_at: "2026-04-19T10:09:00Z",
                  message: "大模型调用失败",
                  error_message: "provider timeout",
                },
              ],
              events: [
                {
                  entry_id: "evt-1",
                  question_id: "q1",
                  question_title: "我在哪",
                  trace_id: "trace-q1",
                  entry_type: "plugin_audit_event",
                  phase: "plugin_execution",
                  phase_status: "completed",
                  timestamp: "2026-04-19T10:08:00Z",
                  source: "kernel",
                  message: "九问插件执行完成",
                  error_message: "",
                  payload: {},
                },
                {
                  entry_id: "evt-3",
                  question_id: "q1",
                  question_title: "我在哪",
                  trace_id: "trace-q1",
                  entry_type: "model_provider_failed",
                  phase: "llm",
                  phase_status: "failed",
                  timestamp: "2026-04-19T10:09:00Z",
                  source: "plugins.q1",
                  message: "大模型调用失败",
                  error_message: "provider timeout",
                  payload: {},
                },
              ],
            },
            {
              question_id: "q2",
              question_title: "我是谁",
              current_status: "not_started",
              latest_trace_id: "",
              last_event_at: "",
              latest_error: "",
              diagnosis_code: "not_started",
              diagnosis_message: "当前问题还没有进入真实执行链。",
              trace_count: 0,
              phase_statuses: [],
              events: [],
            },
          ],
        }),
    } as Response);

    render(
      <MemoryRouter>
        <NineQuestionsWorkflowPage />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("nine-questions-workflow-page")).toBeInTheDocument();
    });

    expect(screen.getByText("九问工作流总览")).toBeInTheDocument();
    expect(screen.getByText("监控事件数: 3")).toBeInTheDocument();
    expect(screen.getByText(/该页面是九问执行链的监控视图/)).toBeInTheDocument();
    expect(screen.queryByText(/Session:/)).not.toBeInTheDocument();
    expect(screen.getByTestId("workflow-overview-canvas")).toBeInTheDocument();
    expect(screen.getByText("监控页只读视图")).toBeInTheDocument();

    const q1Card = screen.getByTestId("workflow-question-q1");
    expect(within(q1Card).getByTestId("workflow-status-q1")).toHaveTextContent("失败");
    expect(within(q1Card).getByTestId("workflow-diagnosis-q1")).toHaveTextContent("大模型失败");
    expect(within(q1Card).getByTestId("workflow-authenticity-q1")).toHaveTextContent("真实性: 部分失败");
    expect(within(q1Card).getByText("使用了 fallback")).toBeInTheDocument();
    expect(within(q1Card).getByText("error: provider timeout")).toBeInTheDocument();
    expect(within(q1Card).getByText("进入工作流").closest("a")).toHaveAttribute("href", "/console/nine-questions/q1/workflow");

    const q2Card = screen.getByTestId("workflow-question-q2");
    expect(within(q2Card).getByTestId("workflow-status-q2")).toHaveTextContent("未开始");
    expect(within(q2Card).getByTestId("workflow-diagnosis-q2")).toHaveTextContent("未开始");
    expect(within(q2Card).getByText("未使用 fallback")).toBeInTheDocument();

    expect(screen.getByText("失败: 1")).toBeInTheDocument();
    expect(screen.getByText("未开始: 1")).toBeInTheDocument();
  });
});
