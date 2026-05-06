import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import Q2Detail from "./Q2Detail";

vi.mock("../nineQuestionsApi", () => ({
  fetchQ2AssetStatistics: vi.fn(async () => ({
    internal_plugin_count: 3,
    cli_count: 2,
    mcp_count: 4,
    agent_count: 5,
    external_service_count: 6,
    total_count: 20,
  })),
  fetchQ2LlmTrace: vi.fn(async () => ({
    question_id: "q2",
    token_usage: { input_tokens: 5, output_tokens: 7, total_tokens: 12 },
    internal_tool_llm: {
      provider_name: "internal-provider",
      token_usage: { input_tokens: 1, output_tokens: 2, total_tokens: 3 },
      input_llm: {
        system_prompt: "internal system prompt",
        prompt: "internal prompt",
        context_data: { Internal_Plugins: ["memory"] },
      },
      output_llm: { InternalAssetInventory: { internal_cognitive_tools: ["memory"] } },
    },
    external_tool_llm: {
      provider_name: "external-provider",
      token_usage: { input_tokens: 4, output_tokens: 5, total_tokens: 9 },
      input_llm: {
        system_prompt: "external system prompt",
        prompt: "external prompt",
        context_data: { CLI_Tools: ["playwright-cli"] },
      },
      output_llm: { ExternalAssetInventory: { available_external_tools: ["playwright-cli"] } },
    },
  })),
  getQuestionDisplayLabel: vi.fn(() => "Q2 我有什么"),
  runSingleNineQuestion: vi.fn(),
}));

describe("Q2Detail", () => {
  it("links asset statistics counts to their asset management pages", async () => {
    render(
      <MemoryRouter>
        <Q2Detail />
      </MemoryRouter>,
    );

    await screen.findByTestId("q2-asset-statistics-card");

    expect(screen.getByRole("link", { name: "内部插件: 3，打开插件页面" })).toHaveAttribute("href", "/console/plugins");
    expect(screen.getByRole("link", { name: "CLI: 2，打开CLI 页面" })).toHaveAttribute("href", "/console/cli-tools");
    expect(screen.getByRole("link", { name: "MCP: 4，打开MCP 页面" })).toHaveAttribute("href", "/console/mcp-servers");
    expect(screen.getByRole("link", { name: "Agent: 5，打开Agent 页面" })).toHaveAttribute("href", "/console/agents");
    expect(screen.getByRole("link", { name: "外接服务: 6，打开外接服务页面" })).toHaveAttribute("href", "/console/external-connectors");
    expect(screen.getByTestId("q2-stat-cli-count")).toHaveTextContent("CLI: 2");
    expect(screen.getByTestId("q2-stat-total-count")).toHaveTextContent("总计: 20");
  });

  it("renders q2 llm provider, token, input and output sections", async () => {
    render(
      <MemoryRouter>
        <Q2Detail />
      </MemoryRouter>,
    );

    await screen.findByText("Provider / Token");

    expect(screen.getByText("Provider: internal-provider")).toBeInTheDocument();
    expect(screen.getByText("Provider: external-provider")).toBeInTheDocument();
    expect(screen.getByText("内部 LLM")).toBeInTheDocument();
    expect(screen.getByText("外部 LLM")).toBeInTheDocument();
    expect(screen.getAllByText("输入 LLM").length).toBe(2);
    expect(screen.getAllByText("输出 LLM").length).toBe(2);
    expect(screen.getByText(/internal prompt/)).toBeInTheDocument();
    expect(screen.getAllByText(/playwright-cli/).length).toBeGreaterThan(0);
  });
});
