import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

import AgentAssetManager from "./AgentAssetManager";

const mockFetch = vi.fn();
global.fetch = mockFetch;

describe("AgentAssetManager", () => {
  beforeEach(() => {
    mockFetch.mockReset();
  });

  it("renders real agent summaries, inbox and task rows from backend payload", async () => {
    const agent = {
      agent_id: "agent-1",
      name: "agent-1",
      agent_name: "Build Bot",
      version: "1.2.3",
      function_description: "Handles CI and build tasks.",
      endpoint: "http://127.0.0.1:9999",
      role_tag: "worker",
      trust_level: "trusted",
      status: "active",
      scope: ["general"],
      capabilities: [{ capability: "build", version: "1.0" }],
      latency_ms: 12,
      success_rate: 0.99,
      last_ping_at: null,
      registered_at: "2026-04-04T12:00:00Z",
      assigned_goal: "Compile release candidate",
      inbox: [
        {
          task_id: "t1",
          title: "Compile",
          status: "todo",
          idempotency_key: "k1",
          originator_id: "operator",
          remarks: "Need new artifact",
        },
      ],
      receipts: [
        {
          task_id: "t9",
          title: "Archive build log",
          status: "done",
          idempotency_key: "r9",
          completed_at: "2026-04-04T12:09:00Z",
          remarks: "Archived",
        },
      ],
    };

    const agents = [
      agent,
      {
        ...agent,
        agent_id: "agent-2",
        name: "agent-2",
        agent_name: "Audit Bot",
        assigned_goal: "Review receipts",
        inbox: [],
        receipts: [],
      },
      {
        ...agent,
        agent_id: "agent-3",
        name: "agent-3",
        agent_name: "Memory Bot",
        assigned_goal: "Store summaries",
        inbox: [],
        receipts: [],
      },
    ];

    const tasks = [
      {
        task_id: "t1",
        subtask_id: "st1",
        title: "Compile",
        task_type: "system_action",
        status: "in_progress",
        progress: 0.42,
        originator_id: "operator",
        remarks: null,
        started_at: "2026-04-04T12:01:00Z",
        completed_at: null,
      },
      {
        task_id: "t2",
        subtask_id: "st2",
        title: "Test",
        task_type: "cognitive_step",
        status: "blocked",
        progress: 0.1,
        originator_id: "operator",
        remarks: "Waiting for env",
        started_at: null,
        completed_at: null,
      },
    ];

    const auditEvents = [
      {
        entry_id: "e1",
        session_id: "agent-management-audit",
        turn_id: "turn-1",
        entry_type: "agent_registered",
        timestamp: "2026-04-04T12:00:10Z",
        source: "AgentCoordinationService",
        trace_id: "trace-1",
        context_info: {},
        payload: { message: "registered", details: { action: "register" } },
      },
    ];

    mockFetch
      .mockResolvedValueOnce({ ok: true, json: async () => agents } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => tasks } as Response)
      .mockResolvedValueOnce({ ok: true, json: async () => auditEvents } as Response);

    render(<AgentAssetManager />);

    await waitFor(() => {
      expect(screen.getByText("Build Bot")).toBeInTheDocument();
    });

    expect(screen.getByText("Audit Bot")).toBeInTheDocument();
    expect(screen.getByText("Memory Bot")).toBeInTheDocument();
    expect(screen.getByText("Assigned Goal: Compile release candidate")).toBeInTheDocument();
    expect(screen.getByText("Inbox: 1 | Receipts: 1")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Build Bot"));

    await waitFor(() => {
      expect(screen.getByText("任务流水线 (Unified Pipeline)")).toBeInTheDocument();
    });

    // DataGrid column assertions (anti-cheat: must render high-density columns)
    expect(screen.getByText("任务ID")).toBeInTheDocument();
    expect(screen.getByText("任务子ID")).toBeInTheDocument();
    expect(screen.getByText("任务名称")).toBeInTheDocument();
    expect(screen.getByText("任务类型")).toBeInTheDocument();
    expect(screen.getByText("任务状态")).toBeInTheDocument();
    expect(screen.getByText("任务进度")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText("Test")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText("正在进行中"));
    await waitFor(() => {
      expect(screen.getAllByText("Compile").length).toBeGreaterThan(0);
    });

    fireEvent.click(screen.getByText("审计与握手详情"));
    await waitFor(() => {
      expect(screen.getByText("todo | k1 | Need new artifact")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText("历史记录"));
    await waitFor(() => {
      expect(screen.getByText("Archive build log")).toBeInTheDocument();
    });
  });
});
