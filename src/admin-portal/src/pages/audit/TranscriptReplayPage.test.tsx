import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import TranscriptReplayPage from "./TranscriptReplayPage";

describe("TranscriptReplayPage", () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        ({
          ok: true,
          json: async () => ({
            event_id: "trace-123",
            trace_id: "trace-123",
            summary: "学习循环 transcript 回放",
            source_module: "learning_engine",
            invocation_phase: "cycle_started",
            question_driver_refs: ["q8"],
            events: [
              {
                entry_id: "entry-1",
                entry_type: "learning_engine_event",
                timestamp: "2026-04-20T10:00:00Z",
                trace_id: "trace-123",
                source: "zentex.learning.engine",
                payload: { kind: "cycle_started" },
              },
            ],
          }),
        }) as Response,
      ),
    );
  });

  afterEach(() => {
    vi.restoreAllMocks();
    globalThis.fetch = originalFetch;
  });

  it("renders replay summary and linked question refs", async () => {
    render(
      <MemoryRouter initialEntries={["/console/audit/transcript-replay/trace-123"]}>
        <Routes>
          <Route path="/console/audit/transcript-replay/:event_id" element={<TranscriptReplayPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByText("Transcript 回放")).toBeInTheDocument();
    expect(screen.getByText("学习循环 transcript 回放")).toBeInTheDocument();
    expect(screen.getByText("entry_id: entry-1")).toBeInTheDocument();
    expect(screen.getByText("驱动: q8")).toBeInTheDocument();
  });
});
