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
vi.mock("./pages/tasks/TaskDetailPage", () => ({ default: () => <div>task-detail</div> }));
vi.mock("./pages/plugins/PluginManagement", () => ({ default: () => <div>plugins</div> }));
vi.mock("./pages/upgrades/UpgradeManagement", () => ({ default: () => <div>upgrades</div> }));
vi.mock("./pages/cli/CliAssetManager", () => ({ default: () => <div>cli</div> }));
vi.mock("./pages/mcp/McpServerDashboard", () => ({ default: () => <div>mcp</div> }));
vi.mock("./pages/audit/AuditReplay", () => ({ default: () => <div>audit</div> }));
vi.mock("./pages/audit/AuditTraceCenterPage", () => ({ default: () => <div>audit-trace-center</div> }));
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

describe("App task routes", () => {
  it("renders task detail route instead of falling back to dashboard", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      text: async () =>
        JSON.stringify({
          available: true,
          probe_checked: false,
          provider_name: "ollama",
        }),
    } as Response);

    render(
      <MemoryRouter initialEntries={["/console/tasks/task-123"]}>
        <App />
      </MemoryRouter>,
    );

    expect(screen.getByText("task-detail")).toBeInTheDocument();
    expect(screen.queryByText("dashboard")).not.toBeInTheDocument();

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        "/api/web/llm/status",
        expect.objectContaining({
          headers: { Accept: "application/json" },
        }),
      );
    });
  });
});

describe("App audit routes", () => {
  beforeEach(() => {
    mockFetch.mockResolvedValue({
      ok: true,
      text: async () =>
        JSON.stringify({
          available: true,
          probe_checked: false,
          provider_name: "ollama",
        }),
    } as Response);
  });

  it("renders audit trace center at /console/audit instead of model-provider replay", async () => {
    render(
      <MemoryRouter initialEntries={["/console/audit"]}>
        <App />
      </MemoryRouter>,
    );

    expect(screen.getByText("audit-trace-center")).toBeInTheDocument();
    expect(screen.queryByText("audit")).not.toBeInTheDocument();

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        "/api/web/llm/status",
        expect.objectContaining({
          headers: { Accept: "application/json" },
        }),
      );
    });
  });

  it("keeps model-provider audit replay on its dedicated route", async () => {
    render(
      <MemoryRouter initialEntries={["/console/audit/model-provider"]}>
        <App />
      </MemoryRouter>,
    );

    expect(screen.getByText("audit")).toBeInTheDocument();

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        "/api/web/llm/status",
        expect.objectContaining({
          headers: { Accept: "application/json" },
        }),
      );
    });
  });

  it("routes audit workflow and transcript replay pages before fallback", async () => {
    const workflowRender = render(
      <MemoryRouter initialEntries={["/console/audit/nine_questions/workflow"]}>
        <App />
      </MemoryRouter>,
    );
    expect(screen.getByText("audit-trace-mode-page")).toBeInTheDocument();

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        "/api/web/llm/status",
        expect.objectContaining({
          headers: { Accept: "application/json" },
        }),
      );
    });
    workflowRender.unmount();
    mockFetch.mockClear();

    render(
      <MemoryRouter initialEntries={["/console/audit/transcript-replay/trace-123"]}>
        <App />
      </MemoryRouter>,
    );
    expect(screen.getByText("transcript-replay")).toBeInTheDocument();

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        "/api/web/llm/status",
        expect.objectContaining({
          headers: { Accept: "application/json" },
        }),
      );
    });
  });
});
