import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import LearningDashboard from "./LearningDashboard";

describe("LearningDashboard", () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/api/web/learning/plan")) {
          return {
            ok: true,
            json: async () => ({
              directions: [
                {
                  id: "g24_curiosity",
                  architecture_ref: "G24",
                  title_zh: "好奇心学习",
                  title_en: "Curiosity",
                  body_zh: "desc",
                  body_en: "desc",
                },
              ],
              redlines: { zh: "redline", en: "redline" },
            }),
          } as Response;
        }
        if (url.includes("/api/web/learning/history")) {
          return {
            ok: true,
            json: async () => ({
              rows: [
                {
                  entry_id: "entry-1",
                  timestamp: "2026-04-20T10:00:00Z",
                  trace_id: "learn-trace-1",
                  session_id: "learning_engine",
                  replay_event_id: "learn-trace-1",
                  kind: "cycle_started",
                  direction: "g24_curiosity",
                  verified: false,
                  summary: "学习循环启动",
                  architecture_ref: "G24",
                  question_driver_refs: ["q8"],
                },
              ],
            }),
          } as Response;
        }
        return { ok: false, text: async () => "" } as Response;
      }),
    );
  });

  afterEach(() => {
    vi.restoreAllMocks();
    globalThis.fetch = originalFetch;
  });

  it("renders replay and question traceability links", async () => {
    render(
      <MemoryRouter>
        <LearningDashboard />
      </MemoryRouter>,
    );

    expect(await screen.findByText("学习固定问题")).toBeInTheDocument();
    expect(screen.getByText("1. 我今天学到了什么？")).toBeInTheDocument();
    expect(screen.getByText("3. 这些内容下次可以怎么用？")).toBeInTheDocument();
    expect(await screen.findByText("学习循环启动")).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: "q8" })).toHaveAttribute("href", "/console/nine-questions/q8");
    expect(screen.getByRole("link", { name: "查看 trace" })).toHaveAttribute(
      "href",
      "/console/audit/transcript-replay/learn-trace-1",
    );
  });
});
