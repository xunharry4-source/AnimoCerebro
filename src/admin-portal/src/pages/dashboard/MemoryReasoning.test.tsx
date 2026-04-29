import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createInstance } from "i18next";
import { MemoryRouter } from "react-router-dom";
import { I18nextProvider, initReactI18next } from "react-i18next";

import zhCN from "../../locales/zh-CN.json";
import MemoryReasoning from "./MemoryReasoning";

const mockFetch = vi.fn();
global.fetch = mockFetch;

const testI18n = createInstance();
await testI18n.use(initReactI18next).init({
  resources: { "zh-CN": { translation: zhCN } },
  lng: "zh-CN",
  fallbackLng: "zh-CN",
  interpolation: { escapeValue: false },
});

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
      if (url === "/api/web/memory/overview") {
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
            health_status: "degraded",
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
      if (url.startsWith("/api/web/memory/records")) {
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
                source_event_id: "memory-source-event-1",
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
                storage_schema_version: 2,
                record_health_status: "degraded",
                repair_status: "pending_repair",
              },
            ],
          }),
        } as Response;
      }
      if (url === "/api/web/memory/repair/status") {
        return {
          ok: true,
          json: async () => ({
            enabled: true,
            interval_seconds: 3600,
            last_cycle_at: "2026-04-06T00:30:00Z",
            last_summary: { status: "ok", tickets: 1 },
          }),
        } as Response;
      }
      if (url.startsWith("/api/web/memory/search")) {
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
      if (url === "/api/web/memory/mem-1") {
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
            source_event_id: "memory-source-event-1",
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
            storage_schema_version: 2,
            record_health_status: "degraded",
            repair_status: "pending_repair",
          }),
        } as Response;
      }
      if (url === "/api/web/memory/mem-1/diagnostics") {
        return {
          ok: true,
          json: async () => ({
            memory_id: "mem-1",
            storage_schema_version: 2,
            record_health_status: "degraded",
            repair_status: "pending_repair",
            header: {
              memory_id: "mem-1",
              record_health_status: "degraded",
            },
            manifest: {
              memory_id: "mem-1",
              manifest_version: 1,
              descriptors: [
                {
                  block_id: "mem-1:title_block",
                  block_kind: "title_block",
                  required: true,
                  derived: false,
                  codec_chain: ["msgpack"],
                  status: "healthy",
                  repairable: true,
                  compression_strategy: "none",
                  encryption_context: null,
                  last_verified_at: "2026-04-06T00:05:00Z",
                },
                {
                  block_id: "mem-1:content_block",
                  block_kind: "content_block",
                  required: false,
                  derived: false,
                  codec_chain: ["msgpack", "zstd", "aesgcm"],
                  status: "missing",
                  repairable: true,
                  compression_strategy: "zstd",
                  encryption_context: "memory:mem-1:content_block",
                  last_verified_at: "2026-04-06T00:05:00Z",
                },
              ],
            },
            verification: {
              memory_id: "mem-1",
              record_health_status: "degraded",
              repaired_blocks: [],
              quarantined_blocks: ["content_block"],
              projection_repairs: [],
              notes: ["missing content block"],
            },
          }),
        } as Response;
      }
      if (url === "/api/web/memory/mem-1/audit?limit=20") {
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
      if (url === "/api/web/memory/mem-1/management" && init?.method === "POST") {
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
            source_event_id: "memory-source-event-1",
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
      if (url === "/api/web/memory/mem-1/verify" && init?.method === "POST") {
        return {
          ok: true,
          text: async () => JSON.stringify({
            memory_id: "mem-1",
            record_health_status: "degraded",
            repaired_blocks: [],
            quarantined_blocks: ["content_block"],
            projection_repairs: [],
            notes: ["missing content block"],
          }),
          json: async () => ({
            memory_id: "mem-1",
            record_health_status: "degraded",
            repaired_blocks: [],
            quarantined_blocks: ["content_block"],
            projection_repairs: [],
            notes: ["missing content block"],
          }),
        } as Response;
      }
      if (url === "/api/web/memory/mem-1/repair" && init?.method === "POST") {
        return {
          ok: true,
          text: async () => JSON.stringify({
            memory_id: "mem-1",
            record_health_status: "healthy",
            repaired_blocks: ["content_block"],
            quarantined_blocks: [],
            projection_repairs: ["fts_projection", "vector_projection"],
            notes: ["content_block reconstructed"],
          }),
          json: async () => ({
            memory_id: "mem-1",
            record_health_status: "healthy",
            repaired_blocks: ["content_block"],
            quarantined_blocks: [],
            projection_repairs: ["fts_projection", "vector_projection"],
            notes: ["content_block reconstructed"],
          }),
        } as Response;
      }
      if (url === "/api/web/memory/repair/trigger" && init?.method === "POST") {
        return {
          ok: true,
          text: async () => JSON.stringify({
            triggered_by: "web_console_manual",
            scheduler: {
              enabled: true,
              interval_seconds: 3600,
              last_cycle_at: "2026-04-06T00:45:00Z",
              last_summary: { status: "ok", tickets: 1 },
            },
            items: [
              {
                memory_id: "mem-1",
                record_health_status: "healthy",
                repaired_blocks: ["content_block"],
                quarantined_blocks: [],
                projection_repairs: ["fts_projection", "vector_projection"],
                notes: ["content_block reconstructed"],
              },
            ],
          }),
          json: async () => ({
            triggered_by: "web_console_manual",
            scheduler: {
              enabled: true,
              interval_seconds: 3600,
              last_cycle_at: "2026-04-06T00:45:00Z",
              last_summary: { status: "ok", tickets: 1 },
            },
            items: [
              {
                memory_id: "mem-1",
                record_health_status: "healthy",
                repaired_blocks: ["content_block"],
                quarantined_blocks: [],
                projection_repairs: ["fts_projection", "vector_projection"],
                notes: ["content_block reconstructed"],
              },
            ],
          }),
        } as Response;
      }
      throw new Error(`Unexpected fetch URL: ${url}`);
    });

    render(
      <I18nextProvider i18n={testI18n}>
        <MemoryRouter>
          <MemoryReasoning />
        </MemoryRouter>
      </I18nextProvider>,
    );

    await waitFor(() => {
      expect(screen.getByText("记忆治理台")).toBeInTheDocument();
    });

    expect(screen.getAllByText("Plugin upgrade for router").length).toBeGreaterThan(0);
    expect(screen.getByText("Active: 6")).toBeInTheDocument();
    expect(screen.getAllByText("schema:2").length).toBeGreaterThan(0);
    expect(screen.getAllByText("health:degraded").length).toBeGreaterThan(0);
    expect(screen.getAllByText("repair:pending_repair").length).toBeGreaterThan(0);
    expect(screen.getByText("visible:1")).toBeInTheDocument();

    fireEvent.click(screen.getAllByText("Plugin upgrade for router")[0]);

    await waitFor(() => {
      expect(screen.getByText("记忆详情")).toBeInTheDocument();
    });

    expect(screen.getByText("块级诊断")).toBeInTheDocument();
    expect(screen.getByText("Health: degraded")).toBeInTheDocument();
    expect(screen.getByText("repair:on")).toBeInTheDocument();
    expect(screen.getByText("status:ok")).toBeInTheDocument();
    expect(screen.getByText("missing")).toBeInTheDocument();

    expect(screen.getAllByRole("link", { name: "查看 trace" })[0]).toHaveAttribute(
      "href",
      "/console/audit/transcript-replay/trace-1",
    );
    expect(screen.getByRole("link", { name: "查看源事件" })).toHaveAttribute(
      "href",
      "/console/audit/transcript-replay/memory-source-event-1",
    );

    fireEvent.change(screen.getByLabelText("治理原因"), {
      target: { value: "Confirmed after trace replay." },
    });
    fireEvent.change(screen.getByLabelText("治理备注"), {
      target: { value: "Can be reused for future plugin upgrades." },
    });
    fireEvent.click(screen.getByText("标记可信"));

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        "/api/web/memory/mem-1/management",
        expect.objectContaining({ method: "POST" }),
      );
    });

    fireEvent.click(screen.getByRole("button", { name: "校验" }));
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        "/api/web/memory/mem-1/verify",
        expect.objectContaining({ method: "POST" }),
      );
    });

    fireEvent.click(screen.getByRole("button", { name: "修复" }));
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        "/api/web/memory/mem-1/repair",
        expect.objectContaining({ method: "POST" }),
      );
    });

    fireEvent.click(screen.getByRole("button", { name: "全量修复" }));
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        "/api/web/memory/repair/trigger",
        expect.objectContaining({ method: "POST" }),
      );
    });

    expect(screen.getByText("最近一次全量修复")).toBeInTheDocument();
    expect(screen.getAllByText("repaired:1").length).toBeGreaterThan(0);
    expect(screen.getByText("content_block reconstructed")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "只看待修" }));
    await waitFor(() => {
      expect(screen.getByText("health-filter:degraded")).toBeInTheDocument();
      expect(screen.getByText("repair-filter:pending_repair")).toBeInTheDocument();
      expect(screen.getByText("schema-filter:modular_only")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "清除预设" }));
    await waitFor(() => {
      expect(screen.getByText("health-filter:all")).toBeInTheDocument();
      expect(screen.getByText("repair-filter:all")).toBeInTheDocument();
      expect(screen.getByText("schema-filter:all")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "只看旧结构" }));
    await waitFor(() => {
      expect(screen.getByText("当前筛选条件下没有匹配记录。")).toBeInTheDocument();
    });
  });
});
