import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

import UpgradeManagement from "./UpgradeManagement";

const mockFetch = vi.fn();
global.fetch = mockFetch;

describe("UpgradeManagement", () => {
  beforeEach(() => {
    mockFetch.mockReset();
    vi.restoreAllMocks();
  });

  it("renders waiting and ongoing upgrade records and opens detail drawer", async () => {
    vi.spyOn(window, "prompt").mockReturnValue("operator action reason");
    mockFetch.mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input);

      if (url === "/api/web/upgrades/overview") {
        return {
          ok: true,
          text: async () =>
            JSON.stringify({
              llm: { all: 2, waiting: 1, ongoing: 1, completed: 0, failed: 0 },
              plugins: { all: 2, waiting: 0, ongoing: 0, completed: 1, failed: 1 },
              recent_llm: [],
              recent_plugins: [],
            }),
        } as Response;
      }

      if (url === "/api/web/upgrades/llm?lifecycle=all") {
        return {
          ok: true,
          text: async () =>
            JSON.stringify({
              target_kind: "llm",
              lifecycle: "all",
              action_filter: null,
              counts: { all: 2, waiting: 1, ongoing: 1, completed: 0, failed: 0 },
              items: [
                {
                  record_id: "llm-upgrade-q1-001",
                  target_kind: "llm",
                  action: "upgrade",
                  target_id: "nine_questions.q1.where_am_i",
                  title: "Q1 reasoning accuracy optimization",
                  reason: "Q1 domain classification drift detected in mixed workspaces.",
                  trace_id: "upgrade-trace-q1-001",
                  request_id: "upgrade-request-q1-001",
                  source_event_id: "signal:q1-drift-001",
                  parent_record_id: null,
                  evidence_refs: ["metrics/q1_drift_report.json"],
                  change_summary: "Re-optimize prompt bundle and scorer thresholds.",
                  function_summary: "Improve Q1 environment inference stability.",
                  previous_version: "1.0.0",
                  current_version: "1.0.0",
                  candidate_version: "1.1.0-candidate",
                  current_status: "validating",
                  lifecycle_view: "ongoing",
                  current_progress: 72,
                  failure_reason: null,
                  source_path: null,
                  candidate_path: null,
                  audit_status: "running",
                  memory_status: "queued",
                  created_at: "2026-04-06T12:00:00Z",
                  updated_at: "2026-04-06T12:05:00Z",
                  started_at: "2026-04-06T12:00:00Z",
                  finished_at: null,
                  can_cancel: true,
                  can_cleanup_failed_candidate: false,
                },
                {
                  record_id: "llm-upgrade-q4-queue-001",
                  target_kind: "llm",
                  action: "upgrade",
                  target_id: "nine_questions.q4.what_can_i_do",
                  title: "Q4 capability reasoning upgrade queue",
                  reason: "Queued behind the active Q1 optimization batch.",
                  trace_id: "upgrade-trace-q4-queue-001",
                  request_id: "upgrade-request-q4-queue-001",
                  source_event_id: "queue:q4-batch-001",
                  parent_record_id: "llm-upgrade-q1-001",
                  evidence_refs: ["queue/q4_upgrade_batch.json"],
                  change_summary: "Prepare DSPy optimization assets for Q4 capability reasoning.",
                  function_summary: "Improve Q4 actionable-space ranking consistency.",
                  previous_version: "1.2.0",
                  current_version: "1.2.0",
                  candidate_version: "1.3.0-candidate",
                  current_status: "queued",
                  lifecycle_view: "waiting",
                  current_progress: 0,
                  failure_reason: null,
                  source_path: null,
                  candidate_path: null,
                  audit_status: "queued",
                  memory_status: "queued",
                  created_at: "2026-04-06T12:01:00Z",
                  updated_at: "2026-04-06T12:01:00Z",
                  started_at: null,
                  finished_at: null,
                  can_cancel: true,
                  can_cleanup_failed_candidate: false,
                },
              ],
            }),
        } as Response;
      }

      if (url === "/api/web/upgrades/llm-upgrade-q4-queue-001") {
        return {
          ok: true,
          text: async () =>
            JSON.stringify({
              record_id: "llm-upgrade-q4-queue-001",
              target_kind: "llm",
              action: "upgrade",
              target_id: "nine_questions.q4.what_can_i_do",
              title: "Q4 capability reasoning upgrade queue",
              reason: "Queued behind the active Q1 optimization batch.",
              trace_id: "upgrade-trace-q4-queue-001",
              request_id: "upgrade-request-q4-queue-001",
              source_event_id: "queue:q4-batch-001",
              parent_record_id: "llm-upgrade-q1-001",
              evidence_refs: ["queue/q4_upgrade_batch.json"],
              change_summary: "Prepare DSPy optimization assets for Q4 capability reasoning.",
              function_summary: "Improve Q4 actionable-space ranking consistency.",
              previous_version: "1.2.0",
              current_version: "1.2.0",
              candidate_version: "1.3.0-candidate",
              current_status: "queued",
              lifecycle_view: "waiting",
              current_progress: 0,
              failure_reason: null,
              source_path: null,
              candidate_path: null,
              audit_status: "queued",
              memory_status: "queued",
              created_at: "2026-04-06T12:01:00Z",
              updated_at: "2026-04-06T12:01:00Z",
              started_at: null,
              finished_at: null,
              can_cancel: true,
              can_cleanup_failed_candidate: false,
            }),
        } as Response;
      }

      if (url === "/api/web/upgrades/llm-upgrade-q4-queue-001/audit-events") {
        return {
          ok: true,
          text: async () =>
            JSON.stringify([
              {
                event_id: "audit-001",
                record_id: "llm-upgrade-q4-queue-001",
                trace_id: "upgrade-trace-q4-queue-001",
                request_id: "upgrade-request-q4-queue-001",
                source_event_id: "queue:q4-batch-001",
                parent_record_id: "llm-upgrade-q1-001",
                target_kind: "llm",
                action: "upgrade",
                target_id: "nine_questions.q4.what_can_i_do",
                title: "Q4 capability reasoning upgrade queue",
                event_type: "llm_upgrade_started",
                reason: "Queued behind the active Q1 optimization batch.",
                summary: "LLM upgrade execution started with a real optimizer runner.",
                current_status: "queued",
                current_progress: 0,
                previous_version: "1.2.0",
                current_version: "1.2.0",
                candidate_version: "1.3.0-candidate",
                failure_reason: null,
                source_path: null,
                candidate_path: null,
                evidence_refs: ["queue/q4_upgrade_batch.json"],
                payload: {},
                created_at: "2026-04-06T12:01:00Z",
              },
            ]),
        } as Response;
      }

      if (url === "/api/web/upgrades/llm-upgrade-q4-queue-001/memory-records") {
        return {
          ok: true,
          text: async () =>
            JSON.stringify([
              {
                memory_id: "memory-001",
                record_id: "llm-upgrade-q4-queue-001",
                trace_id: "upgrade-trace-q4-queue-001",
                request_id: "upgrade-request-q4-queue-001",
                source_event_id: "queue:q4-batch-001",
                parent_record_id: "llm-upgrade-q1-001",
                target_kind: "llm",
                action: "upgrade",
                target_id: "nine_questions.q4.what_can_i_do",
                title: "Q4 capability reasoning upgrade queue",
                memory_kind: "upgrade_history",
                event_type: "llm_upgrade_started",
                summary: "LLM upgrade execution started with a real optimizer runner.",
                current_status: "queued",
                current_progress: 0,
                previous_version: "1.2.0",
                current_version: "1.2.0",
                candidate_version: "1.3.0-candidate",
                failure_reason: null,
                evidence_refs: ["queue/q4_upgrade_batch.json"],
                payload: {},
                created_at: "2026-04-06T12:01:00Z",
              },
            ]),
        } as Response;
      }

      if (url === "/api/web/upgrades/llm-upgrade-q4-queue-001/cancel") {
        return {
          ok: true,
          text: async () =>
            JSON.stringify({
              record_id: "llm-upgrade-q4-queue-001",
              target_kind: "llm",
              action: "upgrade",
              target_id: "nine_questions.q4.what_can_i_do",
              title: "Q4 capability reasoning upgrade queue",
              reason: "Queued behind the active Q1 optimization batch.",
              trace_id: "upgrade-trace-q4-queue-001",
              request_id: "upgrade-request-q4-queue-001",
              source_event_id: "queue:q4-batch-001",
              parent_record_id: "llm-upgrade-q1-001",
              evidence_refs: ["queue/q4_upgrade_batch.json"],
              change_summary: "Prepare DSPy optimization assets for Q4 capability reasoning.",
              function_summary: "Improve Q4 actionable-space ranking consistency.",
              previous_version: "1.2.0",
              current_version: "1.2.0",
              candidate_version: "1.3.0-candidate",
              current_status: "cancelled",
              lifecycle_view: "failed",
              current_progress: 0,
              failure_reason: "operator action reason",
              source_path: null,
              candidate_path: null,
              audit_status: "cancelled",
              memory_status: "persisted",
              created_at: "2026-04-06T12:01:00Z",
              updated_at: "2026-04-06T12:10:00Z",
              started_at: null,
              finished_at: "2026-04-06T12:10:00Z",
              can_cancel: false,
              can_cleanup_failed_candidate: false,
            }),
        } as Response;
      }

      throw new Error(`unexpected fetch: ${url}`);
    });

    render(<UpgradeManagement />);

    await waitFor(() => {
      expect(screen.getByTestId("upgrade-management-root")).toBeInTheDocument();
    });

    expect(screen.getByText("LLM Upgrade")).toBeInTheDocument();
    expect(screen.getByText("Plugin Evolution")).toBeInTheDocument();
    expect(screen.getByText("Q1 reasoning accuracy optimization")).toBeInTheDocument();
    expect(screen.getByText("Q4 capability reasoning upgrade queue")).toBeInTheDocument();
    expect(screen.getByText("Waiting: 1")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Q4 capability reasoning upgrade queue"));

    await waitFor(() => {
      expect(screen.getByTestId("upgrade-detail-drawer")).toBeInTheDocument();
    });

    const drawer = screen.getByTestId("upgrade-detail-drawer");
    expect(within(drawer).getByText(/Improve Q4 actionable-space ranking consistency/)).toBeInTheDocument();
    expect(within(drawer).getByText(/nine_questions.q4.what_can_i_do/)).toBeInTheDocument();
    expect(within(drawer).getByText(/upgrade-trace-q4-queue-001/)).toBeInTheDocument();
    expect(within(drawer).getAllByText(/LLM upgrade execution started with a real optimizer runner/)).toHaveLength(2);

    fireEvent.click(within(drawer).getByText("取消升级"));

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        "/api/web/upgrades/llm-upgrade-q4-queue-001/cancel",
        expect.objectContaining({ method: "POST" }),
      );
    });
  });
});
