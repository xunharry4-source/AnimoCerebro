import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import Q3Detail from "./Q3Detail";
import * as api from "../nineQuestionsApi";

vi.mock("../nineQuestionsApi", async () => {
  const actual = await vi.importActual("../nineQuestionsApi");
  return {
    ...actual,
    fetchNineQuestionSummary: vi.fn(),
    fetchNineQuestionEvidence: vi.fn(),
    fetchNineQuestionInference: vi.fn(),
    fetchNineQuestionTracePayload: vi.fn(),
    fetchNineQuestionRaw: vi.fn(),
    fetchNineQuestionModules: vi.fn(),
  };
});

describe("Q3Detail business tests", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows mounted plugins and resource sufficiency values from partitioned Q3 results", async () => {
    vi.mocked(api.fetchNineQuestionSummary).mockResolvedValue({
      status: "completed",
      question_id: "q3",
    } as any);
    vi.mocked(api.fetchNineQuestionEvidence).mockResolvedValue({
      workspace_permission: {
        workspaces: ["workspace-a"],
        tenant_permissions: ["read", "write"],
        execution_tokens: ["token-a"],
      },
      tools_agents: {
        connected_agents: [{ agent_id: "agent-a", status: "online" }],
        cognitive_tool_rows: [],
        execution_tool_rows: [],
        connected_agent_rows: [],
        mcp_servers: [],
        cli_tools: [],
      },
      memory_strategy: {
        experience_logs: ["incident-1"],
        strategy_patches: ["patch-a"],
      },
    } as any);
    vi.mocked(api.fetchNineQuestionInference).mockResolvedValue({
      sufficiency_assessment: {
        resource_status: "sufficient",
        missing_critical_assets: [],
        bottleneck_node: "agent_layer",
        reasoning_summary: "Core runtime assets are available.",
      },
    } as any);
    vi.mocked(api.fetchNineQuestionTracePayload).mockResolvedValue({
      provider_name: "provider-tools-default",
      elapsed_ms: 52,
      token_usage: { input_tokens: 12, output_tokens: 6, total_tokens: 18 },
      context_data: {},
    } as any);
    vi.mocked(api.fetchNineQuestionRaw).mockResolvedValue({
      trace_id: "trace-q3-business",
      tool_id: "nine_questions.q3",
      mounted_plugins: [
        {
          plugin_id: "nine-question-q3-what-do-i-have",
          description: "Q3 inventory plugin",
          version: "1.0.0",
          status: "active",
          source_kind: "base",
        },
      ],
    } as any);
    vi.mocked(api.fetchNineQuestionModules).mockResolvedValue({
      status: { status: "completed" },
    } as any);

    render(
      <MemoryRouter initialEntries={["/console/nine-questions/q3"]}>
        <Routes>
          <Route path="/console/nine-questions/q3" element={<Q3Detail />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("q3-detail-root")).toBeInTheDocument();
    });

    expect(screen.getByText(/Core runtime assets are available/)).toBeInTheDocument();
    expect(screen.getByTestId("mounted-plugin-nine-question-q3-what-do-i-have")).toBeInTheDocument();
    expect(screen.getByText(/资源状态/)).toBeInTheDocument();
  });
});
