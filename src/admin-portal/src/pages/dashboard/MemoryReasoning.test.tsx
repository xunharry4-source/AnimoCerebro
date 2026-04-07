import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import MemoryReasoning from "./MemoryReasoning";

const mockFetch = vi.fn();
global.fetch = mockFetch;

describe("MemoryReasoning", () => {
  beforeEach(() => {
    mockFetch.mockReset();
  });

  it("renders manageable memory records and applies governance actions", async () => {
    mockFetch.mockImplementation(async (input: RequestInfo, init?: RequestInit) => {
      const url = String(input);
      if (url === "/api/web/cognitive-agenda") {
        return {
          ok: true,
          json: async () => ({
            state: { state_id: "agenda-1", review_now_item_ids: [], overdue_item_ids: [] },
            items: [],
          }),
        } as Response;
      }
      if (url === "/api/web/memory/enhanced/overview") {
        return {
          ok: true,
          json: async () => ({
            semantic_count: 4,
            procedural_count: 2,
            episodic_count: 3,
            active_count: 6,
            deprecated_count: 1,
            archived_count: 0,
            suspect_count: 1,
            projection_failures: [],
            backends: [
              {
                backend: "external_semantic_bridge",
                package_name: null,
                package_installed: true,
                write_enabled: true,
                recall_enabled: false,
                mode: "adapter",
                detail: "Projects semantic/procedural memory into the configured external store.",
              },
            ],
          }),
        } as Response;
      }
      if (url.startsWith("/api/web/memory/enhanced/records")) {
        return {
          ok: true,
          json: async () => ({
            layer: "all",
            limit: 30,
            items: [
              {
                memory_id: "mem-1",
                memory_layer: "semantic",
                source_kind: "upgrade",
                title: "Plugin upgrade for router",
                summary: "Plugin upgrade completed successfully.",
                content: "content",
                trace_id: "trace-1",
                version_id: "1.2.1-candidate",
                tags: ["plugin", "upgrade"],
                source_refs: ["src-1"],
                evidence_refs: [],
                payload: {},
                status: "active",
                visibility: "internal",
                trust_level: "unverified",
                management_note: "Projected from upgrade.",
                correction_note: null,
                supersedes_memory_id: null,
                superseded_by_memory_id: null,
                operator: "system",
                last_action: "ingested",
                last_action_reason: "Projected from upgrade semantic evidence.",
                last_verified_at: null,
                updated_at: "2026-04-06T00:10:00Z",
                created_at: "2026-04-06T00:00:00Z",
              },
            ],
          }),
        } as Response;
      }
      if (url.startsWith("/api/web/memory/enhanced/search")) {
        return {
          ok: true,
          json: async () => ({
            query: "router",
            limit: 10,
            items: [
              {
                memory_id: "mem-1",
                memory_layer: "semantic",
                source_kind: "upgrade",
                title: "Plugin upgrade for router",
                summary: "Plugin upgrade completed successfully.",
                trace_id: "trace-1",
                score: 0.9,
                tags: ["plugin", "upgrade"],
                source_refs: ["src-1"],
              },
            ],
          }),
        } as Response;
      }
      if (url === "/api/web/memory/enhanced/mem-1") {
        return {
          ok: true,
          json: async () => ({
            memory_id: "mem-1",
            memory_layer: "semantic",
            source_kind: "upgrade",
            title: "Plugin upgrade for router",
            summary: "Plugin upgrade completed successfully.",
            content: "content",
            trace_id: "trace-1",
            version_id: "1.2.1-candidate",
            tags: ["plugin", "upgrade"],
            source_refs: ["src-1"],
            evidence_refs: [],
            payload: {},
            status: "active",
            visibility: "internal",
            trust_level: "unverified",
            management_note: "Projected from upgrade.",
            correction_note: null,
            supersedes_memory_id: null,
            superseded_by_memory_id: null,
            operator: "system",
            last_action: "ingested",
            last_action_reason: "Projected from upgrade semantic evidence.",
            last_verified_at: null,
            updated_at: "2026-04-06T00:10:00Z",
            created_at: "2026-04-06T00:00:00Z",
          }),
        } as Response;
      }
      if (url === "/api/web/memory/enhanced/mem-1/audit?limit=20") {
        return {
          ok: true,
          json: async () => ({
            memory_id: "mem-1",
            limit: 20,
            items: [
              {
                event_id: "audit-1",
                memory_id: "mem-1",
                action: "ingested",
                reason: "Projected from upgrade semantic evidence.",
                operator: "system",
                details: {},
                created_at: "2026-04-06T00:00:00Z",
              },
            ],
          }),
        } as Response;
      }
      if (url === "/api/web/memory/enhanced/mem-1/management" && init?.method === "POST") {
        const payload = JSON.parse(String(init.body));
        return {
          ok: true,
          json: async () => ({
            memory_id: "mem-1",
            memory_layer: "semantic",
            source_kind: "upgrade",
            title: "Plugin upgrade for router",
            summary: "Plugin upgrade completed successfully.",
            content: "content",
            trace_id: "trace-1",
            version_id: "1.2.1-candidate",
            tags: ["plugin", "upgrade"],
            source_refs: ["src-1"],
            evidence_refs: [],
            payload: {},
            status: payload.status ?? "active",
            visibility: payload.visibility ?? "internal",
            trust_level: payload.trust_level ?? "trusted",
            management_note: payload.management_note ?? "confirmed",
            correction_note: payload.correction_note ?? null,
            supersedes_memory_id: null,
            superseded_by_memory_id: null,
            operator: payload.operator,
            last_action: "trust_changed:trusted",
            last_action_reason: payload.reason,
            last_verified_at: "2026-04-06T00:20:00Z",
            updated_at: "2026-04-06T00:20:00Z",
            created_at: "2026-04-06T00:00:00Z",
          }),
        } as Response;
      }
      throw new Error(`Unexpected fetch URL: ${url}`);
    });

    render(<MemoryReasoning />);

    await waitFor(() => {
      expect(screen.getByText("记忆治理台")).toBeInTheDocument();
    });

    expect(screen.getByText("Plugin upgrade for router")).toBeInTheDocument();
    expect(screen.getByText("Active: 6")).toBeInTheDocument();

    fireEvent.click(screen.getAllByText("Plugin upgrade for router")[0]);

    await waitFor(() => {
      expect(screen.getByText("记忆详情")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText("治理原因"), {
      target: { value: "Confirmed after trace replay." },
    });
    fireEvent.change(screen.getByLabelText("治理备注"), {
      target: { value: "Can be reused for future plugin upgrades." },
    });
    fireEvent.click(screen.getByText("标记可信"));

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        "/api/web/memory/enhanced/mem-1/management",
        expect.objectContaining({ method: "POST" }),
      );
    });
  });
});
