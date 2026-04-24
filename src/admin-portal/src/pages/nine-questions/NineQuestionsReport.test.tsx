import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import NineQuestionsReport from "./NineQuestionsReport";
import NineQuestionDetailPage from "./NineQuestionDetailPage";
import NineQuestionSandboxPage from "./NineQuestionSandboxPage";

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

const mockQ1PreprocessedEvidence = {
  physical_and_environment: {
    environment_event: { kind: "production_run", summary: "runtime snapshot" },
    physical_host_state: { memory_pressure: "high", network_health: "degraded" },
    memory_pressure: "high",
    network_health: "degraded",
    memory_pressure_status: "high",
    network_health_status: "degrade",
    environment_summary: ["cwd=/workspace", "environment_kind=production_run"],
  },
  workspace_structure: {
    directory_hierarchy_summary: "src/, logs/, data/",
    top_level_dirs: ["src", "logs", "data"],
    file_total_count: 42,
    suffix_distribution: { ".py": 10, ".md": 3, ".log": 2 },
    high_frequency_filename_keywords: { invoice: 2, api: 4 },
    candidate_groups: ["python_code", "logs"],
    obvious_risk_files: ["data/invoices.csv"],
    directory_tree_rows: [{ row_id: "dir-top-0", path: "src", label: "src", depth: 0, kind: "directory" }],
    candidate_group_details: [{ group_id: "group-0", label: "python_code", file_count: 10, summary: "core code" }],
    obvious_risk_file_details: [{ path: "data/invoices.csv", severity: "high", reason: "sensitive data" }],
    analyzer_snapshot: {},
  },
  workspace_content_sampling: {
    sampled_file_summaries: [{ path: "logs/app.log", summary: "长日志样本", snippet: "ERROR sandbox validation failed on line 1" }],
    log_anomaly_snippets: ["ERROR sandbox validation failed on line 1"],
    long_text_evidence: [
      {
        evidence_id: "sample-0-snippet",
        label: "logs/app.log · 样本行",
        kind: "snippet",
        source: "workspace_content_sampler",
        path: "logs/app.log",
        text: "ERROR sandbox validation failed on line 1",
      },
    ],
    sample_count: 1,
    anomaly_count: 1,
    sampler_snapshot: {},
  },
};

const mockReport = {
  status: "ready",
  status_message: null,
  last_turn_id: "turn-9",
  snapshot_version: 9,
  revision: 9,
  refreshed_at: "2026-04-04T12:00:00Z",
  last_refresh_reason: "test_seed",
  question_driver_refs: ["seed:web-console"],
  questions: [
    {
      question_id: "q1",
      title: "我在哪",
      tool_id: "nine_questions.q1",
      summary: "当前运行域是本地 Web Console 验收环境。",
      confidence: 0.93,
      trace_id: "trace-q1-111",
      timestamp: "2026-04-04T12:00:00Z",
      result: { primary_domain: "web_console", environment_description: "Q1 环境描述: 本地开发运行态。" },
      context_updates: { primary_domain: "web_console", environment_description: "Q1 环境描述: 本地开发运行态。" },
      cache_status: "已就绪",
      provider_name: "provider-tools-default",
      preprocessed_evidence: mockQ1PreprocessedEvidence,
      inference_result: {
        primary_domain: "web_console",
        secondary_domains: ["ops_console"],
        confidence: 0.93,
        reasoning_summary: "目录结构和采样日志显示本地 Web Console 运行态。",
        uncertainties: ["缺少更多 data 抽样"],
        suggested_first_step: "inspect workspace evidence",
      },
    },
    {
      question_id: "q5",
      title: "我被允许做什么",
      tool_id: "nine_questions.q5",
      summary: "允许动作限定为受审计的只读检查与显式人工干预。",
      confidence: 0.9,
      trace_id: "trace-q5-555",
      timestamp: "2026-04-04T12:00:04Z",
      result: {
        permission_boundary: { execution_tier: "guarded_write", interaction_scope: "web_console_control_plane" },
      },
      context_updates: {
        permission_boundary: { execution_tier: "guarded_write", interaction_scope: "web_console_control_plane" },
      },
      cache_status: "已就绪",
      provider_name: "provider-tools-default",
    },
  ],
};

