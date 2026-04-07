import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import McpServerDashboard from "./McpServerDashboard";

const mockFetch = vi.fn();
globalThis.fetch = mockFetch;

describe("McpServerDashboard", () => {
  beforeEach(() => {
    mockFetch.mockReset();
  });

  it("renders MCP servers in DataGrid and shows tool domain chips in drawer", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => [
        {
          server_id: "knowledge-hub",
          transport_type: "stdio",
          status: "online",
          tool_count: 1,
          tools: [
            {
              tool_name: "search_documents",
              description: "Search indexed runbooks",
              mapped_domain: "cognitive",
              plugin_id: "mcp:knowledge-hub:search_documents",
              feature_code: "mcp.knowledge-hub.search_documents",
              read_only: true,
              side_effect_free: true,
              mutates_state: false,
              requires_cloud_audit: false,
              status: "active",
            },
          ],
        },
        {
          server_id: "ops-bridge",
          transport_type: "sse",
          status: "degraded",
          tool_count: 1,
          error_message: "transport disconnected",
          tools: [
            {
              tool_name: "update_ticket",
              description: "Update external incident ticket",
              mapped_domain: "execution",
              plugin_id: "mcp:ops-bridge:update_ticket",
              feature_code: "mcp.ops-bridge.update_ticket",
              execution_domain: "mcp",
              read_only: false,
              side_effect_free: false,
              mutates_state: true,
              requires_cloud_audit: true,
              status: "active",
            },
          ],
        },
      ],
    } as Response);

    render(<McpServerDashboard />);

    await waitFor(() => {
      expect(screen.getByText("knowledge-hub")).toBeInTheDocument();
    });

    expect(screen.getByText("ops-bridge")).toBeInTheDocument();
    expect(screen.getByText("stdio")).toBeInTheDocument();
    expect(screen.getByText("sse")).toBeInTheDocument();

    fireEvent.click(screen.getByText("ops-bridge"));

    await waitFor(() => {
      expect(screen.getByText("工具清单")).toBeInTheDocument();
    });

    expect(screen.getByText("物理执行")).toBeInTheDocument();
    expect(screen.getByText("CloudAudit")).toBeInTheDocument();
    expect(screen.getByText("Update external incident ticket")).toBeInTheDocument();
    expect(screen.getByText("transport disconnected")).toBeInTheDocument();
  });

  it("registers an MCP server and executes a test call", async () => {
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => [],
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          server_id: "knowledge-hub",
          transport_type: "stdio",
          status: "online",
          tool_count: 1,
          tools: [
            {
              tool_name: "search_documents",
              description: "Search indexed runbooks",
              mapped_domain: "cognitive",
              plugin_id: "mcp:knowledge-hub:search_documents",
              feature_code: "mcp.knowledge-hub.search_documents",
              read_only: true,
              side_effect_free: true,
              mutates_state: false,
              requires_cloud_audit: false,
              status: "active",
            },
          ],
        }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => [
          {
            server_id: "knowledge-hub",
            transport_type: "stdio",
            status: "online",
            tool_count: 1,
            tools: [
              {
                tool_name: "search_documents",
                description: "Search indexed runbooks",
                mapped_domain: "cognitive",
                plugin_id: "mcp:knowledge-hub:search_documents",
                feature_code: "mcp.knowledge-hub.search_documents",
                read_only: true,
                side_effect_free: true,
                mutates_state: false,
                requires_cloud_audit: false,
                status: "active",
              },
            ],
          },
        ],
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          server_id: "knowledge-hub",
          tool_name: "search_documents",
          trace_id: "trace-1",
          payload: { summary: "search completed", hits: ["runbook-42"] },
        }),
      } as Response);

    render(<McpServerDashboard />);

    await waitFor(() => expect(screen.getByText("注册 Server")).toBeInTheDocument());

    fireEvent.click(screen.getByText("注册 Server"));
    fireEvent.change(screen.getByLabelText("Server ID"), { target: { value: "knowledge-hub" } });
    fireEvent.change(screen.getByLabelText("Transport"), { target: { value: "stdio" } });
    fireEvent.change(screen.getByLabelText("Command / URL"), { target: { value: "uvx" } });
    fireEvent.click(screen.getByText("确认注册"));

    await waitFor(() => expect(screen.getByText("knowledge-hub")).toBeInTheDocument());

    fireEvent.click(screen.getByText("knowledge-hub"));

    await waitFor(() => expect(screen.getByText("工具清单")).toBeInTheDocument());

    fireEvent.click(screen.getByText("选择用于测试"));
    fireEvent.click(screen.getByText("执行测试"));

    await waitFor(() => expect(screen.getByText(/runbook-42/)).toBeInTheDocument());
  });
});
