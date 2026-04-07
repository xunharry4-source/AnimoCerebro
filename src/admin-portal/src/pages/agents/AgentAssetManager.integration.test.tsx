import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import React from 'react';
import AgentAssetManager from "./AgentAssetManager";

// Mock window.confirm
const mockConfirm = vi.fn(() => true);
window.confirm = mockConfirm;

const mockFetch = vi.fn();
global.fetch = mockFetch;

describe("AgentAssetManager Lifecycle Integration", () => {
  beforeEach(() => {
    mockFetch.mockReset();
    mockConfirm.mockClear();
  });

  const mockAgent = {
    agent_id: "test-agent-123",
    name: "test-agent",
    agent_name: "Random Number Agent",
    version: "1.0.0",
    function_description: "Handles math.",
    endpoint: "http://127.0.0.1:9201",
    role_tag: "worker",
    trust_level: "trusted",
    status: "idle",
    scope: ["math"],
    capabilities: [],
    latency_ms: 10,
    success_rate: 1.0,
    last_ping_at: null,
    registered_at: "2026-04-05T00:00:00Z",
    inbox: [],
    assigned_goal: null,
    receipts: [],
  };

  it("Task 2: allows revoking trust and reflects the 'revoked' status (Red Chip)", async () => {
    mockFetch
      .mockResolvedValueOnce({ ok: true, json: async () => [mockAgent] }) // Initial List
      .mockResolvedValueOnce({ ok: true, json: async () => [] }) // Tasks for drawer
      .mockResolvedValueOnce({ ok: true, json: async () => [] }) // Audit for drawer
      .mockResolvedValueOnce({ 
        ok: true, 
        json: async () => ({ ...mockAgent, trust_level: 'revoked' }) 
      }); // PATCH response

    render(<AgentAssetManager />);

    // Click to open drawer
    await waitFor(() => {
      fireEvent.click(screen.getByText("Random Number Agent"));
    });

    // Find and click Revoke button
    const revokeBtn = screen.getByText("Revoke Trust (Block)");
    fireEvent.click(revokeBtn);

    // Verify PATCH call
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        "/api/web/agents/test-agent-123/policy",
        expect.objectContaining({
          method: 'PATCH',
          body: JSON.stringify({ trust_level: 'revoked', scope: ['math'] })
        })
      );
    });

    // Verify the UI update (Red Chip is 'error' color in MUI, which is handled by TrustLevelChip)
    // The chip label will be REVOKED
    expect(screen.getByText("REVOKED")).toBeInTheDocument();
  });

  it("Task 3: allows deleting an agent and removes it from the UI", async () => {
    mockFetch
      .mockResolvedValueOnce({ ok: true, json: async () => [mockAgent] }) // Initial List
      .mockResolvedValueOnce({ ok: true, json: async () => [] }) // Tasks
      .mockResolvedValueOnce({ ok: true, json: async () => [] }) // Audit
      .mockResolvedValueOnce({ ok: true, json: async () => ({ status: 'deleted' }) }) // DELETE response
      .mockResolvedValueOnce({ ok: true, json: async () => [] }); // Final List Refresh (empty)

    render(<AgentAssetManager />);

    // Click to open drawer
    await waitFor(() => {
      fireEvent.click(screen.getByText("Random Number Agent"));
    });

    // Click Delete button
    const deleteBtn = screen.getByText("Delete Asset");
    fireEvent.click(deleteBtn);

    // Assert confirmation was called
    expect(mockConfirm).toHaveBeenCalled();

    // Verify DELETE call
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        "/api/web/agents/test-agent-123",
        expect.objectContaining({ method: 'DELETE' })
      );
    });

    // Verify that the list was refreshed and the agent is gone
    await waitFor(() => {
      expect(screen.queryByText("Random Number Agent")).not.toBeInTheDocument();
    });
  });
});
