import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import React from 'react';

import Q1Detail from "./q1/Q1Detail";
import Q1Test from "./q1/Q1Test";
import * as api from "./nineQuestionsApi";

// 全面 Mock API 模块，确保物理流量隔绝测试
vi.mock("./nineQuestionsApi", async () => {
  const actual = await vi.importActual("./nineQuestionsApi");
  return {
    ...actual,
    fetchNineQuestionDetail: vi.fn(),
    runNineQuestionSandboxTest: vi.fn(),
  };
});

const sampleLongText = "A".repeat(5000);

const mockEvidence = {
  physical_and_environment: {
    environment_event: { kind: "production_audit", summary: "live system check" },
    physical_host_state: { memory_pressure: "normal", network_health: "healthy", hostname: "zentex-prod-01" },
    memory_pressure: "normal",
    network_health: "healthy",
    memory_pressure_status: "healthy",
    network_health_status: "healthy",
    environment_summary: ["hostname=zentex-prod-01", "environment_kind=production_audit"],
  },
  workspace_structure: {
    directory_hierarchy_summary: "Main production workspace with src/ and bin/",
    top_level_dirs: ["src", "bin"],
    file_total_count: 1540,
    suffix_distribution: { ".ts": 450, ".json": 120, ".lock": 5 },
    high_frequency_filename_keywords: { service: 45, controller: 30 },
    candidate_groups: ["typescript_backend", "config"],
    obvious_risk_files: ["src/secrets.ts.bak"],
    directory_tree_rows: [{ row_id: "dir-1", path: "src", label: "src", depth: 0, kind: "directory", file_count: 450 }],
    candidate_group_details: [{ group_id: "group-1", label: "typescript_backend", file_count: 450, summary: "Core production logic" }],
    obvious_risk_file_details: [{ path: "src/secrets.ts.bak", severity: "critical", reason: "Potential credential leak" }],
    analyzer_snapshot: {},
  },
  workspace_content_sampling: {
    sampled_file_summaries: [{ path: "src/main.ts", summary: "Entry point sampler", header: "import { NestFactory } from '@nestjs/core';" }],
    log_anomaly_snippets: ["CRITICAL: Database connection dropped at 02:00"],
    long_text_evidence: [
      {
        evidence_id: "extremely-long-text-1",
        label: "src/main.ts · 极长采样文本",
        kind: "header",
        source: "workspace_content_sampler",
        path: "src/main.ts",
        text: sampleLongText,
      },
    ],
    sample_count: 1,
    anomaly_count: 1,
    sampler_snapshot: {},
  },
};

const mockInference = {
  primary_domain: "production_server",
  secondary_domains: ["api_gateway", "database_cluster"],
  confidence: 0.98,
  reasoning_summary: "High density of TypeScript files.",
  uncertainties: ["Cloud provider metadata not fully analyzed"],
  suggested_first_step: "Verify security group policies",
};

const mockQuestionItem = {
  question_id: "q1",
  title: "我在哪",
  tool_id: "nine_questions.q1",
  summary: "系统已确认当前处于生产环境 API 节点。",
  confidence: 0.98,
  trace_id: "trace-prod-q1-xyz",
  timestamp: "2026-04-05T01:00:00Z",
  result: {},
  context_updates: {},
  cache_status: "已就绪",
  provider_name: "gemini-1.5-pro",
  mounted_plugins: [
    { plugin_id: "nine-question-q1-where-am-i", description: "Q1 Base Plugin: workspace domain inference", version: "1.0.0", status: "active", source_kind: "base" },
    { plugin_id: "nine-question-q1-where-am-i-capability-patch", description: "Q1 Enhancement Patch: semantic domain refinement", version: "1.1.0", status: "active", source_kind: "patch" },
  ],
  preprocessed_evidence: mockEvidence,
  inference_result: mockInference,
  llm_trace_payload: {
    provider_name: "gemini-1.5-pro",
    model: "gemini-1.5-pro",
    system_prompt: "SYSTEM_PROMPT: You are auditing a system...",
    prompt: "USER_PROMPT: You are auditing a system...",
    context_data: { analysis_summary: "workspace summary" },
    raw_response: { id: "raw-q1", content: "raw lLM output payload " + "X".repeat(3000) },
    token_usage: { input_tokens: 120, output_tokens: 45, total_tokens: 165 },
    elapsed_ms: 812,
    question_driver_refs: ["我在哪"],
  },
  q1_llm_upgrade: {
    planning_status: "planned",
    profile: {
      objective_summary: "Improve Q1 environment inference stability on mixed workspaces.",
      target_component: "q1_where_am_i_reasoner",
      target_metric: "production_accuracy",
      baseline_version: "1.0.0",
      recommended_dataset: "q1_workspace_goldens_v1",
      validation_commands: [
        "pytest tests/plugins/test_q1_where_am_i_plugin.py -q",
        "pytest tests/web_console/api/test_q1_production_evidence.py -q",
      ],
    },
    candidate_version: "1.0.1",
    release_gate: "all_validation_commands_green",
    error_message: null,
  },
};

