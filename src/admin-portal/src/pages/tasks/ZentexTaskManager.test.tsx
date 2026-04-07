import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

import ZentexTaskManager from "./ZentexTaskManager";

const mockFetch = vi.fn();
global.fetch = mockFetch;

describe("ZentexTaskManager", () => {
  beforeEach(() => {
    mockFetch.mockReset();
  });

  it("renders real task rows from backend payload", async () => {
    const tasks = [
      {
        task_id: "t1",
        subtask_id: "st1",
        idempotency_key: "k1",
        title: "Compile",
        task_type: "system_action",
        status: "in_progress",
        progress: 0.25,
        originator_id: "operator",
        remarks: null,
        started_at: "2026-04-04T12:01:00Z",
        completed_at: null,
      },
      {
        task_id: "t2",
        subtask_id: "st2",
        idempotency_key: "k2",
        title: "Run E2E",
        task_type: "cognitive_step",
        status: "blocked",
        progress: 0.5,
        originator_id: "audit-bot",
        remarks: "Waiting for credentials",
        started_at: "2026-04-04T12:02:00Z",
        completed_at: null,
      },
      {
        task_id: "t3",
        subtask_id: "st3",
        idempotency_key: "k3",
        title: "Publish Receipt",
        task_type: "intervention",
        status: "done",
        progress: 1,
        originator_id: "memory-bot",
        remarks: "Receipt archived",
        started_at: "2026-04-04T12:03:00Z",
        completed_at: "2026-04-04T12:04:00Z",
      },
    ];

    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => tasks } as Response);

    render(<ZentexTaskManager />);

    await waitFor(() => {
      expect(screen.getByText("Zentex 独立任务管理中心")).toBeInTheDocument();
    });

    expect(screen.getByText("任务ID")).toBeInTheDocument();
    expect(screen.getByText("子ID")).toBeInTheDocument();
    expect(screen.getByText("任务标题")).toBeInTheDocument();
    expect(screen.getByText("任务类型")).toBeInTheDocument();
    expect(screen.getByText("状态")).toBeInTheDocument();
    expect(screen.getByText("进度")).toBeInTheDocument();
    expect(screen.getByText("人工干预")).toBeInTheDocument();
    expect(screen.getByText("Compile (t1)")).toBeInTheDocument();
    expect(screen.getByText("Run E2E (t2)")).toBeInTheDocument();
    expect(screen.getByText("Publish Receipt (t3)")).toBeInTheDocument();
    expect(screen.getByText("blocked | k2 | Waiting for credentials")).toBeInTheDocument();
    expect(screen.getByText("done | k3 | Receipt archived")).toBeInTheDocument();
  });

  it("opens intervene dialog and requires idempotency_key", async () => {
    const tasks = [
      {
        task_id: "t1",
        subtask_id: "st1",
        idempotency_key: "k1",
        title: "Compile",
        task_type: "system_action",
        status: "in_progress",
        progress: 0.25,
        originator_id: "operator",
        remarks: null,
        started_at: "2026-04-04T12:01:00Z",
        completed_at: null,
      },
    ];

    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => tasks } as Response);

    render(<ZentexTaskManager />);

    await waitFor(() => {
      expect(screen.getByText("Compile")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByLabelText("pause-task"));

    await waitFor(() => {
      expect(screen.getByText(/确认干预: pause/i)).toBeInTheDocument();
    });

    expect(screen.getByLabelText(/idempotency_key/i)).toBeInTheDocument();
    expect(screen.getByText("Confirm Action")).toBeEnabled();
  });
});