beforeEach(() => {
  mockFetch.mockReset();
});

function renderNineQuestionRoutes(initialEntry: string) {
  return render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <Routes>
        <Route path="/console/nine-questions" element={<NineQuestionsReport />} />
        <Route path="/console/nine-questions/:q_id" element={<NineQuestionDetailPage />} />
        <Route path="/console/nine-questions/:q_id/sandbox" element={<NineQuestionSandboxPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("NineQuestions routing", () => {
  it("renders initializing state instead of empty-result notice during cold start", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        status: "initializing",
        status_message: "大脑冷启动中：正在执行全量九问推演...",
        last_turn_id: "0",
        snapshot_version: 0,
        revision: 0,
        refreshed_at: null,
        last_refresh_reason: "bootstrap",
        question_driver_refs: [],
        questions: [],
      }),
    } as Response);

    renderNineQuestionRoutes("/console/nine-questions");

    expect(await screen.findAllByText("大脑冷启动中：正在执行全量九问推演...")).toHaveLength(2);
    expect(screen.queryByText("当前还没有九问结果。运行一次九问后再回到监控页刷新查看。")).not.toBeInTheDocument();
  });

  it("renders real list rows and drills into detail page on row click", async () => {
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockReport,
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockReport,
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          trace_id: "trace-q1-111",
          prompt: "PROMPT_Q1: infer the environment",
          context: { workspace_structure: ["src", "tests"] },
          result: { primary_domain: "web_console" },
          invocation_phase: "nine_question_q1_where_am_i",
          provider_plugin_id: "provider-tools-default",
          preprocessed_evidence: mockQ1PreprocessedEvidence,
          inference_result: {
            primary_domain: "web_console",
            secondary_domains: ["ops_console"],
            confidence: 0.93,
            reasoning_summary: "目录结构和采样日志显示本地 Web Console 运行态。",
            uncertainties: ["缺少更多 data 抽样"],
            suggested_first_step: "inspect workspace evidence",
          },
          llm_trace_payload: {
            request_id: "req-q1-111",
            decision_id: "decision-q1-111",
            provider_name: "provider-tools-default",
            model: "gemini-2.5-flash",
            system_prompt: "SYSTEM_Q1",
            prompt: "PROMPT_Q1: infer the environment",
            context_data: { workspace_structure: ["src", "tests"] },
            raw_response: { id: "raw-q1-111", result: { primary_domain: "web_console" } },
            token_usage: { input_tokens: 220, output_tokens: 66, total_tokens: 286 },
            elapsed_ms: 980,
          },
        }),
      } as Response);

    renderNineQuestionRoutes("/console/nine-questions");

    await waitFor(() => {
      expect(screen.getByText("Q1_Where_Am_I")).toBeInTheDocument();
    });

    expect(screen.getByText(/该页面只是九问运行结果的监控与审计视图/)).toBeInTheDocument();
    expect(screen.getByText("当前最新快照: v9 / rev 9")).toBeInTheDocument();
    expect(screen.queryByText(/Session:/)).not.toBeInTheDocument();
    expect(screen.getAllByText("provider-tools-default")).toHaveLength(2);
    expect(screen.getByText("当前运行域是本地 Web Console 验收环境。")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Q1_Where_Am_I"));

    await waitFor(() => {
      expect(screen.getByText("进入独立沙箱测试")).toBeInTheDocument();
    });

    expect(screen.getByText("结构化推演结果")).toBeInTheDocument();
    expect(screen.getByText("物理与环境态势区")).toBeInTheDocument();
    expect(screen.getByText("工作区本地统计与结构区")).toBeInTheDocument();
    expect(screen.getByText("内容采样与证据区")).toBeInTheDocument();
    expect(screen.getByText("大模型终极推断区")).toBeInTheDocument();
    expect(screen.getByText(".py: 10")).toBeInTheDocument();
    expect(screen.getByText("invoice: 2")).toBeInTheDocument();
    expect(screen.getByText("data/invoices.csv")).toBeInTheDocument();
    const accordionButton = screen.getByRole("button", { name: "logs/app.log · 样本行 workspace_content_sampler | logs/app.log" });
    expect(accordionButton).toHaveAttribute("aria-expanded", "false");
    const llmPromptAccordion = screen.getByTestId("llm-trace-prompt-accordion");
    const llmPromptButton = within(llmPromptAccordion).getByRole("button", { name: "输入 Prompt" });
    expect(llmPromptButton).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(llmPromptButton);
    expect(await screen.findByText(/PROMPT_Q1/)).toBeInTheDocument();
  });

  it("renders sandbox JSON input and shows backend sandbox result text", async () => {
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockReport,
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          question_id: "q1",
          title: "我在哪",
          tool_id: "nine_questions.q1",
          summary: "沙箱确认当前域是独立测试环境。",
          confidence: 0.96,
          trace_id: "sandbox-q1-001",
          elapsed_ms: 1280,
          provider_name: "provider-tools-default",
          prompt: "PROMPT_Q1_SANDBOX",
          context: { mock_seed: true },
          result: {
            primary_domain: "sandbox_console",
            secondary_domains: ["ops_console", "billing_workspace"],
            confidence: 0.96,
            reasoning_summary: "目录结构与日志样本显示这是一个独立测试环境。",
            uncertainties: ["仍缺少更多 data/ 抽样"],
            suggested_first_step: "inspect sandbox output",
          },
          context_updates: {
            workspace_domain_inference: {
              primary_domain: "sandbox_console",
            },
          },
          preprocessed_evidence: {
            physical_and_environment: {
              environment_event: { kind: "sandbox_run", summary: "manual inspection" },
              physical_host_state: {
                memory_pressure: "high",
                network_health: "degraded",
                cwd: "/tmp/q1-sandbox",
              },
              memory_pressure: "high",
              network_health: "degraded",
              memory_pressure_status: "high",
              network_health_status: "degrade",
              environment_summary: ["cwd=/tmp/q1-sandbox", "environment_kind=sandbox_run"],
            },
            workspace_structure: {
              directory_hierarchy_summary: "src/, logs/, data/",
              top_level_dirs: ["src", "logs", "data"],
              file_total_count: 42,
              suffix_distribution: { ".py": 10, ".md": 3, ".log": 2 },
              high_frequency_filename_keywords: { invoice: 2, api: 4 },
              candidate_groups: ["python_code", "logs"],
              obvious_risk_files: ["data/invoices.csv"],
              directory_tree_rows: [
                { row_id: "dir-1", path: "src", label: "src", depth: 0, kind: "directory", file_count: 10 },
              ],
              candidate_group_details: [
                { group_id: "group-1", label: "python_code", file_count: 10, summary: "核心代码目录" },
              ],
              obvious_risk_file_details: [
                { path: "data/invoices.csv", severity: "high", reason: "账单数据直出" },
              ],
              analyzer_snapshot: {},
            },
            workspace_content_sampling: {
              sampled_file_summaries: [
                {
                  path: "logs/app.log",
                  summary: "长日志样本",
                  snippet: "ERROR sandbox validation failed on line 1",
                },
              ],
              log_anomaly_snippets: ["ERROR sandbox validation failed on line 1"],
              long_text_evidence: [
                {
                  evidence_id: "sample-1-snippet",
                  label: "logs/app.log · 样本行",
                  kind: "snippet",
                  source: "workspace_content_sampler",
                  path: "logs/app.log",
                  text: "ERROR sandbox validation failed on line 1",
                },
              ],
              sample_count: 1,
              anomaly_count: 1,
              sampler_snapshot: {},
            },
          },
          inference_result: {
            primary_domain: "sandbox_console",
            secondary_domains: ["ops_console", "billing_workspace"],
            confidence: 0.96,
            reasoning_summary: "目录结构与日志样本显示这是一个独立测试环境。",
            uncertainties: ["仍缺少更多 data/ 抽样"],
            suggested_first_step: "inspect sandbox output",
          },
          llm_trace_payload: {
            provider_name: "provider-tools-default",
            model: "gemini-3-flash(auto)",
            system_prompt: "SYSTEM_PROMPT: infer workspace domain",
            prompt: "SYSTEM_PROMPT: infer workspace domain\n\nEvidence Summary...",
            context_data: { analysis_summary: "src/, logs/, data/" },
            raw_response: { id: "raw-q1-sandbox", choices: [{ message: { content: "{\"primary_domain\":\"sandbox_console\"}" } }] },
            token_usage: { input_tokens: 101, output_tokens: 27, total_tokens: 128 },
            elapsed_ms: 1280,
          },
        }),
      } as Response);

    renderNineQuestionRoutes("/console/nine-questions/q1/sandbox");

    await waitFor(() => {
      expect(screen.getByLabelText("Mock 上下文 JSON")).toBeInTheDocument();
    });

    expect(screen.getByText("执行测试")).toBeInTheDocument();
    fireEvent.click(screen.getByText("执行测试"));

    await waitFor(() => {
      expect(screen.getByText(/沙箱确认当前域是独立测试环境。/)).toBeInTheDocument();
    });

    expect(screen.getByText("primary_domain")).toBeInTheDocument();
    expect(screen.getByText("sandbox_console")).toBeInTheDocument();
    expect(screen.getByText("ops_console")).toBeInTheDocument();
    expect(screen.getByText(".py: 10")).toBeInTheDocument();
    expect(screen.getByText("invoice: 2")).toBeInTheDocument();
    expect(screen.getByText("data/invoices.csv")).toBeInTheDocument();
    const accordionButton = screen.getByRole("button", { name: /logs\/app\.log · 样本行/i });
    expect(accordionButton).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(accordionButton);
    await waitFor(() => {
      expect(screen.getAllByText(/ERROR sandbox validation failed on line 1/).length).toBeGreaterThanOrEqual(1);
    });
    expect(screen.getAllByText(/provider-tools-default/).length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("大模型交互溯源区")).toBeInTheDocument();
    const promptAccordion = screen.getByTestId("llm-trace-prompt-accordion");
    expect(promptAccordion.querySelector(".MuiAccordionSummary-root")).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(screen.getByText("输入 Prompt"));
    await waitFor(() => {
      expect(screen.getByText(/SYSTEM_PROMPT: infer workspace domain/)).toBeInTheDocument();
    });
  });

  it("renders a visible alert when sandbox API returns an LLM configuration error", async () => {
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockReport,
      } as Response)
      .mockResolvedValueOnce({
        ok: false,
        status: 503,
        text: async () =>
          JSON.stringify({
            detail: {
              error_code: "llm_missing_credentials",
              user_message: "大模型配置错误或 API Key 缺失，请检查设置。",
            },
          }),
      } as Response);

    renderNineQuestionRoutes("/console/nine-questions/q1/sandbox");

    await waitFor(() => {
      expect(screen.getByLabelText("Mock 上下文 JSON")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText("执行测试"));

    await waitFor(() => {
      expect(screen.getByText("大模型配置错误或 API Key 缺失，请检查设置。")).toBeInTheDocument();
    });
  });

  it("renders a visible alert when the report API itself fails with an LLM configuration error", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 503,
      text: async () =>
        JSON.stringify({
          detail: {
            error_code: "llm_missing_credentials",
            user_message: "大模型配置错误或 API Key 缺失，请检查设置。",
          },
        }),
    } as Response);

    renderNineQuestionRoutes("/console/nine-questions");

    await waitFor(() => {
      expect(screen.getByText("大模型配置错误或 API Key 缺失，请检查设置。")).toBeInTheDocument();
    });
  });
});
