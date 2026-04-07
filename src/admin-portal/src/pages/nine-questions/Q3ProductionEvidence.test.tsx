import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import React from 'react';

import Q3Detail from "./q3/Q3Detail";
import Q3Test from "./q3/Q3Test";
import * as api from "./nineQuestionsApi";

// Mock API 模块，确保测试独立性
vi.mock("./nineQuestionsApi", async () => {
  const actual = await vi.importActual("./nineQuestionsApi");
  return {
    ...actual,
    fetchNineQuestionDetail: vi.fn(),
    runNineQuestionSandboxTest: vi.fn(),
  };
});

const mockEvidence = {
  workspace_permission: {
    workspaces: ["/vol/trading_data", "/tmp/scratch"],
    tenant_permissions: ["READ_ONLY_MARKET_DATA", "EXECUTE_TRADES"],
    execution_tokens: ["JWT_TOKEN_EXPIRED_IN_1H"],
  },
  tools_agents: {
    cognitive_tools: ["brain_analyzer", "pattern_matcher"],
    execution_tools: ["binance_connector", "slack_notifier"],
    connected_agents: [{ agent_id: "risk_manager_bot", status: "online" }],
    cognitive_tool_rows: [
      { id: "brain_analyzer", name: "Brain Analyzer", introduction: "认知分析工具", function_description: "用于识别模式与风险。" },
      { id: "pattern_matcher", name: "Pattern Matcher", introduction: "模式匹配工具", function_description: "用于寻找重复信号。" },
    ],
    execution_tool_rows: [
      { id: "binance_connector", name: "Binance Connector", introduction: "交易连接器", function_description: "用于访问交易所执行域。" },
      { id: "slack_notifier", name: "Slack Notifier", introduction: "通知工具", function_description: "用于发送运行告警。" },
    ],
    connected_agent_rows: [
      { id: "risk_manager_bot", name: "Risk Manager Bot", introduction: "风险协作 Agent", function_description: "用于审核风险边界。", status: "online" },
    ],
  },
  memory_strategy: {
    experience_logs: ["Last rebalance failed at 02:00"],
    strategy_patches: ["Conservative mode active due to high volatility"],
  },
};

const mockInference = {
  sufficiency_assessment: {
    resource_status: "sufficient",
    resource_status_label: "资源充沛",
    resource_status_explanation: "当前关键工具与协作资源基本齐备。",
    missing_critical_assets: [],
    bottleneck_node: "market_data_api_rate_limit",
    reasoning_summary: "All essential tools are mounted and responding.",
  },
};

const mockQuestionItem = {
  question_id: "q3",
  title: "我有什么",
  tool_id: "nine_questions.q3",
  summary: "资源盘点完成，工具链完整度 100%。",
  confidence: 0.95,
  trace_id: "trace-prod-q3-ghi",
  timestamp: "2026-04-05T03:00:00Z",
  result: {},
  context_updates: {},
  cache_status: "已就绪",
  provider_name: "gpt-4o",
  mounted_plugins: [{ plugin_id: "asset_auditor", description: "Asset Auditor", version: "2.1", status: "active", source_kind: "base" }],
  preprocessed_evidence: mockEvidence,
  inference_result: mockInference,
  llm_trace_payload: {
    provider_name: "gpt-4o",
    model: "gpt-4o",
    system_prompt: "You are an asset auditor...",
    prompt: "Scanning workspace...",
    context_data: {},
    raw_response: {},
    token_usage: { input_tokens: 150, output_tokens: 75, total_tokens: 225 },
    elapsed_ms: 1500,
  },
};

describe("【Q3 资源审计物理隔离与证据全景测试】", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("任务 1: 断言 Q3 详情页独立 API 绑定与物理路由隔离", async () => {
    vi.mocked(api.fetchNineQuestionDetail).mockResolvedValue(mockQuestionItem as any);

    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q3"]}>
        <Routes>
          <Route path="/console/nine-questions/q3" element={<Q3Detail />} />
        </Routes>
      </MemoryRouter>
    );

    // 强断言：必须调用 Q3 的独立 REST 端点
    await waitFor(() => {
      expect(api.fetchNineQuestionDetail).toHaveBeenCalledWith("q3");
    });

    expect(screen.getByTestId("q3-detail-root")).toBeInTheDocument();
    expect(screen.getByText(/Q3_What_Do_I_Have 正式审计页/)).toBeInTheDocument();
    expect(screen.getByTestId("q3-sandbox-nav-button")).toBeInTheDocument();
  });

  it("任务 2: Q3 异常降级人话提示强断言 (503 场景)", async () => {
    vi.mocked(api.fetchNineQuestionDetail).mockRejectedValue(new Error("状态机未挂载到运行时"));

    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q3"]}>
        <Routes>
          <Route path="/console/nine-questions/q3" element={<Q3Detail />} />
        </Routes>
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByTestId("q3-error-boundary")).toBeInTheDocument();
    });

    // 强断言：展示后端引擎未就绪建议
    expect(screen.getByText("后端推演引擎未就绪")).toBeInTheDocument();
  });
});
