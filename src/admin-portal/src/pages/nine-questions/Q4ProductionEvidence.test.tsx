import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, fireEvent, within } from "@testing-library/react";
import React from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import Q4Detail from "./q4/Q4Detail";
import Q4Test from "./q4/Q4Test";
import * as api from "./nineQuestionsApi";

vi.mock("./nineQuestionsApi", async () => {
  const actual = await vi.importActual("./nineQuestionsApi");
  return {
    ...actual,
    fetchNineQuestionDetail: vi.fn(),
    fetchNineQuestionTrace: vi.fn(),
    runNineQuestionSandboxTest: vi.fn(),
  };
});

const mockQ4Evidence = {
  q1_context: {
    scene_model: { primary_domain: "audit_console", environment_type: "console" },
    uncertainty_profile: { uncertainty_intensity: 0.44, risk_sources: ["network_jitter"] },
  },
  q2_context: {
    role_profile: { identity_role: "zentex", active_role: "auditor", task_role: "capability_assessor" },
    mission_boundary: { current_mission: "determine safe actions", continuity_boundaries: ["do_not_fake_capability"] },
  },
  q3_inventory: {
    available_cognitive_tools: ["MemorySearch", "CodeAnalyzer"],
    available_execution_tools: [],
    connected_agents: [
      { agent_id: "agent-online", name: "AuditAgent", summary: "read-only audit helper", status: "online" },
      { agent_id: "agent-offline", name: "OfflineAgent", summary: "offline", status: "offline" },
    ],
    activated_strategy_patches: ["Patch-v3: disallow write path"],
    accessible_workspace_zones: ["/workspace/audit", "/workspace/reports"],
    resource_evaluation: { resource_status: "degraded", missing_critical_assets: ["WRITE_EXECUTOR"] },
  },
};

const mockQ4Inference = {
  capability_upper_limits: ["read_workspace_state", "inspect_audit_log"],
  actionable_space: ["view_dashboard", "inspect_audit_log"],
  executable_strategies: [
    "Use read-only inspection workflow.\nStep 1: inspect logs.\nStep 2: collect evidence.",
    "Escalate to human operator for any missing write capability.",
  ],
};

const mockTrace = {
  trace_id: "trace-q4-abc",
  prompt: "PROMPT_Q4",
  context: {},
  result: { capability_boundary_profile: mockQ4Inference },
  provider_name: "Mock Provider",
  preprocessed_evidence: mockQ4Evidence,
  inference_result: mockQ4Inference,
  llm_trace_payload: {
    provider_name: "Mock Provider",
    model: "mock-model",
    elapsed_ms: 100,
    system_prompt: "Extremely long system prompt indicating mock...",
    prompt: "Context payload goes here...",
    source_module: "q4_what_can_i_do_plugin",
    question_driver_refs: ["我能做什么"],
    raw_response: { test: "raw" },
    token_usage: { input_tokens: 50, output_tokens: 20, total_tokens: 70 },
    context_data: {},
  },
};

const mockDetail = {
  question_id: "q4",
  title: "我能做什么",
  tool_id: "tool_q4",
  summary: "Q4 summary",
  confidence: 0.95,
  trace_id: "trace-q4-abc",
  timestamp: "2026-04-05T10:00:00Z",
  cache_status: "已就绪",
  provider_name: "Mock Provider",
  mounted_plugins: [
    { plugin_id: "q4_plugin", description: "desc", version: "1.0.0", status: "active", source_kind: "base" },
  ],
  preprocessed_evidence: mockQ4Evidence,
  inference_result: mockQ4Inference,
  llm_trace_payload: mockTrace.llm_trace_payload,
  result: {},
  context_updates: { q3_unified_asset_inventory: mockQ4Evidence.q3_inventory },
};

describe("Q4 structured evidence rendering", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(api.fetchNineQuestionDetail).mockResolvedValue(mockDetail as any);
    vi.mocked(api.fetchNineQuestionTrace).mockResolvedValue(mockTrace as any);
    vi.mocked(api.runNineQuestionSandboxTest).mockResolvedValue({
      ...mockDetail,
      elapsed_ms: 100,
    } as any);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders Q4 detail via single-question API with isolated root and folded long text", async () => {
    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q4"]}>
        <Routes>
          <Route path="/console/nine-questions/q4" element={<Q4Detail />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText("Q4_What_Can_I_Do 正式审计页")).toBeInTheDocument();
    });
    expect(screen.getByTestId("q4-detail-root")).toBeInTheDocument();
    expect(screen.queryByTestId("q4-test-root")).not.toBeInTheDocument();
    expect(api.fetchNineQuestionDetail).toHaveBeenCalledWith("q4");
    expect(screen.getByText("【前置资产与态势依据区】")).toBeInTheDocument();
    expect(screen.getByText("MemorySearch")).toBeInTheDocument();
    expect(screen.queryByText("OfflineAgent")).not.toBeInTheDocument();
    expect(screen.getByText("【物理能力上限与动作空间区】")).toBeInTheDocument();
    const actionSpace = screen.getByTestId("q4-actionable-space");
    const chips = actionSpace.querySelectorAll(".MuiChip-root");
    expect(chips.length).toBeGreaterThan(0);
    expect(chips[0].className).toMatch(/MuiChip-colorPrimary/);
    expect(screen.getByText("view_dashboard")).toBeInTheDocument();

    const strategyAccordions = screen.getAllByTestId("executable-strategy-accordion");
    strategyAccordions.forEach((el) => {
      const btn = within(el).getByRole("button");
      expect(btn).toHaveAttribute("aria-expanded", "false");
    });
    const promptAccordion = screen.getByTestId("llm-trace-prompt-accordion");
    expect(within(promptAccordion).getByRole("button", { name: "输入 Prompt" })).toHaveAttribute("aria-expanded", "false");
  });

  it("renders Q4 sandbox with isolated root and mock json injection area", async () => {
    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q4/test"]}>
        <Routes>
          <Route path="/console/nine-questions/q4/test" element={<Q4Test />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("q4-test-root")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("q4-detail-root")).not.toBeInTheDocument();
    expect(api.fetchNineQuestionDetail).toHaveBeenCalledWith("q4");
    expect(screen.getByRole("textbox")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "执行沙箱测试" }));
    await waitFor(() => {
      expect(screen.getByText("【物理能力上限与动作空间区】")).toBeInTheDocument();
    });
    expect(screen.getByText("view_dashboard")).toBeInTheDocument();
  });

  it("renders a human-readable error panel when Q4 detail loading fails", async () => {
    vi.mocked(api.fetchNineQuestionDetail).mockRejectedValueOnce(new Error("大模型调用失败，请检查 API Key 配置"));

    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q4"]}>
        <Routes>
          <Route path="/console/nine-questions/q4" element={<Q4Detail />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByText("大模型调用失败，请检查 API Key 配置")).toBeInTheDocument();
  });
});
