import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

import AuditReplay from "./AuditReplay";

describe("AuditReplay", () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.startsWith("/api/web/audit/model-provider?")) {
          return {
            ok: true,
            json: async () => [
              {
                trace_id: "trace-1",
                request_id: "req-1",
                decision_id: "decision-1",
                phase_name: "phase_2_frame",
                session_id: "session-1",
                turn_id: "turn-1",
                provider_plugin_id: "model-provider-openai-compat",
                provider_name: "openai_compat",
                model: "gpt-test",
                source_module: "ThinkLoop",
                invocation_phase: "nine_question_q6_redline",
                question_driver_refs: ["q6", "q8"],
                invoked_at: "2026-04-04T12:00:00Z",
                completed_at: "2026-04-04T12:00:01Z",
                failed_at: null,
                prompt: "VERY_LONG_PROMPT_SHOULD_BE_COLLAPSED",
                context: { k: "v" },
                request_driver: { question_driver_refs: ["q6"] },
                result: { ok: true },
                error_type: null,
                error_message: null,
                related_events: [],
              },
            ],
          } satisfies Partial<Response> as Response;
        }
        return {
          ok: false,
          json: async () => ({}),
        } satisfies Partial<Response> as Response;
      }),
    );
  });

  afterEach(() => {
    vi.restoreAllMocks();
    globalThis.fetch = originalFetch;
  });

  it("renders traces and keeps raw JSON accordions collapsed by default", async () => {
    render(<AuditReplay />);

    expect(await screen.findByText("审计与回放")).toBeInTheDocument();
    expect(await screen.findByText("request_id: req-1")).toBeInTheDocument();
    const traceChainButton = screen.getByRole("button", { name: "调用链路溯源" });
    expect(traceChainButton).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(traceChainButton as HTMLElement);
    await waitFor(() => {
      expect(screen.getByText(/九问驱动问题/)).toBeInTheDocument();
    });

    // Raw request JSON section must be collapsed by default.
    const requestAccordionButton = screen.getByRole("button", { name: "原始请求 JSON" });
    expect(requestAccordionButton).toHaveAttribute("aria-expanded", "false");

    // Expand and verify prompt appears.
    fireEvent.click(requestAccordionButton as HTMLElement);
    await waitFor(() => {
      expect(screen.getByText(/VERY_LONG_PROMPT_SHOULD_BE_COLLAPSED/)).toBeInTheDocument();
    });
  });
});
