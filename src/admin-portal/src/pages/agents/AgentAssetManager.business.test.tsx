import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import React from 'react';
import AgentAssetManager from "./AgentAssetManager";

// Mock window.confirm and window.alert
const mockConfirm = vi.fn(() => true);
const mockAlert = vi.fn();
window.confirm = mockConfirm;
window.alert = mockAlert;

const mockFetch = vi.fn();
global.fetch = mockFetch;

describe("AgentAssetManager - Real Business Scenarios", () => {
  beforeEach(() => {
    mockFetch.mockReset();
    mockConfirm.mockClear();
    mockAlert.mockClear();
  });

  const mockAgents = [
    {
      agent_id: "agent-1",
      name: "calc-agent",
      agent_name: "Calculator Bot",
      version: "2.0.0",
      function_description: "Handles complex math.",
      endpoint: "http://127.0.0.1:9001",
      role_tag: "worker",
      trust_level: "trusted",
      status: "idle",
      scope: ["math"],
      capabilities: [{ capability: "add", version: "1.0" }],
      latency_ms: 15,
      success_rate: 1.0,
      last_ping_at: null,
      registered_at: "2026-04-08T10:00:00Z",
      assigned_goal: "Calculate Q3 Revenue",
      inbox: [],
      receipts: [],
    },
  ];

  it("Scenario 1: Registration Flow with Validation (Normal/Abnormal)", async () => {
    // Normal Case: Successful registration
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => mockAgents } as Response);
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => [] } as Response); // Initial fetch
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => mockAgents } as Response); // Post-register fetch

    render(<AgentAssetManager />);

    await waitFor(() => expect(screen.getByText("Calculator Bot")).toBeInTheDocument());

    // Open Registration Dialog
    fireEvent.click(screen.getByText(/Add Agent Asset/i));

    // Abnormal Case: Try to continue without required fields
    const continueBtn = screen.getByText("Continue");
    expect(continueBtn).toBeDisabled();

    // Fill Step 0
    fireEvent.change(screen.getByLabelText(/Technical Name/i), { target: { value: "new-bot" } });
    fireEvent.change(screen.getByLabelText(/Human-Readable Name/i), { target: { value: "New Bot" } });
    fireEvent.change(screen.getByLabelText(/Function Description/i), { target: { value: "Testing" } });

    fireEvent.click(continueBtn);

    // Fill Step 1
    fireEvent.change(screen.getByLabelText(/Endpoint URL/i), { target: { value: "http://localhost:9999" } });
    fireEvent.click(screen.getByText("Continue"));

    // Step 2: Finalize
    fireEvent.click(screen.getByText("Finalize Registration"));

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith("/api/web/agents/register", expect.objectContaining({
        method: 'POST',
      }));
    });
  });

  it("Scenario 2: Detail Drawer & Task Pipeline Filtering (Special Case)", async () => {
    const agentWithTasks = {
      ...mockAgents[0],
      inbox: [{ task_id: "t1", title: "Pending Calc", status: "todo", idempotency_key: "k1", originator_id: "admin", remarks: null }],
      receipts: [{ task_id: "t2", title: "Old Calc", status: "done", idempotency_key: "k2", completed_at: "2026-04-08T11:00:00Z", remarks: null }],
    };

    const tasks = [
      { task_id: "t1", subtask_id: null, title: "Pending Calc", task_type: "agent_delegation", status: "todo", progress: 0.0, originator_id: "admin", remarks: null, started_at: null, completed_at: null },
      { task_id: "t3", subtask_id: null, title: "Active Task", task_type: "cognitive_step", status: "in_progress", progress: 0.5, originator_id: "system", remarks: "Running", started_at: "2026-04-08T12:00:00Z", completed_at: null },
    ];

    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => [agentWithTasks] } as Response);
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => tasks } as Response); // Fetch tasks
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => [] } as Response); // Fetch audit

    render(<AgentAssetManager />);

    await waitFor(() => expect(screen.getByText("Calculator Bot")).toBeInTheDocument());

    // Open Drawer
    fireEvent.click(screen.getByText("Calculator Bot"));

    await waitFor(() => {
      expect(screen.getByText("任务流水线 (Unified Pipeline)")).toBeInTheDocument();
    });

    // Special Case: Verify filtering logic in DataGrid
    // Initially on Tab 0 (Pending/Blocked)
    expect(screen.getByText("Pending Calc")).toBeInTheDocument();
    
    // Switch to Tab 1 (In Progress)
    fireEvent.click(screen.getByText("正在进行中"));
    await waitFor(() => {
      // Use getAllByText because the text might appear in both the list snapshot and the grid
      const activeTasks = screen.getAllByText("Active Task");
      expect(activeTasks.length).toBeGreaterThan(0);
    });
  });

  it("Scenario 3: Audit Trail Visualization (Evidence Requirement)", async () => {
    const auditEvents = [
      {
        entry_id: "e1",
        session_id: "agent-management-audit",
        turn_id: "turn-1",
        entry_type: "agent_registered",
        timestamp: "2026-04-08T10:00:10Z",
        source: "AgentCoordinationService",
        trace_id: "trace-reg-001",
        context_info: {},
        payload: { message: "registered", details: { action: "register" } },
      },
    ];

    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => mockAgents } as Response);
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => [] } as Response); // Tasks
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => auditEvents } as Response); // Audit

    render(<AgentAssetManager />);

    await waitFor(() => expect(screen.getByText("Calculator Bot")).toBeInTheDocument());

    fireEvent.click(screen.getByText("Calculator Bot"));

    // Switch to Audit Tab
    fireEvent.click(screen.getByText("审计与握手详情"));
    fireEvent.click(screen.getByText("历史记录"));

    await waitFor(() => {
      expect(screen.getByText("agent_registered")).toBeInTheDocument();
    });

    // Verify Payload Expansion
    fireEvent.click(screen.getByText("Payload（默认折叠）"));
    await waitFor(() => {
      expect(screen.getByText(/"message": "registered"/)).toBeInTheDocument();
    });
  });
});
