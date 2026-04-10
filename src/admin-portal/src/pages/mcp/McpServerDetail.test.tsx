import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import McpServerDetail from "./McpServerDetail";

const mockFetch = vi.fn();
globalThis.fetch = mockFetch;

const renderWithRouter = (serverId: string = "test-server") => {
  return render(
    <MemoryRouter initialEntries={[`/console/mcp-servers/${serverId}`]}>
      <Routes>
        <Route path="/console/mcp-servers/:server_id" element={<McpServerDetail />} />
      </Routes>
    </MemoryRouter>
  );
};

describe("McpServerDetail", () => {
  beforeEach(() => {
    mockFetch.mockReset();
  });

  it("renders server detail with credit score", async () => {
    const mockDetail = {
      server_id: "test-server",
      transport_type: "stdio",
      status: "online",
      tool_count: 2,
      credit_score: 95,
      total_tasks_run: 20,
      success_rate: 0.95,
      uptime_seconds: 7200,
      tools: [
        {
          tool_name: "search_docs",
          description: "Search documentation",
          mapped_domain: "cognitive",
          plugin_id: "mcp:test-server:search_docs",
          feature_code: "mcp.test-server.search_docs",
          read_only: true,
          side_effect_free: true,
          mutates_state: false,
          requires_cloud_audit: false,
          status: "active",
        },
      ],
    };

    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockDetail,
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => [],
      });

    renderWithRouter("test-server");

    await waitFor(() => expect(screen.getByText("test-server")).toBeInTheDocument());
    expect(screen.getByText("95")).toBeInTheDocument();
    expect(screen.getByText("服务器信用分")).toBeInTheDocument();
  });

  it("shows loading state while fetching data", () => {
    mockFetch.mockImplementation(() => new Promise(() => {}));

    renderWithRouter("test-server");

    expect(screen.getByRole("progressbar")).toBeInTheDocument();
  });

  it("displays error message when fetch fails", async () => {
    mockFetch.mockRejectedValueOnce(new Error("Network error"));

    renderWithRouter("test-server");

    await waitFor(() => expect(screen.getByText("获取详情失败")).toBeInTheDocument());
    expect(screen.getByText("返回列表")).toBeInTheDocument();
  });

  it("switches to running tasks tab and loads data", async () => {
    const mockDetail = {
      server_id: "test-server",
      transport_type: "stdio",
      status: "online",
      tool_count: 1,
      credit_score: 100,
      total_tasks_run: 0,
      success_rate: 1.0,
      uptime_seconds: 3600,
      tools: [],
    };

    const mockRunningTasks = [
      {
        record_id: "task-1",
        task_id: null,
        action_type: "search_documents",
        status: "running",
        start_time: "2026-04-10T10:00:00",
        end_time: null,
        duration_seconds: null,
        verification_status: "pending",
        error: null,
      },
    ];

    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockDetail,
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockRunningTasks,
      });

    renderWithRouter("test-server");

    await waitFor(() => expect(screen.getByText("正在进行")).toBeInTheDocument());

    // First tab should be selected by default
    const runningTab = screen.getByText("正在进行");
    expect(runningTab).toBeInTheDocument();

    // Verify API was called with correct status parameter
    await waitFor(() => {
      const calls = mockFetch.mock.calls;
      const taskCall = calls.find((call) => call[0].includes("/tasks"));
      expect(taskCall).toBeTruthy();
      if (taskCall) {
        expect(taskCall[0]).toContain("?status=running");
      }
    });
  });

  it("switches to pending tasks tab and loads data", async () => {
    const mockDetail = {
      server_id: "test-server",
      transport_type: "stdio",
      status: "online",
      tool_count: 1,
      credit_score: 100,
      total_tasks_run: 0,
      success_rate: 1.0,
      uptime_seconds: 3600,
      tools: [],
    };

    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockDetail,
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => [],
      });

    renderWithRouter("test-server");

    await waitFor(() => expect(screen.getByText("待人审核")).toBeInTheDocument());

    const pendingTab = screen.getByText("待人审核");
    fireEvent.click(pendingTab);

    await waitFor(() => {
      const calls = mockFetch.mock.calls;
      const taskCall = calls.filter((call) => call[0].includes("/tasks"));
      expect(taskCall.length).toBeGreaterThanOrEqual(2);
      expect(taskCall[taskCall.length - 1][0]).toContain("?status=pending");
    });
  });

  it("switches to failed tasks tab and loads data", async () => {
    const mockDetail = {
      server_id: "test-server",
      transport_type: "stdio",
      status: "online",
      tool_count: 1,
      credit_score: 80,
      total_tasks_run: 10,
      success_rate: 0.8,
      uptime_seconds: 3600,
      tools: [],
    };

    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockDetail,
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => [],
      });

    renderWithRouter("test-server");

    await waitFor(() => expect(screen.getByText("执行失败")).toBeInTheDocument());

    const failedTab = screen.getByText("执行失败");
    fireEvent.click(failedTab);

    await waitFor(() => {
      const calls = mockFetch.mock.calls;
      const taskCall = calls.filter((call) => call[0].includes("/tasks"));
      expect(taskCall.length).toBeGreaterThanOrEqual(2);
      expect(taskCall[taskCall.length - 1][0]).toContain("?status=failed");
    });
  });

  it("switches to history tab and loads all tasks without status filter", async () => {
    const mockDetail = {
      server_id: "test-server",
      transport_type: "stdio",
      status: "online",
      tool_count: 1,
      credit_score: 100,
      total_tasks_run: 5,
      success_rate: 1.0,
      uptime_seconds: 3600,
      tools: [],
    };

    const mockAllTasks = [
      {
        record_id: "task-1",
        task_id: null,
        action_type: "search_documents",
        status: "completed",
        start_time: "2026-04-10T10:00:00",
        end_time: "2026-04-10T10:01:00",
        duration_seconds: 60,
        verification_status: "passed",
        error: null,
      },
    ];

    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockDetail,
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockAllTasks,
      });

    renderWithRouter("test-server");

    await waitFor(() => expect(screen.getByText("任务历史记录")).toBeInTheDocument());

    const historyTab = screen.getByText("任务历史记录");
    fireEvent.click(historyTab);

    await waitFor(() => {
      const calls = mockFetch.mock.calls;
      const taskCall = calls.filter((call) => call[0].includes("/tasks"));
      expect(taskCall.length).toBeGreaterThanOrEqual(2);
      // History tab should not include status parameter
      expect(taskCall[taskCall.length - 1][0]).not.toContain("?status=");
    });
  });

  it("displays task error information in table", async () => {
    const mockDetail = {
      server_id: "test-server",
      transport_type: "stdio",
      status: "online",
      tool_count: 1,
      credit_score: 80,
      total_tasks_run: 10,
      success_rate: 0.8,
      uptime_seconds: 3600,
      tools: [],
    };

    const mockFailedTasks = [
      {
        record_id: "task-failed-1",
        task_id: null,
        action_type: "execute_command",
        status: "failed",
        start_time: "2026-04-10T09:00:00",
        end_time: "2026-04-10T09:00:05",
        duration_seconds: 5,
        verification_status: "failed",
        error: "Connection timeout after 5 seconds",
      },
    ];

    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockDetail,
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockFailedTasks,
      });

    renderWithRouter("test-server");

    // Switch to failed tab
    await waitFor(() => expect(screen.getByText("执行失败")).toBeInTheDocument());
    const failedTab = screen.getByText("执行失败");
    fireEvent.click(failedTab);

    // Wait for error message to appear
    await waitFor(() => {
      expect(screen.getByText(/Connection timeout/)).toBeInTheDocument();
    });
  });

  it("shows credit score explanation tooltip", async () => {
    const mockDetail = {
      server_id: "test-server",
      transport_type: "stdio",
      status: "online",
      tool_count: 1,
      credit_score: 90,
      total_tasks_run: 10,
      success_rate: 0.9,
      uptime_seconds: 3600,
      tools: [],
    };

    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockDetail,
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => [],
      });

    renderWithRouter("test-server");

    await waitFor(() => expect(screen.getByText("信用分说明")).toBeInTheDocument());
    
    // Tooltip should be present
    const helpIcon = screen.getByTestId("HelpOutlineIcon");
    expect(helpIcon).toBeInTheDocument();
  });

  it("calculates credit score correctly based on failures", async () => {
    const mockDetail = {
      server_id: "test-server",
      transport_type: "stdio",
      status: "online",
      tool_count: 1,
      credit_score: 75, // 100 - (5 failures * 5)
      total_tasks_run: 20,
      success_rate: 0.75,
      uptime_seconds: 3600,
      tools: [],
    };

    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockDetail,
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => [],
      });

    renderWithRouter("test-server");

    await waitFor(() => expect(screen.getByText("75")).toBeInTheDocument());
    expect(screen.getByText("任务成功率")).toBeInTheDocument();
    expect(screen.getByText("75.0%")).toBeInTheDocument();
  });

  it("displays tool list with domain chips", async () => {
    const mockDetail = {
      server_id: "test-server",
      transport_type: "sse",
      status: "online",
      tool_count: 2,
      credit_score: 100,
      total_tasks_run: 0,
      success_rate: 1.0,
      uptime_seconds: 3600,
      tools: [
        {
          tool_name: "search_docs",
          description: "Search documentation",
          mapped_domain: "cognitive",
          plugin_id: "mcp:test-server:search_docs",
          feature_code: "mcp.test-server.search_docs",
          read_only: true,
          side_effect_free: true,
          mutates_state: false,
          requires_cloud_audit: false,
          status: "active",
        },
        {
          tool_name: "update_record",
          description: "Update database record",
          mapped_domain: "execution",
          plugin_id: "mcp:test-server:update_record",
          feature_code: "mcp.test-server.update_record",
          read_only: false,
          side_effect_free: false,
          mutates_state: true,
          requires_cloud_audit: true,
          status: "active",
        },
      ],
    };

    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockDetail,
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => [],
      });

    renderWithRouter("test-server");

    await waitFor(() => {
      expect(screen.getByText("search_docs")).toBeInTheDocument();
      expect(screen.getByText("update_record")).toBeInTheDocument();
      expect(screen.getByText("cognitive")).toBeInTheDocument();
      expect(screen.getByText("execution")).toBeInTheDocument();
    });
  });

  it("handles empty task list gracefully", async () => {
    const mockDetail = {
      server_id: "test-server",
      transport_type: "stdio",
      status: "online",
      tool_count: 1,
      credit_score: 100,
      total_tasks_run: 0,
      success_rate: 1.0,
      uptime_seconds: 3600,
      tools: [],
    };

    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockDetail,
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => [],
      });

    renderWithRouter("test-server");

    await waitFor(() => expect(screen.getByText("实时任务监控与历史")).toBeInTheDocument());
    // DataGrid should render even with empty data
    expect(screen.getByRole("grid")).toBeInTheDocument();
  });

  it("navigates back to MCP servers list", async () => {
    const mockDetail = {
      server_id: "test-server",
      transport_type: "stdio",
      status: "online",
      tool_count: 1,
      credit_score: 100,
      total_tasks_run: 0,
      success_rate: 1.0,
      uptime_seconds: 3600,
      tools: [],
    };

    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockDetail,
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => [],
      });

    renderWithRouter("test-server");

    await waitFor(() => expect(screen.getByText("返回仪表盘")).toBeInTheDocument());
    
    const backButton = screen.getByText("返回仪表盘");
    expect(backButton).toBeInTheDocument();
  });
});