// ════════════════════════════════════════════════════════════════
// 强断言测试套件：物理隔离 · 高密度 MUI 渲染 · 防炸版折叠 · 人话降级
// ════════════════════════════════════════════════════════════════
describe("【物理隔离与证据全景测试】Q1 生产审计页与独立沙箱强断言测试", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // ── 任务 1：独立路由与物理隔离断言 ──────────────────────────────────
  it("任务 1a: 断言 Q1Detail 在独立路由 /console/nine-questions/q1 渲染并调用专属 API", async () => {
    vi.mocked(api.fetchNineQuestionDetail).mockResolvedValue(mockQuestionItem as any);

    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q1"]}>
        <Routes>
          <Route path="/console/nine-questions/q1" element={<Q1Detail />} />
        </Routes>
      </MemoryRouter>
    );

    // 验证是否调用了独立的 Q1 Detail 接口（GET /api/web/nine-questions/q1），而非聚合接口
    await waitFor(() => {
      expect(api.fetchNineQuestionDetail).toHaveBeenCalledWith("q1");
    });

    // 断言页面物理隔离：拥有独立的根节点 data-testid
    expect(screen.getByTestId("q1-detail-root")).toBeInTheDocument();
    expect(screen.getByText(/Q1_Where_Am_I 正式审计页/)).toBeInTheDocument();
    // 导航到沙箱按钮必须存在，证明两页物理分离
    expect(screen.getByTestId("q1-sandbox-nav-button")).toBeInTheDocument();
    // 严禁 runNineQuestionSandboxTest 被调用（生产页绝不触发沙箱接口）
    expect(api.runNineQuestionSandboxTest).not.toHaveBeenCalled();
  });

  it("任务 1b: 断言 Q1Test 在独立路由 /console/nine-questions/q1/test 渲染并拥有独立 DOM 根节点", async () => {
    vi.mocked(api.fetchNineQuestionDetail).mockResolvedValue(mockQuestionItem as any);

    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q1/test"]}>
        <Routes>
          <Route path="/console/nine-questions/q1/test" element={<Q1Test />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByTestId("q1-test-root")).toBeInTheDocument();
    });

    // 沙箱页有独立 DOM 根节点，与生产页的 q1-detail-root 物理隔离
    expect(screen.queryByTestId("q1-detail-root")).not.toBeInTheDocument();
    expect(screen.getByText(/独立沙箱测试页/)).toBeInTheDocument();
    // 沙箱页加载初始模板时仅读取，不调用 runNineQuestionSandboxTest
    expect(api.runNineQuestionSandboxTest).not.toHaveBeenCalled();
  });

  // ── 任务 2：高密度 MUI Chip 阵列渲染断言 ─────────────────────────────
  it("任务 2: 生产页高密度 MUI Chip 阵列渲染 — 后缀分布 / 次领域 / 插件状态", async () => {
    vi.mocked(api.fetchNineQuestionDetail).mockResolvedValue(mockQuestionItem as any);

    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q1"]}>
        <Routes>
          <Route path="/console/nine-questions/q1" element={<Q1Detail />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByTestId("q1-primary-domain-chip")).toBeInTheDocument();
    });

    // 主领域 Chip 渲染
    expect(screen.getByTestId("q1-primary-domain-chip")).toHaveTextContent("主领域: production_server");
    // 次领域 Chip 阵列必须完整渲染（2个）
    expect(screen.getAllByTestId("q1-secondary-domain-chip")).toHaveLength(2);
    // cache_status Chip
    expect(screen.getByTestId("q1-cache-status-chip")).toHaveTextContent("已就绪");
    // trace_id Chip
    expect(screen.getByTestId("q1-trace-chip")).toBeInTheDocument();
    expect(screen.getByTestId("q1-upgrade-panel")).toBeInTheDocument();
    expect(screen.getByTestId("q1-upgrade-baseline-chip")).toHaveTextContent("Baseline: 1.0.0");
    expect(screen.getByTestId("q1-upgrade-candidate-chip")).toHaveTextContent("Candidate: 1.0.1");
    expect(screen.getByTestId("q1-upgrade-release-gate-chip")).toHaveTextContent(
      "Release Gate: all_validation_commands_green",
    );

    // 文件后缀分布 Chip 阵列（来自 Q1EvidencePanel 工作区结构区）
    expect(screen.getByText(".ts: 450")).toBeInTheDocument();
    expect(screen.getByText(".json: 120")).toBeInTheDocument();
    expect(screen.getByText(".lock: 5")).toBeInTheDocument();

    // 高频关键词 Chip 阵列
    expect(screen.getByText("service: 45")).toBeInTheDocument();
    expect(screen.getByText("controller: 30")).toBeInTheDocument();

    // 文件总数 Chip
    expect(screen.getByText("文件总数: 1540")).toBeInTheDocument();

    // MountedPluginsZone 插件 Chip（基础插件 + 补丁插件，active=绿）
    expect(screen.getByTestId("mounted-plugin-nine-question-q1-where-am-i")).toBeInTheDocument();
    expect(screen.getByTestId("mounted-plugin-nine-question-q1-where-am-i-capability-patch")).toBeInTheDocument();
  });

  // ── 任务 3：长文本防炸版 + 防黑盒 Accordion 默认折叠断言（核心强校验）──
  it("任务 3: 超长采样文本与 LLM 溯源 Payload 均通过 Accordion 包裹且默认折叠", async () => {
    vi.mocked(api.fetchNineQuestionDetail).mockResolvedValue(mockQuestionItem as any);

    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q1"]}>
        <Routes>
          <Route path="/console/nine-questions/q1" element={<Q1Detail />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByTestId("q1-long-text-accordion")).toBeInTheDocument();
    });

    // 强断言：内容采样长文本 Accordion 默认折叠
    const longTextAccordion = screen.getByTestId("q1-long-text-accordion");
    expect(longTextAccordion.querySelector(".MuiAccordionSummary-root")).toHaveAttribute("aria-expanded", "false");
    // 折叠状态下，超长文本不应出现在 DOM 可见区（防炸版）
    expect(screen.queryByText(sampleLongText.substring(0, 100))).not.toBeInTheDocument();

    // 强断言：LLM 溯源三个 Accordion 均默认折叠（防黑盒红线）
    const promptAccordion = screen.getByTestId("llm-trace-prompt-accordion");
    const contextAccordion = screen.getByTestId("llm-trace-context-accordion");
    const rawResponseAccordion = screen.getByTestId("llm-trace-raw-response-accordion");

    expect(promptAccordion.querySelector(".MuiAccordionSummary-root")).toHaveAttribute("aria-expanded", "false");
    expect(contextAccordion.querySelector(".MuiAccordionSummary-root")).toHaveAttribute("aria-expanded", "false");
    expect(rawResponseAccordion.querySelector(".MuiAccordionSummary-root")).toHaveAttribute("aria-expanded", "false");

    // 验证大模型溯源区 question_driver_refs 标识透传
    // (数据通过 llm_trace_payload 传递至 LLMTracePanel)
    expect(screen.getByText(/大模型交互溯源区/)).toBeInTheDocument();

    // 展开 Prompt Accordion 后，内容应可见
    const promptSummary = promptAccordion.querySelector(".MuiAccordionSummary-root") as HTMLElement;
    fireEvent.click(promptSummary);
    await waitFor(() => {
      expect(promptAccordion.querySelector(".MuiAccordionSummary-root")).toHaveAttribute("aria-expanded", "true");
    });
    expect(promptAccordion).toHaveTextContent("USER_PROMPT: You are auditing a system");
  });

  // ── 任务 4：人话提示与降级断言（严禁白屏崩溃）─────────────────────────
  it("任务 4a: Q1Detail 503 错误 → 人话提示 '后端推演引擎未就绪' + 下一步操作", async () => {
    vi.mocked(api.fetchNineQuestionDetail).mockRejectedValue(new Error("九问状态机未挂载到运行时"));

    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q1"]}>
        <Routes>
          <Route path="/console/nine-questions/q1" element={<Q1Detail />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByTestId("q1-error-boundary")).toBeInTheDocument();
    });

    // 强断言：展示人话标题（问题是什么）
    expect(screen.getByText("后端推演引擎未就绪")).toBeInTheDocument();
    // 强断言：展示下一步操作指引
    expect(screen.getByText(/检查 Zentex Brain Runtime 的启动状态/)).toBeInTheDocument();
    // 强断言：必须提供重试按钮，严禁白屏
    expect(screen.getByTestId("q1-retry-button")).toBeInTheDocument();
    // 强断言：绝不暴露原始 Error 字符串 "状态机未挂载到运行时"
    expect(screen.queryByText("九问状态机未挂载到运行时")).not.toBeInTheDocument();
  });

  it("任务 4b: Q1Detail NetworkError → 人话提示 '网络连接失败'", async () => {
    vi.mocked(api.fetchNineQuestionDetail).mockRejectedValue(new Error("Failed to fetch"));

    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q1"]}>
        <Routes>
          <Route path="/console/nine-questions/q1" element={<Q1Detail />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByTestId("q1-error-boundary")).toBeInTheDocument();
    });

    expect(screen.getByText("网络连接失败")).toBeInTheDocument();
    expect(screen.getByText(/检查网络连接或确认 dev server 正在运行/)).toBeInTheDocument();
  });

  it("任务 4c: Q1Test 沙箱执行 500 错误 → 人话提示 '沙箱推演引擎内部错误' 不白屏", async () => {
    vi.mocked(api.fetchNineQuestionDetail).mockResolvedValue(mockQuestionItem as any);
    vi.mocked(api.runNineQuestionSandboxTest).mockRejectedValue(
      new Error("Internal Server Error 500")
    );

    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q1/test"]}>
        <Routes>
          <Route path="/console/nine-questions/q1/test" element={<Q1Test />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByTestId("q1-test-root")).toBeInTheDocument();
    });

    // 点击执行触发 500 错误
    fireEvent.click(screen.getByTestId("q1-test-run-button"));

    await waitFor(() => {
      expect(screen.getByTestId("q1-test-run-error")).toBeInTheDocument();
    });

    // 强断言：展示人话标题（问题是什么）
    expect(screen.getByText("沙箱推演引擎内部错误（HTTP 500）")).toBeInTheDocument();
    // 强断言：展示下一步操作指引
    expect(screen.getByText(/请检查后台服务日志/)).toBeInTheDocument();
    // 严禁暴露原始 Error Enum
    expect(screen.queryByText("Internal Server Error 500")).not.toBeInTheDocument();
  });

  it("任务 4d: Q1Test 沙箱 NetworkError → 人话提示 '无法连接到后端，请检查服务'", async () => {
    vi.mocked(api.fetchNineQuestionDetail).mockResolvedValue(mockQuestionItem as any);
    vi.mocked(api.runNineQuestionSandboxTest).mockRejectedValue(
      new Error("Failed to fetch")
    );

    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q1/test"]}>
        <Routes>
          <Route path="/console/nine-questions/q1/test" element={<Q1Test />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByTestId("q1-test-root")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId("q1-test-run-button"));

    await waitFor(() => {
      expect(screen.getByTestId("q1-test-run-error")).toBeInTheDocument();
    });

    expect(screen.getByText("无法连接到后端，请检查服务")).toBeInTheDocument();
    expect(screen.getByText(/请确认 Zentex Dev Server 正在运行/)).toBeInTheDocument();
  });

  // ── 任务 5：沙箱防污染断言 ───────────────────────────────────────────
  it("任务 5: 沙箱执行独立于生产状态机 — runNineQuestionSandboxTest 用专属沙箱接口", async () => {
    vi.mocked(api.fetchNineQuestionDetail).mockResolvedValue(mockQuestionItem as any);
    vi.mocked(api.runNineQuestionSandboxTest).mockResolvedValue({
      ...mockQuestionItem,
      summary: "Sandbox Analysis Result",
    } as any);

    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q1/test"]}>
        <Routes>
          <Route path="/console/nine-questions/q1/test" element={<Q1Test />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByTestId("q1-test-root")).toBeInTheDocument();
    });

    // 执行沙箱分析
    fireEvent.click(screen.getByTestId("q1-test-run-button"));

    await waitFor(() => {
      expect(screen.getByTestId("q1-test-success-alert")).toBeInTheDocument();
    });

    // 强断言：使用沙箱接口（POST /test），而非生产接口
    expect(api.runNineQuestionSandboxTest).toHaveBeenCalledWith("q1", expect.any(Object));
    // 沙箱执行后 fetchNineQuestionDetail 只在初始加载时被调用一次（模板读取），不因沙箱结果而重复调用
    expect(api.fetchNineQuestionDetail).toHaveBeenCalledTimes(1);

    // 沙箱结果成功展示
    expect(screen.getByText("Sandbox Analysis Result")).toBeInTheDocument();
    expect(screen.getByTestId("q1-test-result-panel")).toBeInTheDocument();
    expect(screen.getByTestId("q1-upgrade-panel")).toBeInTheDocument();
    expect(screen.getByTestId("q1-upgrade-status-chip")).toHaveTextContent("状态: planned");
    expect(screen.getByTestId("q1-upgrade-validation-commands")).toHaveTextContent(
      "pytest tests/plugins/test_q1_where_am_i_plugin.py -q",
    );
  });
});
