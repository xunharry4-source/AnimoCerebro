import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

import ZentexTaskManager from "./ZentexTaskManager";

const mockFetch = vi.fn();
class MockWebSocket {
  static instances: MockWebSocket[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  constructor(public url: string) {
    MockWebSocket.instances.push(this);
  }
  close() {}
}

global.fetch = mockFetch;
vi.stubGlobal("WebSocket", MockWebSocket as any);

describe("ZentexTaskManager", () => {
  beforeEach(() => {
    mockFetch.mockReset();
    MockWebSocket.instances = [];
  });

  it("passes source_module filter and renders workflow columns", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        in_progress: [
          {
            task_id: "upgrade-1",
            subtask_id: "sub-upgrade-1",
            idempotency_key: "upgrade:1",
            title: "Planner prompt upgrade",
            task_type: "system_action",
            status: "in_progress",
            priority: "high",
            progress: 0.72,
            originator_id: "upgrade.execution_service",
            remarks: "Upgrade status -> validating",
            started_at: "2026-04-18T10:00:00Z",
            completed_at: null,
            created_at: "2026-04-18T09:00:00Z",
            metadata: {
              source_module: "upgrade",
              workflow_status: "validating",
              workflow_progress: 72,
            },
          },
        ],
        pending: [],
        waiting_confirmation: [],
        completed: [],
        cancelled: [],
      }),
    } as Response);

    render(<ZentexTaskManager />);

    await waitFor(() => {
      expect(screen.getByText("Planner prompt upgrade")).toBeInTheDocument();
    });

    expect(screen.getByText("来源")).toBeInTheDocument();
    expect(screen.getByText("工作流状态")).toBeInTheDocument();
    expect(screen.getByText("upgrade")).toBeInTheDocument();
    expect(screen.getByText("validating")).toBeInTheDocument();

    fireEvent.mouseDown(screen.getByLabelText("来源模块"));
    fireEvent.click(screen.getByText("升级"));

    await waitFor(() => {
      expect(mockFetch).toHaveBeenLastCalledWith("/api/web/tasks/by-status?source_module=upgrade");
    });
  });
});
