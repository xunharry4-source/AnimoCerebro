import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MemoryRouter } from "react-router-dom";

vi.mock("./pages/dashboard/RealtimeDashboard", () => ({ default: () => <div>dashboard</div> }));
vi.mock("./pages/dashboard/MemoryReasoning", () => ({ default: () => <div>memory</div> }));
vi.mock("./pages/dashboard/SimulationExplorer", () => ({ default: () => <div>simulation</div> }));
vi.mock("./pages/nine-questions/NineQuestionsReport", () => ({ default: () => <div>nine-questions</div> }));
vi.mock("./pages/nine-questions/NineQuestionDetailPage", () => ({ default: () => <div>nine-question-detail</div> }));
vi.mock("./pages/nine-questions/NineQuestionSandboxPage", () => ({ default: () => <div>nine-question-sandbox</div> }));
vi.mock("./pages/agents/AgentAssetManager", () => ({ default: () => <div>agents</div> }));
vi.mock("./pages/tasks/ZentexTaskManager", () => ({ default: () => <div>tasks</div> }));
vi.mock("./pages/plugins/PluginManagement", () => ({ default: () => <div>plugins</div> }));
vi.mock("./pages/upgrades/UpgradeManagement", () => ({ default: () => <div>upgrades</div> }));
vi.mock("./pages/cli/CliAssetManager", () => ({ default: () => <div>cli</div> }));
vi.mock("./pages/mcp/McpServerDashboard", () => ({ default: () => <div>mcp</div> }));
vi.mock("./pages/audit/AuditReplay", () => ({ default: () => <div>audit</div> }));
vi.mock("./pages/audit/AuditTraceModePage", () => ({ default: () => <div>audit-trace-mode-page</div> }));
vi.mock("./pages/audit/AuditReviewLedgerPage", () => ({ default: () => <div>audit-review-ledger</div> }));
vi.mock("./pages/audit/TranscriptReplayPage", () => ({ default: () => <div>transcript-replay</div> }));

import App from "./App";

const mockFetch = vi.fn();
global.fetch = mockFetch;

beforeEach(() => {
  mockFetch.mockReset();
});

describe("App LLM startup banner", () => {
  it("renders a top-level alert when startup LLM probe reports unavailable", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      text: async () =>
        JSON.stringify({
          available: false,
          probe_checked: true,
          provider_name: "openai_compat",
          reason: "timeout",
          hint: "大模型探针超时或网络不可达，请检查网关连通性。",
        }),
    } as Response);

    render(
      <MemoryRouter initialEntries={["/console/dashboard"]}>
        <App />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("global-llm-status-alert")).toBeInTheDocument();
    });

    expect(screen.getByText(/启动前 LLM 检查未通过/)).toBeInTheDocument();
    expect(screen.getByText(/openai_compat/)).toBeInTheDocument();
    expect(screen.getByText(/大模型探针超时或网络不可达/)).toBeInTheDocument();
    expect(mockFetch).toHaveBeenCalledWith(
      "/api/web/llm/status",
      expect.objectContaining({
        headers: { Accept: "application/json" },
      }),
    );
  });
});
